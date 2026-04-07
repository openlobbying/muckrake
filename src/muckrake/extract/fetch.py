import json
import time
import requests
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING
from lxml import html
from lxml.html import HtmlElement
from banal import hash_data
from rigour.urls import build_url
import logging

if TYPE_CHECKING:
    from nomenklatura.cache import Cache

log = logging.getLogger(__name__)


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
        log.info("Using cached file: %s", out_path)
        return out_path

    log.info("Fetching file from %s", url)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    requester = session.request if session is not None else requests.request

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
    requester = session.request if session is not None else requests.request
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
