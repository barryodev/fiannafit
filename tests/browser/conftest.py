"""Browser tests (DAI-11 step 3b): the real app in Chromium and WebKit.

These only cover what the TestClient tests can't prove: static files loading,
HTMX swapping responses in, browser-side JS and the real cookie jar, and layout.

The app runs as its own uvicorn process over HTTPS, with a throwaway self-signed
certificate made for this test run. The session cookie is Secure, so this keeps
the same cookie behaviour as production without changing the app. The browser
is told to accept the certificate (ignore_https_errors), so no warning page.
"""

import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.request

import pytest

STARTUP_TIMEOUT_SECONDS = 15


def pytest_configure(config):
    """Run in both engines unless --browser picks some: WebKit is the nearest
    stand-in for iOS Safari. Set here, not in addopts, because --browser on
    the command line adds to addopts' browsers instead of replacing them."""
    if config.option.show:
        config.option.headed = True
        config.option.slowmo = config.option.slowmo or 300
        config.option.browser = config.option.browser or ["chromium"]
    if not config.option.browser:
        config.option.browser = ["chromium", "webkit"]


@pytest.fixture(scope="session")
def tls_cert(tmp_path_factory) -> tuple[str, str]:
    """A self-signed certificate for 127.0.0.1, only for this test run."""
    cert_dir = tmp_path_factory.mktemp("tls")
    key, cert = cert_dir / "key.pem", cert_dir / "cert.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", key, "-out", cert, "-subj", "/CN=fiannafit-test",
            "-addext", "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return str(key), str(cert)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_up(url: str, cert: str, server: subprocess.Popen, log_path) -> None:
    # Trusts the throwaway certificate itself, so this is real, verified HTTPS
    context = ssl.create_default_context(cafile=cert)
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"{url}/healthz", context=context, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    server.kill()
    pytest.fail(f"The app didn't start. Its output:\n{log_path.read_text()}")


@pytest.fixture(scope="session")
def base_url(tls_cert, tmp_path_factory):
    """Start the app and give its address. Replaces pytest-base-url's fixture,
    so tests can use page.goto("/")."""
    key, cert = tls_cert
    port = _free_port()
    url = f"https://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("server") / "uvicorn.log"
    env = os.environ | {"SESSION_SECRET_KEY": "browser-test-only-key"}
    with log_path.open("w") as log:
        server = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "fiannafit.main:app",
                "--host", "127.0.0.1", "--port", str(port),
                "--ssl-keyfile", key, "--ssl-certfile", cert,
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )  # fmt: skip
    try:
        _wait_until_up(url, cert, server, log_path)
        yield url
    finally:
        server.terminate()
        server.wait(timeout=10)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """A mid-size Android phone (412×915, touch) that accepts the test certificate."""
    return browser_context_args | {
        "ignore_https_errors": True,
        "viewport": {"width": 412, "height": 915},
        "is_mobile": True,
        "has_touch": True,
    }
