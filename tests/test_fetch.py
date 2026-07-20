import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from muckrake.extract.fetch import fetch_text, get_session, make_session


class Handler(BaseHTTPRequestHandler):
    failures_remaining = 0
    seen_user_agents: list[str] = []
    request_times: list[float] = []

    def do_GET(self):
        Handler.seen_user_agents.append(self.headers.get("User-Agent", ""))
        Handler.request_times.append(time.monotonic())
        if Handler.failures_remaining > 0:
            Handler.failures_remaining -= 1
            self.send_response(503)
            self.end_headers()
            return
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    Handler.failures_remaining = 0
    Handler.seen_user_agents = []
    Handler.request_times = []
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


def test_retries_transient_statuses(server_url):
    Handler.failures_remaining = 2
    session = make_session(retries=3, backoff_factor=0.01)
    assert fetch_text(server_url, session=session) == "ok"
    assert len(Handler.request_times) == 3


def test_exhausted_retries_raise(server_url):
    Handler.failures_remaining = 10
    session = make_session(retries=2, backoff_factor=0.01)
    with pytest.raises(requests.exceptions.RequestException):
        fetch_text(server_url, session=session)


def test_default_session_sets_user_agent(server_url):
    assert fetch_text(server_url) == "ok"
    assert Handler.seen_user_agents[-1].startswith("muckrake/")


def test_per_host_min_interval(server_url, monkeypatch):
    monkeypatch.setenv("MUCKRAKE_HTTP_MIN_INTERVAL", "0.3")
    fetch_text(server_url, params={"q": "1"})
    fetch_text(server_url, params={"q": "2"})
    assert Handler.request_times[1] - Handler.request_times[0] >= 0.25


def test_shared_session_is_reused():
    assert get_session() is get_session()
