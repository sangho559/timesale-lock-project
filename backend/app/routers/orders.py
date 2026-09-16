"""
재고 차감 API - 3가지 동시성 제어 방식

/order/no-lock       (A) 락 없음 - Race Condition 재현용 (비교 기준선)
/order/pessimistic   (B) 비관적 락 - SELECT ... FOR UPDATE (행 잠금)
/order/optimistic    (C) 낙관적 락 - version 컬럼 기반 CAS + 재시도

세 엔드포인트 모두 동일한 요청/응답 스키마를 쓰기 때문에,
시뮬레이션 스크립트에서 URL만 바꿔가며 동일 조건으로 비교할 수 있습니다.
"""
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db, engine
from app.models.models import Product, Order, OrderStatus, LockMode
from app.schemas.schemas import OrderRequest, OrderResponse

router = APIRouter(prefix="/order", tags=["orders"])

IS_POSTGRES = engine.dialect.name == "postgresql"
MAX_OPTIMISTIC_RETRIES = 10


def _build_order(
    product_id: int,
    payload: OrderRequest,
    status: OrderStatus,
    lock_mode: LockMode,
    retry_count: int,
    duration_ms: float,
) -> Order:
    """
    Order 객체를 만들기만 하고 commit은 호출부에서 처리.
    (재고 업데이트와 주문 로그 기록을 같은 트랜잭션/커밋으로 묶어야
     - 락 획득 횟수가 요청당 1회로 줄어 SQLite 경합이 크게 줄고
     - 실제 서비스에서도 '재고 차감'과 '주문 기록'은 원자적으로 처리되는 게 맞음)
    """
    return Order(
        product_id=product_id,
        user_id=payload.user_id,
        quantity=payload.quantity,
        status=status,
        lock_mode=lock_mode,
        retry_count=retry_count,
        duration_ms=Decimal(str(round(duration_ms, 3))),
    )


# ---------------------------------------------------------------------------
# (A) 락 없음 - Race Condition 재현용
# ---------------------------------------------------------------------------
@router.post("/no-lock/{product_id}", response_model=OrderResponse)
def order_no_lock(product_id: int, payload: OrderRequest, db: Session = Depends(get_db)):
    """
    의도적으로 '읽고-판단하고-쓰는' 3단계 사이에 아무 보호장치가 없는 버전.
    동시에 여러 요청이 들어오면 같은 stock 값을 동시에 읽고,
    각자 차감 후 덮어쓰기 때문에 실제 판매량보다 재고가 더 많이 빠지거나
    재고가 음수가 될 수 있습니다. -> 이게 이 실험에서 보여주고 싶은 '문제 상황'.
    """
    start = time.perf_counter()

    # 1) 읽기
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 동시 요청 시 경쟁 상태를 더 잘 드러내기 위한 아주 짧은 인위적 지연
    # (읽기와 쓰기 사이 window를 넓혀 race condition을 재현하기 쉽게 함)
    time.sleep(0.001)

    # 2) 판단
    if product.stock < payload.quantity:
        duration_ms = (time.perf_counter() - start) * 1000
        order = _build_order(
            product_id, payload, OrderStatus.OUT_OF_STOCK,
            LockMode.NO_LOCK, 0, duration_ms,
        )
        db.add(order)
        db.commit()
        return OrderResponse(
            status=order.status, lock_mode=order.lock_mode,
            retry_count=0, duration_ms=duration_ms,
            remaining_stock=product.stock, message="재고 부족",
        )

    # 3) 쓰기 (다른 트랜잭션이 이미 값을 바꿨을 수 있음 - 아무 체크 없이 덮어씀)
    product.stock = product.stock - payload.quantity
    duration_ms = (time.perf_counter() - start) * 1000
    order = _build_order(
        product_id, payload, OrderStatus.SUCCESS,
        LockMode.NO_LOCK, 0, duration_ms,
    )
    db.add(product)
    db.add(order)
    db.commit()  # 상품 갱신 + 주문 로그를 한 번에 커밋

    return OrderResponse(
        status=order.status, lock_mode=order.lock_mode,
        retry_count=0, duration_ms=duration_ms,
        remaining_stock=product.stock, message="구매 성공",
    )


# ---------------------------------------------------------------------------
# (B) 비관적 락 - SELECT ... FOR UPDATE
# ---------------------------------------------------------------------------
@router.post("/pessimistic/{product_id}", response_model=OrderResponse)
def order_pessimistic(product_id: int, payload: OrderRequest, db: Session = Depends(get_db)):
    """
    해당 상품 row에 대해 트랜잭션이 끝날 때까지 다른 트랜잭션의 접근을 막는 방식.
    - PostgreSQL: SELECT ... FOR UPDATE 로 실제 행 잠금
    - SQLite: FOR UPDATE 문법 자체가 없어서, BEGIN IMMEDIATE 로
      DB 파일 단위 쓰기 락을 걸어 유사하게 동작을 재현
      (실무에서는 PostgreSQL/MySQL 사용을 권장하며, README에 이 한계를 명시)
    다른 트랜잭션은 락이 풀릴 때까지 대기하므로 정합성은 보장되지만,
    동시 요청이 많을수록 대기 시간이 늘어나 처리량(TPS)이 떨어지는 트레이드오프가 있음.
    """
    start = time.perf_counter()

    if IS_POSTGRES:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .with_for_update()
            .first()
        )
    else:
        # SQLite: 쓰기 잠금을 즉시 획득 (다른 커넥션의 쓰기를 대기시킴)
        db.execute(text("BEGIN IMMEDIATE"))
        product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        db.rollback()
        raise HTTPException(status_code=404, detail="Product not found")

    if product.stock < payload.quantity:
        duration_ms = (time.perf_counter() - start) * 1000
        order = _build_order(
            product_id, payload, OrderStatus.OUT_OF_STOCK,
            LockMode.PESSIMISTIC, 0, duration_ms,
        )
        db.add(order)
        db.commit()  # 락 해제
        return OrderResponse(
            status=order.status, lock_mode=order.lock_mode,
            retry_count=0, duration_ms=duration_ms,
            remaining_stock=product.stock, message="재고 부족",
        )

    product.stock = product.stock - payload.quantity
    duration_ms = (time.perf_counter() - start) * 1000
    order = _build_order(
        product_id, payload, OrderStatus.SUCCESS,
        LockMode.PESSIMISTIC, 0, duration_ms,
    )
    db.add(product)
    db.add(order)
    db.commit()  # 상품 갱신 + 주문 로그 커밋과 동시에 락 해제

    return OrderResponse(
        status=order.status, lock_mode=order.lock_mode,
        retry_count=0, duration_ms=duration_ms,
        remaining_stock=product.stock, message="구매 성공",
    )


# ---------------------------------------------------------------------------
# (C) 낙관적 락 - version 컬럼 기반 CAS(Compare-And-Swap) + 재시도
# ---------------------------------------------------------------------------
@router.post("/optimistic/{product_id}", response_model=OrderResponse)
def order_optimistic(product_id: int, payload: OrderRequest, db: Session = Depends(get_db)):
    """
    락을 걸지 않고 낙관적으로 진행하되, UPDATE 시점에
    'WHERE id = :id AND version = :읽었던_version' 조건으로
    내가 읽은 이후 다른 트랜잭션이 먼저 수정했는지를 확인합니다.
    - 조건에 걸려 반영된 row가 0개면 -> 누군가 먼저 바꿨다는 뜻 -> 재조회 후 재시도
    - MAX_OPTIMISTIC_RETRIES 초과 시 실패 처리(RETRY_EXHAUSTED)
    경쟁이 심하지 않을 때는 락 대기가 없어 빠르지만,
    경쟁이 심해지면 재시도 비용이 늘어나는 트레이드오프가 있음.
    """
    start = time.perf_counter()
    retry_count = 0

    while retry_count <= MAX_OPTIMISTIC_RETRIES:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        if product.stock < payload.quantity:
            duration_ms = (time.perf_counter() - start) * 1000
            order = _build_order(
                product_id, payload, OrderStatus.OUT_OF_STOCK,
                LockMode.OPTIMISTIC, retry_count, duration_ms,
            )
            db.add(order)
            db.commit()
            return OrderResponse(
                status=order.status, lock_mode=order.lock_mode,
                retry_count=retry_count, duration_ms=duration_ms,
                remaining_stock=product.stock, message="재고 부족",
            )

        expected_version = product.version
        new_stock = product.stock - payload.quantity

        # CAS: version이 내가 읽은 값과 같을 때만 갱신 + version 증가
        result = db.execute(
            text(
                """
                UPDATE products
                SET stock = :new_stock, version = version + 1
                WHERE id = :product_id AND version = :expected_version
                """
            ),
            {
                "new_stock": new_stock,
                "product_id": product_id,
                "expected_version": expected_version,
            },
        )

        if result.rowcount == 1:
            # 성공: 내가 읽은 이후 아무도 먼저 바꾸지 않았음 -> 같은 트랜잭션에서 로그까지 커밋
            duration_ms = (time.perf_counter() - start) * 1000
            order = _build_order(
                product_id, payload, OrderStatus.SUCCESS,
                LockMode.OPTIMISTIC, retry_count, duration_ms,
            )
            db.add(order)
            db.commit()
            return OrderResponse(
                status=order.status, lock_mode=order.lock_mode,
                retry_count=retry_count, duration_ms=duration_ms,
                remaining_stock=new_stock, message="구매 성공",
            )

        # 실패: 다른 트랜잭션이 먼저 반영함 -> 롤백 후 재조회하여 재시도
        db.rollback()
        retry_count += 1

    # 재시도 횟수 초과
    duration_ms = (time.perf_counter() - start) * 1000
    order = _build_order(
        product_id, payload, OrderStatus.RETRY_EXHAUSTED,
        LockMode.OPTIMISTIC, retry_count, duration_ms,
    )
    db.add(order)
    db.commit()
    return OrderResponse(
        status=order.status, lock_mode=order.lock_mode,
        retry_count=retry_count, duration_ms=duration_ms,
        remaining_stock=None, message="재시도 초과로 실패",
    )
