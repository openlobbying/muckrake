import os
import logging
from typing import Optional, Any

from muckrake.env import load_env_file

log = logging.getLogger(__name__)

_LOGFIRE_CONFIGURED = False


def configure_logging(
    level: int = logging.INFO,
    app: Optional[Any] = None,
    enable_logfire: bool = False,
) -> None:
    """Configure basic logging and Logfire if available."""
    # Basic logging setup
    logging.basicConfig(level=level)

    global _LOGFIRE_CONFIGURED

    if not enable_logfire:
        return

    try:
        import logfire
    except ImportError:
        _LOGFIRE_CONFIGURED = True
        return

    # If we haven't configured the global Logfire instance yet, do it now
    if not _LOGFIRE_CONFIGURED:
        from muckrake.settings import BASE_PATH

        load_env_file(BASE_PATH / ".env")

        logfire.configure(
            send_to_logfire="if-token-present",
            service_name="muckrake",
            environment=os.getenv("ENVIRONMENT", "development"),
            console=False,
        )
        logfire.instrument_pydantic_ai()
        _LOGFIRE_CONFIGURED = True

    # If an app is provided, instrument it (safe to call multiple times for different apps,
    # but here we usually have one)
    if app:
        try:
            logfire.instrument_fastapi(app)
        except RuntimeError as exc:
            log.warning("FastAPI Logfire instrumentation skipped: %s", exc)
