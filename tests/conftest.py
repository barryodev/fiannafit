import os

# The app reads the signing key from the environment; tests use a fixed one.
os.environ.setdefault("SESSION_SECRET_KEY", "test-only-key")
