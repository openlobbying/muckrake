import logging
import os
from typing import Any

log = logging.getLogger(__name__)

_LOGFIRE_CONFIGURED = False


def configure_logging(
    level: int = logging.INFO,
    app: Any | None = None,
    enable_logfire: bool = False,
) -> None:
    """Configure basic logging and Logfire if available."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.setLevel(level)
    else:
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
        # Importing settings loads .env by the usual rules (nearest file upward,
        # MUCKRAKE_ENV_FILE, skipped when ENVIRONMENT=production), so
        # LOGFIRE_TOKEN can come from it.
        import muckrake.settings  # noqa: F401

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
