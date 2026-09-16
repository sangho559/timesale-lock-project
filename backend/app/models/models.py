"""
상품(Product) / 주문(Order) 모델

핵심 포인트:
- Product.stock: 재고 수량 (동시성 제어의 대상)
- Product.version: 낙관적 락을 위한 버전 컬럼
  (UPDATE 시 version이 내가 읽었던 값과 같을 때만 반영,
   다르면 다른 트랜잭션이 먼저 수정한 것이므로 재시도)
- Order.status: 각 주문 시도의 결과를 남겨 정합성/실패율 검증에 사용
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base


class OrderStatus(str, enum.Enum):
    SUCCESS = "success"          # 재고 차감 성공
    OUT_OF_STOCK = "out_of_stock"  # 재고 부족으로 실패
    RETRY_EXHAUSTED = "retry_exhausted"  # 낙관적 락 재시도 초과로 실패


class LockMode(str, enum.Enum):
    NO_LOCK = "no_lock"
    PESSIMISTIC = "pessimistic"
    OPTIMISTIC = "optimistic"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    sale_start = Column(DateTime, nullable=True)
    sale_end = Column(DateTime, nullable=True)

    # 낙관적 락용 버전 컬럼. UPDATE 시 WHERE version = :expected_version 조건에 사용.
    version = Column(Integer, nullable=False, default=0)

    orders = relationship("Order", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    status = Column(Enum(OrderStatus), nullable=False)
    lock_mode = Column(Enum(LockMode), nullable=False)

    # 낙관적 락에서 몇 번 재시도했는지 (실험 지표용)
    retry_count = Column(Integer, nullable=False, default=0)

    # 요청 처리에 걸린 시간 (ms) - 응답시간 분포(p50/p95/p99) 계산용
    duration_ms = Column(Numeric(10, 3), nullable=True)

    product = relationship("Product", back_populates="orders")
