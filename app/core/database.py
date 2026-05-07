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


async def get_db() -> AsyncSession:
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
    """Crea las tablas y convierte las relevantes en hypertables de TimescaleDB."""
    async with engine.begin() as conn:
        # Crear todas las tablas definidas en los modelos
        await conn.run_sync(Base.metadata.create_all)

        # Convertir state_vectors en hypertable (serie temporal principal)
        await conn.execute(text("""
            SELECT create_hypertable(
                'state_vectors',
                'time_position',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """))

        # Convertir flight_tracks en hypertable
        await conn.execute(text("""
            SELECT create_hypertable(
                'flight_tracks',
                'timestamp',
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """))

        # Política de compresión automática para state_vectors (> 7 días)
        await conn.execute(text("""
            SELECT add_compression_policy(
                'state_vectors',
                INTERVAL '7 days',
                if_not_exists => TRUE
            );
        """))

        # Política de retención: borrar datos > 30 días para no saturar disco
        await conn.execute(text("""
            SELECT add_retention_policy(
                'state_vectors',
                INTERVAL '30 days',
                if_not_exists => TRUE
            );
        """))

        logger.info("Base de datos inicializada correctamente con TimescaleDB")


async def check_db_connection() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Error de conexión a BD: {e}")
        return False