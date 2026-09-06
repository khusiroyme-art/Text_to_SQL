# Two stages so Node never ships to production: the frontend is built here and
# only its output is copied into the Python image.
FROM node:24-slim AS frontend

WORKDIR /app/frontend
# Copy manifests first so `npm ci` is cached until dependencies actually change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# The demo database ships in the image; uploads are written here at runtime and
# are deliberately not persisted (see README).
RUN mkdir -p backend/uploads

# 5000 to match the local dev port and every example in the README. Hosts
# that inject PORT (Render does) override it; the default only matters for
# a plain `docker run`.
EXPOSE 5000

# Threads, not more workers: every request spends its time waiting on the
# Anthropic API or on SQLite, so this is an I/O-bound service. The timeout
# clears the worst case - MAX_ATTEMPTS model calls plus query time.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 180 backend.app:app"]
