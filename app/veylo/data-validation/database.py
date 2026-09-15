import logging
import os
from typing import Generator
import google.auth
from google.auth.exceptions import DefaultCredentialsError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

logger = logging.getLogger(__name__)


def create_db_engine() -> Engine:
    """
    Creates the SQLAlchemy engine.
    If BigQuery is specified but Google Application Default Credentials (ADC) are not found,
    it falls back to a local SQLite database for local development and test execution.
    """
    settings = get_settings()
    db_url = settings.effective_database_url

    if db_url.startswith("bigquery"):
        try:
            # Test if credentials are valid before binding engine
            google.auth.default()
            logger.info(f"Connecting to BigQuery using ADC: {db_url}")
            return create_engine(db_url, pool_pre_ping=True)
        except DefaultCredentialsError:
            fallback_url = "sqlite:///veylo_local.db"
            logger.warning(
                f"Google Application Default Credentials (ADC) not found. "
                f"Falling back to local SQLite database '{fallback_url}' for local development. "
                f"Set GOOGLE_APPLICATION_CREDENTIALS or DATABASE_URL to customize."
            )
            return create_engine(fallback_url, connect_args={"check_same_thread": False})
        except Exception as ex:
            fallback_url = "sqlite:///veylo_local.db"
            logger.warning(f"Could not initialize BigQuery engine ({ex}). Falling back to SQLite '{fallback_url}'.")
            return create_engine(fallback_url, connect_args={"check_same_thread": False})

    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    logger.info(f"Connecting to database: {db_url}")
    return create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)


engine = create_db_engine()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
