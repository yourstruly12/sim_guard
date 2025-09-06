# SIMGuard - Demo (Hackathon)

This repo contains a demo of SIMGuard Central: a prototype automated system that monitors SIM registrations and simulates auto-freeze & recovery workflows.

## Quick start (dev)
1. Backend:
   - cd backend
   - python -m venv venv
   - source venv/bin/activate  # or venv\Scripts\activate on Windows
   - pip install -r requirements.txt
   - uvicorn main:app --reload --port 8000

2. Frontend:
   - cd frontend
   - python -m http.server 5500
   - open http://127.0.0.1:5500/index.html

Make sure the API_BASE in frontend/index.html points to http://127.0.0.1:8000 during local dev.
