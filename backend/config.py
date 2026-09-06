import os

FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

# Generous ceiling: one SELECT is small, but adaptive thinking also draws from
# max_tokens and we are billed on what is actually used, not on the cap.
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000"))

# low | medium | high | xhigh | max. "medium" keeps an interactive request
# snappy; raise it if generated SQL starts missing joins on wider schemas.
EFFORT = os.environ.get("ANTHROPIC_EFFORT", "medium")

# Phase 6 frontend origin, for CORS.
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
