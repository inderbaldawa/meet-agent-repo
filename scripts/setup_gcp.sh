#!/usr/bin/env bash
# One-time GCP setup for the meet-agent project.
#
# Prereqs: run `gcloud auth login` and `gcloud auth application-default login`
# yourself first (both open a browser).
#
# Usage:
#   PROJECT_ID=meet-agents-yourname BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./scripts/setup_gcp.sh
#
# Get your billing account ID with: gcloud billing accounts list

set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID env var (must be globally unique, e.g. meet-agents-yourname)}"
: "${BILLING_ACCOUNT:?Set BILLING_ACCOUNT env var. List with: gcloud billing accounts list}"

REGION="${REGION:-us-central1}"
SA_NAME="meet-bot-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
KEY_DIR="${HOME}/keys"
KEY_PATH="${KEY_DIR}/${PROJECT_ID}-sa.json"

echo ">> creating project ${PROJECT_ID}"
gcloud projects create "${PROJECT_ID}" --name="Meet AI Agents" || echo "(project may already exist)"

echo ">> setting active project"
gcloud config set project "${PROJECT_ID}"

echo ">> linking billing account ${BILLING_ACCOUNT}"
gcloud billing projects link "${PROJECT_ID}" --billing-account="${BILLING_ACCOUNT}"

echo ">> enabling APIs (takes ~30s)"
gcloud services enable \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  vision.googleapis.com \
  customsearch.googleapis.com \
  iamcredentials.googleapis.com \
  generativelanguage.googleapis.com

echo ">> creating Firestore database in ${REGION} (Native mode)"
gcloud firestore databases create --location="${REGION}" --type=firestore-native || echo "(database may already exist)"

echo ">> creating service account ${SA_NAME}"
gcloud iam service-accounts create "${SA_NAME}" \
  --display-name="Meet Bot Service Account" || echo "(service account may already exist)"

echo ">> granting roles"
for role in roles/datastore.user roles/aiplatform.user roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${role}" \
    --condition=None
done

echo ">> generating service account key at ${KEY_PATH}"
mkdir -p "${KEY_DIR}"
chmod 700 "${KEY_DIR}"
gcloud iam service-accounts keys create "${KEY_PATH}" \
  --iam-account="${SA_EMAIL}"
chmod 600 "${KEY_PATH}"

cat <<EOF

GCP setup complete.

Next manual steps:

1. Programmable Search Engine
   - Go to https://programmablesearchengine.google.com/
   - Create a new search engine: "Search the entire web"
   - Copy the "Search engine ID" (cx)

2. Custom Search API key
   - https://console.cloud.google.com/apis/credentials?project=${PROJECT_ID}
   - Create credentials > API key
   - Restrict it to "Custom Search API" (good hygiene, optional)

3. Gemini API key (separate from service account)
   - https://aistudio.google.com/apikey
   - Create API key, choose project ${PROJECT_ID}

4. Firebase linkage
   - https://console.firebase.google.com/
   - "Add project" > "Add Firebase to existing Google Cloud project" > ${PROJECT_ID}
   - In the Firebase console: Build > Firestore Database > use existing database
   - Project settings > General > Your apps > Add Web app > register
   - Copy the firebaseConfig object into frontend/.env

5. Populate backend/.env (copy from .env.example):
   GCP_PROJECT_ID=${PROJECT_ID}
   GOOGLE_APPLICATION_CREDENTIALS=${KEY_PATH}
   GEMINI_API_KEY=<from step 3>
   GOOGLE_SEARCH_API_KEY=<from step 2>
   GOOGLE_SEARCH_CX=<from step 1>

EOF
