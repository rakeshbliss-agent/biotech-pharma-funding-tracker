# Biotech/Pharma Funding Tracker (FastAPI + HTML/CSS + NLP search)

## Deploy on Render
Create a **Web Service**:
- Build: `pip install -r app/requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Weekly auto-update
- RSS sources are configured in `app/sources.yaml`.
- For best extraction accuracy, add GitHub Actions secret `OPENAI_API_KEY`.
