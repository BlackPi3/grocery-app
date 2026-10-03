#!/bin/sh
# Build the server image from this checkout and roll it out to Cloud Run.
#
# One-time setup (the database, the bucket, the secrets) is in
# docs/designs/backend-api.md, "Phase 3". This script is the part that repeats.
# GitHub Actions runs it after every green merge to main
# (.github/workflows/deploy.yml); by hand, run it from the repo root.
#
#   GROCERY_PROJECT=<gcp project id> scripts/deploy.sh
set -eu

PROJECT=${GROCERY_PROJECT:?set GROCERY_PROJECT to the Google Cloud project id}
REGION=${GROCERY_REGION:-europe-west3}

# --no-cpu-throttling: a photo is read after the upload's response has gone
#   out (api/jobs.py), and without it Cloud Run starves that work of CPU.
# --max-instances 1: one shopper; jobs run inside the process that took them.
# The service account may read the two secrets, connect to the database, use
#   the bucket and call Gemini on Vertex AI, and nothing else.
# Gemini goes through Vertex AI as that account (GEMINI_VERTEX_PROJECT): no key,
#   and the calls are billed to this project.
# --allow-unauthenticated: the app checks GROCERY_TOKEN itself on /v1, so the
#   page can load on a phone with no Google sign-in.
# The bucket is mounted where the code expects data/: photos in data/uploads,
#   the ALDI crawl in data/products, the model caches in data/matched and
#   data/identified. uid 1000 is the image's user.
gcloud run deploy grocery --quiet \
  --source . \
  --project "$PROJECT" --region "$REGION" \
  --allow-unauthenticated \
  --service-account "grocery-server@$PROJECT.iam.gserviceaccount.com" \
  --max-instances 1 --no-cpu-throttling --memory 1Gi --timeout 300 \
  --add-cloudsql-instances "$PROJECT:$REGION:grocery" \
  --set-secrets "DATABASE_URL=database-url:latest,GROCERY_TOKEN=grocery-token:latest" \
  --set-env-vars "GROCERY_READER=gemini,GROCERY_MATCHER=gemini,GROCERY_IDENTIFY=gemini,GEMINI_VERTEX_PROJECT=$PROJECT" \
  --add-volume "name=data,type=cloud-storage,bucket=$PROJECT-grocery-data,mount-options=uid=1000;gid=1000" \
  --add-volume-mount "volume=data,mount-path=/app/data"
