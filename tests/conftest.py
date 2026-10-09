import os

# The app reads the signing key from the environment; tests use a fixed one.
os.environ.setdefault("SESSION_SECRET_KEY", "test-only-key")


def pytest_addoption(parser):
    # Here, not in tests/browser/conftest.py: pytest only reads options from
    # conftest files it loads before parsing the command line
    parser.addoption(
        "--show",
        action="store_true",
        help="Watch the browser tests run: headed, slowed down, Chromium unless "
        "--browser says otherwise (headed WebKit misreads widths on scaled desktops)",
    )
