import json
import os
import threading
import time
import requests
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING
from urllib.parse import urlparse
from lxml import html
from lxml.html import HtmlElement
from banal import hash_data
from requests.adapters import HTTPAdapter
from rigour.urls import build_url
from urllib3.util.retry import Retry
import logging

if TYPE_CHECKING:
    from nomenklatura.cache import Cache

log = logging.getLogger(__name__)

RETRY_STATUSES = (429, 500, 502, 503, 504)


def _user_agent() -> str:
    try:
        pkg_version = version("muckrake")
    except PackageNotFoundError:
        pkg_version = "dev"
    return f"muckrake/{pkg_version} (+https://github.com/openlobbying/muckrake)"


def make_session(retries: int = 5, backoff_factor: float = 1.0) -> requests.Session:
    """A polite HTTP session: connection pooling, a muckrake User-Agent, and
    retry with exponential backoff on transient failures (connection errors
    and 429/5xx statuses, honouring Retry-After). Only idempotent methods
    (GET/HEAD) are retried — a failed POST is raised immediately."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=("GET", "HEAD"),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers["User-Agent"] = _user_agent()
    return session


@cache
def get_session() -> requests.Session:
    """The shared session used whenever a caller does not supply one."""
    return make_session()


_throttle_lock = threading.Lock()
_next_request_at: dict[str, float] = {}


def _throttle(url: str) -> None:
    """Enforce a minimum interval between requests to the same host
    (MUCKRAKE_HTTP_MIN_INTERVAL, seconds; off by default)."""
    interval = float(os.getenv("MUCKRAKE_HTTP_MIN_INTERVAL") or 0)
    if interval <= 0:
        return
    host = urlparse(url).netloc
    with _throttle_lock:
        now = time.monotonic()
        wait = _next_request_at.get(host, now) - now
        _next_request_at[host] = max(now, _next_request_at.get(host, now)) + interval
    if wait > 0:
        time.sleep(wait)


def request_hash(
    url: str,
    auth: Optional[Any] = None,
    method: str = "GET",
    data: Any = None,
) -> str:
    """Generate a unique fingerprint for an HTTP request."""
    hsh = hash_data((auth, method, data))
    return f"{url}[{hsh}]"


def fetch_file(
    url: str,
    name: str,
    data_path: Path,
    session: Optional[requests.Session] = None,
    auth: Optional[Any] = None,
    headers: Optional[Any] = None,
    method: str = "GET",
    data: Optional[Any] = None,
    verify: bool = True,
    timeout: float = 120,
) -> Path:
    """Fetch a file via HTTP to the data path, with local caching."""
    out_path = data_path.joinpath(name)
    if out_path.exists():
        # log.info("Using cached file: %s", out_path)
        return out_path

    log.info("Fetching file from %s", url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    requester = (session or get_session()).request
    _throttle(url)

    with requester(
        method=method,
        url=url,
        auth=auth,
        headers=headers,
        stream=True,
        data=data,
        timeout=timeout,
        verify=verify,
    ) as res:
        res.raise_for_status()
        with open(out_path, "wb") as fh:
            for chunk in res.iter_content(chunk_size=8192 * 10):
                fh.write(chunk)

    return out_path


def fetch_text(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    auth: Optional[Any] = None,
    method: str = "GET",
    data: Optional[Any] = None,
    cache: Optional["Cache"] = None,
    cache_days: Optional[int] = None,
    sleep: Optional[float] = None,
    verify: bool = True,
    timeout: float = 120,
) -> Optional[str]:
    """Execute an HTTP request and return the response text."""
    url = build_url(url, params)
    fingerprint = request_hash(url, auth=auth, method=method, data=data)

    if cache is not None and cache_days is not None:
        text = cache.get(fingerprint, max_age=cache_days)
        if text is not None:
            log.debug("HTTP cache hit: %s", url)
            return text
        if text is None and sleep is not None and sleep > 0:
            time.sleep(sleep)

    log.debug("HTTP %s: %s", method, url)
    requester = (session or get_session()).request
    _throttle(url)
    response = requester(
        method=method,
        url=url,
        headers=headers,
        auth=auth,
        data=data,
        timeout=timeout,
        verify=verify,
    )
    response.raise_for_status()
    text = response.text

    if cache is not None and cache_days is not None and text is not None:
        cache.set(fingerprint, text)

    return text


def fetch_json(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    auth: Optional[Any] = None,
    method: str = "GET",
    data: Optional[Any] = None,
    cache: Optional["Cache"] = None,
    cache_days: Optional[int] = None,
    sleep: Optional[float] = None,
    verify: bool = True,
    timeout: float = 120,
) -> Any:
    """Execute an HTTP request and return a JSON-decoded object."""
    text = fetch_text(
        url,
        params=params,
        headers=headers,
        session=session,
        auth=auth,
        method=method,
        data=data,
        cache=cache,
        cache_days=cache_days,
        sleep=sleep,
        verify=verify,
        timeout=timeout,
    )
    if text is not None and len(text.strip()):
        return json.loads(text)
    return None


def fetch_html(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    auth: Optional[Any] = None,
    method: str = "GET",
    data: Optional[Any] = None,
    absolute_links: bool = False,
    cache: Optional["Cache"] = None,
    cache_days: Optional[int] = None,
    sleep: Optional[float] = None,
    verify: bool = True,
    timeout: float = 120,
) -> HtmlElement:
    """Execute an HTTP request and return an lxml HTML element."""
    full_url = build_url(url, params)
    text = fetch_text(
        url,
        params=params,
        headers=headers,
        session=session,
        auth=auth,
        method=method,
        data=data,
        cache=cache,
        cache_days=cache_days,
        sleep=sleep,
        verify=verify,
        timeout=timeout,
    )
    if text is None or len(text.strip()) == 0:
        raise ValueError(f"Invalid HTML document from {url}")

    doc = html.fromstring(text)
    if absolute_links and isinstance(doc, html.HtmlElement):
        doc.make_links_absolute(full_url)
    return doc
