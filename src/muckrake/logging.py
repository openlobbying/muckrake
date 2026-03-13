import os
import logging
from typing import Optional, Any

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
        # Load .env if present and not already loaded (simple manual load)
        from muckrake.settings import BASE_PATH

        env_path = BASE_PATH / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)

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
