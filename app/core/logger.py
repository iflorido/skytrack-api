import sys
from loguru import logger
from app.core.config import settings


def setup_logging():
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    level = "DEBUG" if settings.DEBUG else "INFO"
    logger.add(sys.stdout, format=fmt, level=level, colorize=True)

    logger.add(
        "logs/skytrack_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        format=fmt,
        level="INFO",
        encoding="utf-8",
    )

    logger.info(f"Logging configurado — nivel: {level} — entorno: {settings.ENVIRONMENT}")