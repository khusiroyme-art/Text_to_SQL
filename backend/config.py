import os

# Load .env if one sits next to the repo root, so a key set once keeps working
# across restarts instead of having to be re-exported into every new shell.
# Real environment variables always win: on a host like Render the dashboard is
# the source of truth and must never be shadowed by a file that rode along in
# the image.
def _load_dotenv() -> None:
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
# Off unless asked for. A debug-on default is fine until the day it ships:
# Flask's debugger executes arbitrary code from the browser. Turn it on
# explicitly for local work (FLASK_DEBUG=1), never by forgetting to turn it off.
DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

# Render (and most hosts) inject the port to bind. Respect it or the deploy
# looks healthy and answers nothing.
PORT = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", "5000")))

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

# Generous ceiling: one SELECT is small, but adaptive thinking also draws from
# max_tokens and we are billed on what is actually used, not on the cap.
MAX_TOKENS = int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000"))

# low | medium | high | xhigh | max. "medium" keeps an interactive request
# snappy; raise it if generated SQL starts missing joins on wider schemas.
EFFORT = os.environ.get("ANTHROPIC_EFFORT", "medium")

# Total tries for one question: the first generation plus repair attempts.
# 3 is the knee of the curve - a model that has seen the schema and its own
# error twice is not usually saved by a third look, and every attempt is a
# paid API call the user waits on.
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))

# Uploaded databases (Phase 7). Kept out of backend/data/ so a stray upload
# can never shadow or overwrite the shipped demo.
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"),
)
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

# Frontend origin, for CORS. In production the built frontend is served by
# this same Flask app, so it is same-origin and this list is only used by the
# Vite dev server.
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173")

# The built React app. Present in a deployed image, absent during local
# backend-only work - app.py checks rather than assuming.
FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist"),
)
