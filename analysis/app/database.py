"""E14 Analysis — Database configuration."""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Match acquisition database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://e14user:***@db:5432/e14acquisition"
)

# Fallback to SQLite if not set (dev/testing)
engine = create_engine(
    DATABASE_URL if "postgresql" in DATABASE_URL else "sqlite:///./analysis.db",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
