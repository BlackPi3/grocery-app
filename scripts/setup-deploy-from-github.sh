#!/bin/sh
# One-time: let GitHub Actions deploy this repo's main to Cloud Run.
#
# GitHub proves which repo and branch a workflow runs for with a signed
# token; Google trusts that token through Workload Identity Federation and
# lets it act as one deploy account. No Google key is stored in GitHub.
# Only BlackPi3/grocery-app on refs/heads/main gets in.
#
#   GROCERY_PROJECT=<gcp project id> scripts/setup-deploy-from-github.sh
#
# Safe to run again: what already exists is kept, and the grants are repeated.
set -eu

PROJECT=${GROCERY_PROJECT:?set GROCERY_PROJECT to the Google Cloud project id}
REPO=BlackPi3/grocery-app
NUMBER=$(gcloud projects describe "$PROJECT" --format="value(projectNumber)")
DEPLOYER="github-deployer@$PROJECT.iam.gserviceaccount.com"

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com --project "$PROJECT"

# The trust: tokens from GitHub, accepted only for this repo's main.
gcloud iam workload-identity-pools describe github --project "$PROJECT" --location=global \
    >/dev/null 2>&1 ||
gcloud iam workload-identity-pools create github --project "$PROJECT" \
  --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe grocery-app --project "$PROJECT" \
    --location=global --workload-identity-pool=github >/dev/null 2>&1 ||
gcloud iam workload-identity-pools providers create-oidc grocery-app --project "$PROJECT" \
  --location=global --workload-identity-pool=github --display-name="$REPO" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='$REPO' && assertion.ref=='refs/heads/main'"

# The deploy account, and what it may do: deploy Cloud Run from source, and
# start the server as grocery-server (and the build as the build account).
gcloud iam service-accounts describe "$DEPLOYER" --project "$PROJECT" >/dev/null 2>&1 ||
gcloud iam service-accounts create github-deployer --project "$PROJECT" \
  --display-name="GitHub Actions deploys"
# A new account takes a little while to be visible to IAM; a grant made
# before that fails with "does not exist".
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  gcloud iam service-accounts get-iam-policy "$DEPLOYER" --project "$PROJECT" \
      >/dev/null 2>&1 && break
  sleep 5
done
for role in roles/run.admin roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" --condition=None --format=none \
    --member="serviceAccount:$DEPLOYER" --role="$role"
done
for runs_as in "grocery-server@$PROJECT.iam.gserviceaccount.com" \
               "$NUMBER-compute@developer.gserviceaccount.com"; do
  gcloud iam service-accounts add-iam-policy-binding "$runs_as" --project "$PROJECT" \
    --format=none --member="serviceAccount:$DEPLOYER" --role=roles/iam.serviceAccountUser
done

# GitHub, for this repo only, may act as the deploy account.
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --project "$PROJECT" \
  --format=none --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

echo "Done. The workflow uses:"
echo "  provider: projects/$NUMBER/locations/global/workloadIdentityPools/github/providers/grocery-app"
echo "  account:  $DEPLOYER"
