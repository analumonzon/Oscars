# Oscars Ballot Tool

Local web app for Oscar party guests to submit ballots, track winners, and view a live leaderboard.
The ballot file is loaded once on startup and persisted into SQLite (replacing any existing ballot data).

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
	On startup, the ballot in SQLite is replaced with the file contents.
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