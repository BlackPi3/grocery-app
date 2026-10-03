# The server: the API, the shopper's page at `/`, and the photo reader.
#
# Everything the server keeps lives outside the image: the history in
# PostgreSQL (DATABASE_URL), and photos, the ALDI crawl and the model caches
# under /app/data, which the host mounts from object storage. The image holds
# code only, so it is safe to build from the public repo.
#
# Configuration is environment only: DATABASE_URL, GROCERY_TOKEN (the
# password), GEMINI_API_KEY, GROCERY_READER/GROCERY_MATCHER/GROCERY_IDENTIFY.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]" && rm -rf src

# Not root: nothing here needs it.
RUN useradd --create-home --uid 1000 grocery && mkdir -p /app/data && chown grocery /app/data
USER grocery

# Migrations first, so a new image never serves an old schema. `db upgrade`
# is a no-op on a database that is already current.
ENV PORT=8080
CMD ["sh", "-c", "grocery-app db upgrade && exec uvicorn --factory grocery_app.api.app:default_app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'"]
