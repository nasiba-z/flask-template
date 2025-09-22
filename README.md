# Synthia Pipeline (Hackathon Template)

This is a minimal Cloud Run service for the Google Cloud solutions.

## Features
- Receives Pub/Sub push messages
- Decrypts payloads (Base64 or ROT-N)
- Saves decrypted text to Cloud Storage

## Deploy (from Cloud Shell)

```bash
gcloud run deploy synthia-handler \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --set-env-vars OUTPUT_BUCKET=YOUR_BUCKET_NAME,GCP_REGION=europe-west6
