"""
DB 연결 설정

- 기본값: SQLite (설치/설정 없이 바로 실행 가능, 로컬 데모용)
- PostgreSQL로 바꾸려면 DATABASE_URL 환경변수만 교체하면 됨
  예) postgresql://user:password@localhost:5432/timesale

주의: SQLite는 파일 기반 락이라 동시성 실험의 '순수한 DB 레벨 비교'에는
PostgreSQL이 더 적합합니다. 다만 하루 만에 셋업 없이 돌려보는 용도로는
SQLite로 충분히 A(no-lock) vs B(비관적 락) vs C(낙관적 락)의 차이를
보여줄 수 있습니다. README에 이 트레이드오프를 명시할 예정입니다.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./timesale.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# SQLite에서 동시 쓰기 시 자주 발생하는 "database is locked" 오류를 줄이기 위해
# timeout을 넉넉히 주고, WAL 모드를 사용합니다.
engine = create_engine(
    DATABASE_URL,
    connect_args={**connect_args, "timeout": 30} if DATABASE_URL.startswith("sqlite") else connect_args,
    pool_pre_ping=True,
)

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
