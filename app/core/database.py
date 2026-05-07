from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from loguru import logger
from app.core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Crea las tablas y convierte las relevantes en hypertables de TimescaleDB.
    Las políticas de compresión y retención se configuran manualmente en la BD
    una sola vez — no se gestionan aquí para evitar errores en el arranque.
    """
    async with engine.begin() as conn:

        # Crear todas las tablas definidas en los modelos
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tablas creadas/verificadas correctamente")

        # Convertir state_vectors en hypertable (serie temporal principal)
        await conn.execute(text("""
            SELECT create_hypertable(
                'state_vectors',
                'time_position',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """))
        logger.info("Hypertable state_vectors OK")

        # Convertir flight_tracks en hypertable
        await conn.execute(text("""
            SELECT create_hypertable(
                'flight_tracks',
                'timestamp',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """))
        logger.info("Hypertable flight_tracks OK")

        logger.info("Base de datos inicializada correctamente con TimescaleDB")


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Error de conexión a BD: {e}")
        return False