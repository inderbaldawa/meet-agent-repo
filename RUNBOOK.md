# Runbook

End-to-end startup for the two-laptop demo.

## One-time setup (laptop A)

1. **gcloud auth** (interactive — opens browser):
   ```
   gcloud auth login
   gcloud auth application-default login
   ```

2. **Provision GCP** — get a billing account ID first:
   ```
   gcloud billing accounts list
   PROJECT_ID=meet-agents-yourname BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX \
     ./scripts/setup_gcp.sh
   ```

3. **Custom Search + Gemini key** (manual, web UI):
   - https://programmablesearchengine.google.com/ → new engine → "Search the entire web" → copy CX
   - Cloud Console → Credentials → create API key restricted to Custom Search API
   - https://aistudio.google.com/apikey → create Gemini API key under your project

4. **Firebase** (manual, web UI):
   - https://console.firebase.google.com/ → "Add project" → select existing GCP project
   - Build → Firestore Database → use existing native database
   - Project settings → Your apps → Add Web app → register, copy config

5. **Populate `.env` files**:
   - `cp .env.example .env` at the repo root and fill values
   - `cp frontend/.env.example frontend/.env` and paste the Firebase web config

6. **Deploy Firestore security rules**:
   ```
   firebase deploy --only firestore:rules --project <PROJECT_ID>
   ```
   (or paste `firestore.rules` into the Firebase console manually)

## Each demo (laptop A)

Open three terminals on laptop A:

**Terminal 1 — orchestrator:**
```
set -a; source .env; set +a
cd backend && .venv/bin/uvicorn backend.orchestrator.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend:**
```
cd frontend && npm run dev
```
Note Vite's "Network:" URL — laptop B will use it.

**Terminal 3 — your LAN IP:**
```
ipconfig getifaddr en0
```

**Browser tab 1 — host the Meet:**
- meet.google.com → New meeting → Start an instant meeting
- Keep this tab visible so you can click **Admit** when the bot joins.

**Laptop B — open the dashboard:**
- `http://<laptopA-LAN-IP>:5173`
- Paste the Meet URL into the Deploy tab, click Deploy
- The Vite frontend's `VITE_ORCH_URL` must point to `http://<laptopA-LAN-IP>:8000`.
  If laptop B sees `localhost:8000` it cannot reach the orchestrator — edit `frontend/.env`
  on laptop A and restart Vite.

**Back on laptop A:**
- Click **Admit** when the bot requests to join. The orchestrator waits 60s.
- Once admitted, switch to laptop B to watch the dashboard.

## Mac firewall

If laptop B cannot reach laptop A's ports, allow inbound for the venv Python and Node:
```
sudo /usr/libexec/ApplicationFirewall/socketfilterfw \
  --add /Users/budha.mandapaka/meet-agent/backend/.venv/bin/python
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp \
  /Users/budha.mandapaka/meet-agent/backend/.venv/bin/python
sudo /usr/libexec/ApplicationFirewall/socketfilterfw \
  --add /opt/homebrew/bin/node
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp /opt/homebrew/bin/node
```
Or temporarily disable: System Settings → Network → Firewall → off.

## Tear-down

- DELETE /session/{sid} on the orchestrator (frontend currently has no UI for this — use curl)
- Ctrl-C the orchestrator and Vite when done

## Common breakage

| Symptom | Cause | Fix |
|---|---|---|
| Bot stuck "waiting for host admission" | You forgot to click Admit | Click Admit in the Meet tab |
| Bot keeps timing out at name input | Meet DOM changed | Re-run `python -m backend.bot.discover_selectors <meet-url>`, update `backend/bot/selectors.py` |
| Dashboard never lights up | Firestore rules block reads, or wrong project id | Verify rules deployed; check `VITE_FIREBASE_PROJECT_ID` matches the GCP project |
| Bot reaction click fails | Reactions popover layout changed | Update `selectors.reaction_emoji_button` |
| CORS errors in browser console | Laptop B IP not in ALLOWED_ORIGINS | Set `ALLOWED_ORIGINS=http://<laptopA-LAN-IP>:5173` in backend `.env` and restart uvicorn |
| Vision API 403 | Vision API not enabled or SA missing role | `gcloud services enable vision.googleapis.com` and re-check service account roles |
| Gemini 404 model | Model not available in your project | Edit `MODEL` in `backend/agents/*_agent.py` to `gemini-2.0-flash` / `gemini-2.0-pro` or check `client().models.list()` |
