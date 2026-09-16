from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Product
from app.schemas.schemas import ProductCreate, ProductResponse

router = APIRouter(prefix="/product", tags=["products"])


@router.post("/", response_model=ProductResponse)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    product = Product(
        name=payload.name,
        stock=payload.stock,
        price=payload.price,
        sale_start=payload.sale_start,
        sale_end=payload.sale_end,
        version=0,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/{product_id}/reset-stock", response_model=ProductResponse)
def reset_stock(product_id: int, stock: int, db: Session = Depends(get_db)):
    """
    동시 요청 시뮬레이션을 여러 번(A/B/C 각각) 반복 실행해야 하므로,
    매 실험 전 재고를 원하는 값으로 되돌리기 위한 헬퍼 엔드포인트.
    """
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.stock = stock
    product.version = 0
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
