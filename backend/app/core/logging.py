"""Application logging configuration."""

import logging
import sys


def configure_logging() -> None:
    """Configure standard library logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )
    # Reduce noise from third-party loggers
    for name in ("uvicorn", "uvicorn.access", "sqlalchemy.engine", "alembic"):
        logging.getLogger(name).setLevel(logging.WARNING)


logger = logging.getLogger("uzex_ai")
