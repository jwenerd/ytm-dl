#!/usr/bin/env bash

gcloud functions deploy trigger_run_post --gen2 --runtime=python312 --region=us-central1  --source=./src/cloud_functions --entry-point=trigger_run_post --trigger-http --allow-unauthenticated --set-secrets='SECRETS=APP_SECRETS:latest' --memory=128Mi
