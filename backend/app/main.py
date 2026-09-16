from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import Base, engine
from app.routers import orders, products

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Timesale Lock Comparison API",
    description="선착순 타임세일 & 재고 차감 API - 비관적 락 vs 낙관적 락 동시성 제어 비교",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 데모용. 실제 배포 시에는 출처 제한 필요.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(orders.router)


@app.get("/")
def health_check():
    return {"status": "ok", "service": "timesale-lock-api"}
