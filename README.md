# Oscars Ballot Tool

Local web app for Oscar party guests to submit ballots, track winners, and view a live leaderboard.
The ballot file is loaded on first startup and persisted into SQLite.

## Features
- Digital ballot form with one pick per category
- Admin page to lock ballots and enter winners
- Automatic scoring with live leaderboard
- Data stored locally in SQLite

## Requirements
- Python 3.10+

## Setup
1. Install dependencies:
	```bash
	pip install -r requirements.txt
	```
2. Ensure your ballot CSV is present at docs/OscarBallotList.csv (or set OSCARS_BALLOT_PATH).
	On first startup (or when the DB is empty), the ballot in SQLite is initialized from the file.
3. Run the app:
	```bash
	uvicorn app.main:app --host 0.0.0.0 --port 8000
	```

Open http://localhost:8000 on your laptop. Share the same URL (with your laptop IP) via email or QR code.

## CSV Format
Each row is:
```
category, points, nominee1, nominee2, nominee3, ...
```
Example:
```
Best Actress, 7, Jessie Buckley - "Hamnet" (94.7%), Rose Byrne - "If I had legs I'd kick you" (10.0%), Renate Reinsve - "Sentimental Value" (5.9%)
```

## Admin Access
Set an optional admin key to protect /admin:
```bash
export OSCARS_ADMIN_KEY="your-secret"
```
Then open:
```
http://localhost:8000/admin?key=your-secret
```

## Environment Variables
- OSCARS_BALLOT_PATH: path to the CSV or XLSX ballot file (default: docs/OscarBallotList.csv)
- OSCARS_ADMIN_KEY: optional admin key for /admin
- OSCARS_DB_PATH: path to SQLite file (default: data/oscars.db)
- OSCARS_RESET_BALLOT_ON_START: if true, reloads ballot file and clears existing votes/winners on startup (default: false)

## Public Deployment

### Can this run on GitHub Pages?
No. GitHub Pages only hosts static sites, and this app requires a running FastAPI backend.

### Recommended: Google Cloud Run
This repo includes a `Dockerfile` for container deployment.

1. Set your project and enable required services:
	```bash
	gcloud config set project YOUR_PROJECT_ID
	gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
	```

2. Build and push the container:
	```bash
	gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/oscars-ballot
	```

3. Deploy to Cloud Run:
	```bash
	gcloud run deploy oscars-ballot \
	  --image gcr.io/YOUR_PROJECT_ID/oscars-ballot \
	  --region us-central1 \
	  --platform managed \
	  --allow-unauthenticated \
	  --set-env-vars OSCARS_ADMIN_KEY=YOUR_SECRET
	```

4. Open the service URL from the deploy output.

### Data Persistence Note
Cloud Run local filesystem is ephemeral. With the current SQLite setup, data can be lost on instance replacement.
For production persistence, move to a managed database (for example Cloud SQL Postgres) before event day.