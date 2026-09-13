import logging
from typing import Generator
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from models.orm import Base

logger = logging.getLogger(__name__)


def create_db_engine() -> Engine:
    settings = get_settings()
    url = settings.effective_database_url
    connect_args = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        logger.info(f"[Database] Using local SQLite database: {url}")
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool
            return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
        return create_engine(url, connect_args=connect_args)

    logger.info(f"[Database] Connecting to BigQuery engine: {url}")
    return create_engine(url, pool_pre_ping=True)


engine = create_db_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db() -> None:
    """Initializes tables for SQLite development or ensures schema readiness."""
    settings = get_settings()
    if settings.is_sqlite:
        logger.info("[Database] Ensuring local SQLite tables exist...")
        Base.metadata.create_all(bind=engine)


def get_db_session() -> Session:
    """Returns a new database session."""
    return SessionLocal()
