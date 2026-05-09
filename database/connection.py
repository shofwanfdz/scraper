"""
Database Connection Manager
Uses SQLAlchemy for ORM with MySQL backend
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from config.settings import DATABASE_URL
from .models import Base


class DatabaseManager:
    """
    Manages database connections and sessions.
    """

    def __init__(self, url: str = None):
        self.url = url or DATABASE_URL
        self.engine = create_engine(
            self.url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            echo=False,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        logger.info("Database connection established")

    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def drop_tables(self):
        """Drop all database tables (use with caution!)"""
        Base.metadata.drop_all(bind=self.engine)
        logger.warning("All database tables dropped!")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()

    def get_session_direct(self) -> Session:
        """Get a database session (caller must manage lifecycle)"""
        return self.SessionLocal()


# Global database instance
_db_manager = None


def get_db() -> DatabaseManager:
    """Get or create the global database manager"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
