@echo off
cd /d "%~dp0"
call gcloud builds submit --config=cloudbuild.dashboard.yaml --ignore-file=.gcloudignore-dashboard --project=project-e64210d0-f317-4050-833
if errorlevel 1 exit /b 1
call gcloud run services update factory-dashboard-api --project=project-e64210d0-f317-4050-833 --region=asia-south1 --image=asia-south1-docker.pkg.dev/project-e64210d0-f317-4050-833/factory-ai-investigator/dashboard-api:v5
if errorlevel 1 exit /b 1
call firebase deploy --only hosting --project project-e64210d0-f317-4050-833