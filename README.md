# Backend Deployment

This folder is ready for Render deployment.

## Local demo setup

For the current QR-session based WhatsApp runtime, local execution is the most reliable demo path.

### Windows quick start

From this `backend` folder you can run either:

- `.\start-local.ps1`
- `start-local.bat`

This script will:

- create `.venv` if needed
- install dependencies
- set local login defaults
- start the backend at `http://127.0.0.1:5050`

Default local login:

- `rajm267747@gmail.com`
- `WhatsAppTest`

### Public demo from your machine

If you want the client to open your local working backend from outside your machine:

1. Start the backend locally with `.\start-local.ps1`
2. Install Cloudflare Tunnel
3. Run:

   - `.\start-public-tunnel.ps1`

That exposes your local backend URL publicly while the WhatsApp QR runtime stays on your machine.

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
- The dashboard can be hosted, but QR-session based WhatsApp runtime is more reliable locally or on a VPS than on a free web-service container.

## Recommended client deployment paths

### Option 1: Fastest working demo

- Host frontend/dashboard publicly
- Run this backend locally on one always-on Windows machine
- Expose it with Cloudflare Tunnel

### Option 2: Better hosted deployment

- Move this backend to a VPS
- Use persistent disk/session storage
- Keep the frontend on Vercel

### Option 3: Production-grade long-term path

- Replace QR-session runtime with an official WhatsApp provider
- Keep the CRM UI and lead workflows, but move messaging to supported API infrastructure
