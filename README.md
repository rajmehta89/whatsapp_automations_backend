# Backend Deployment

This folder is ready for Render deployment.

## What runs here

- Flask CRM workspace
- WhatsApp connection runtime
- AI reply logic
- knowledge base processing
- local SQLite/session storage

## Required environment variables

Set these in Render before first deploy:

- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY=your_openai_key`
  or use `OPENAI_API_KEY_1`
- `OPENAI_MODEL=gpt-4.1-mini`
- `ASSISTANT_NAME=Service Desk Assistant`
- `SYNC_WHATSAPP_HISTORY=true`
- `WHATSAPP_HISTORY_LOOKBACK_HOURS=6`
- `ADMIN_NUMBERS=your_whatsapp_number`

Render will provide:

- `PORT`

## Render setup

1. Create a new Web Service in Render.
2. Upload only this `backend` folder.
3. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn dashboard:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
4. Add a persistent disk if you want WhatsApp sessions and SQLite data to survive restarts.
5. After the first deploy, open the Render URL once, then use that URL inside the Vercel frontend `config.js`.

## Important notes

- Without a persistent disk, WhatsApp QR/session data can be lost after restart or redeploy.
- QR generation and WhatsApp linking still happen from the backend workspace UI.
- This backend is now aligned with the latest CRM workspace: lead score, readiness, tasks, knowledge settings, and availability rules.
