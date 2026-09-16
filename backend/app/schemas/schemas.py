from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.models.models import OrderStatus, LockMode


class ProductCreate(BaseModel):
    name: str
    stock: int
    price: Decimal
    sale_start: Optional[datetime] = None
    sale_end: Optional[datetime] = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stock: int
    price: Decimal
    version: int


class OrderRequest(BaseModel):
    user_id: str
    quantity: int = 1


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    status: OrderStatus
    lock_mode: LockMode
    retry_count: int = 0
    duration_ms: Optional[float] = None
    remaining_stock: Optional[int] = None
    message: str = ""
