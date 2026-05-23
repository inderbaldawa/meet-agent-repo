# Meet Agent

An AI-powered meeting assistant that joins a Google Meet as a bot, observes the session through computer vision, researches topics in real time, engages participants via chat and reactions, and moderates emoji spam — all driven by a Firestore event bus and displayed on a live React dashboard.

---

## Features

### Vision-Based Meeting Awareness
- Takes a screenshot of the meeting every **3 seconds**
- Runs **Google Cloud Vision** on each screenshot: object/scene labels, full-text OCR, and logo detection
- A **context agent** (Gemini) distills every screen analysis into a `topic`, `sentiment`, and `urgency` score

### Real-Time Research
- A **research agent** (Gemini) automatically Googles the current topic using Google Programmable Search (3 results)
- Extracts a ≤25-word factual summary with source citations
- Results are **cached per topic for 5 minutes** to avoid redundant API calls

### Autonomous Chat Engagement
- A **hype agent** (Gemini) crafts a conversational chat message (≤90 chars) and selects a reaction emoji based on the research
- Messages are queued to Firestore and sent to the meeting with a **5-second global floor** between any two bot actions
- **SHA-256-based deduplication** prevents the same message from being sent twice
- Respects a **30-second per-session cooldown** to avoid spamming

### Emoji Spam Moderation
- A **moderator agent** monitors every incoming chat message
- Automatically posts a warning (`⚠️ Please keep emoji use to a minimum`) if a message contains more than 5 emojis
- Rate-limited to **one warning per 60 seconds**

### Playwright Bot
- Joins Google Meet as a guest using **headless Chromium** (Playwright) with fake media streams
- Waits up to **60 seconds** for the host to admit the bot
- Can send chat messages, send emoji reactions, take screenshots, and leave the meeting programmatically

### FastAPI Orchestrator
- `POST /deploy` — Launch a bot into a Meet URL; returns a session ID
- `GET /session/{id}` — Retrieve live session state from Firestore
- `DELETE /session/{id}` — Gracefully shut down the bot and all agent loops
- `GET /health` — List currently active sessions

### Real-Time React Dashboard
- Connects directly to Firestore via `onSnapshot` for zero-polling live updates
- **Current Topic card** — topic, sentiment, urgency from the context agent
- **Research card** — fact summary + clickable citation links
- **Live Events feed** — last 20 screen analysis and chat events
- **Incident Log** — color-coded per-agent action history (context, research, hype, moderator)

---

## Architecture

```
Screen share (host)
       │
       ▼  (Playwright screenshot every 3s)
  MeetBot (Chromium)
       │
       ▼
Google Cloud Vision ──► labels, OCR text, logos
       │
       ▼
  Firestore  ◄──────────────────────────────────┐
  events/screen_analysis                        │
       │                                        │
       ▼                                        │
 context_agent (Gemini flash)                   │
  → topic, sentiment, urgency                   │
  → sessions/{sid}.shared_context              │
       │                                        │
       ▼                                        │
 research_agent (Gemini pro + Google Search)    │
  → summary, citations                          │
  → sessions/{sid}.research_data               │
       │                                        │
       ▼                                        │
 hype_agent (Gemini flash)                      │
  → chat message + emoji                        │
  → chat_queue / reaction_queue ───────────────►│
                                                │
 drainer_loop (1s tick, 5s action floor) ──────►┘
  → bot.send_chat() / bot.send_reaction()

 moderator_agent
  ← events/chat_message (every 4s poll)
  → warning message if emoji count > 5

 React Dashboard
  ← onSnapshot (Firestore real-time)
  → live topic, research, events, incidents
```

All agents communicate exclusively through Firestore — the screen capture writes events, agents react via `onSnapshot` listeners running in a thread pool, and the drainer loop executes queued bot actions.

---

## Project Structure

```
meet-agent/
├── backend/
│   ├── agents/
│   │   ├── context_agent.py      # Vision → topic/sentiment/urgency (Gemini)
│   │   ├── research_agent.py     # Topic → Google Search + summary (Gemini)
│   │   ├── hype_agent.py         # Research → chat + emoji (Gemini)
│   │   └── moderator_agent.py    # Chat → emoji spam detection
│   ├── bot/
│   │   ├── meet_bot.py           # Playwright Google Meet automation
│   │   └── selectors.py          # Accessibility locators for Meet UI
│   ├── orchestrator/
│   │   ├── main.py               # FastAPI app (deploy/stop/health routes)
│   │   ├── loop.py               # Screenshot capture + chat polling loops
│   │   ├── listeners.py          # Firestore onSnapshot → agent dispatch
│   │   └── drainer.py            # Bot action queue executor
│   ├── storage/
│   │   └── firestore_client.py   # Firestore helpers, queues, caching, cooldowns
│   ├── tools/
│   │   └── google_search.py      # Google Programmable Search wrapper
│   └── vision/
│       └── labeler.py            # Google Cloud Vision (labels, OCR, logos)
├── frontend/
│   └── src/
│       ├── App.tsx               # Tab shell (Deploy / Dashboard)
│       ├── api.ts                # Axios client for orchestrator
│       ├── firebase.ts           # Firestore SDK init
│       └── components/
│           ├── DeployTab.tsx     # Bot deploy form
│           ├── DashboardTab.tsx  # Real-time session dashboard
│           └── IncidentFeed.tsx  # Color-coded agent incident log
├── scripts/
│   └── setup_gcp.sh              # One-time GCP provisioning script
├── firestore.rules               # Firestore security rules
├── RUNBOOK.md                    # Detailed setup and demo instructions
└── DEMO_SCRIPT.md                # 3-minute live demo talk track
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Google Cloud project with the following APIs enabled:
  - Cloud Vision API
  - Cloud Firestore
  - Gemini API (via AI Studio or Vertex)
  - Custom Search API
- A Google service account with Firestore and Vision permissions
- A Google Programmable Search Engine configured to search the entire web

---

## Setup

### 1. Clone and configure environment

```bash
cp .env.example .env
# Fill in GCP_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS, GEMINI_API_KEY,
# GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_CX
```

```bash
cp frontend/.env.example frontend/.env
# Fill in VITE_FIREBASE_* values from your Firebase project settings
```

### 2. Deploy Firestore rules

```bash
firebase deploy --only firestore:rules
```

### 3. Start the backend

```bash
cd backend
pip install uv && uv sync
uv run uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, paste a Google Meet URL in the Deploy tab, and admit the bot from the meeting.

---

## Configuration

| Variable | Description |
|---|---|
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account key JSON |
| `GEMINI_API_KEY` | API key from [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GOOGLE_SEARCH_API_KEY` | Cloud Console API key with Custom Search enabled |
| `GOOGLE_SEARCH_CX` | Programmable Search Engine ID |
| `ORCH_HOST` / `ORCH_PORT` | Orchestrator bind address (default `0.0.0.0:8000`) |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins for the frontend |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot automation | Playwright (Chromium) |
| Computer vision | Google Cloud Vision API |
| AI agents | Google Gemini (flash + pro via `google-genai`) |
| Web search | Google Programmable Search Engine |
| Event store | Google Cloud Firestore |
| Backend API | FastAPI + uvicorn |
| Frontend | React + TypeScript + Vite + Tailwind CSS |
| Real-time UI | Firestore `onSnapshot` |

---

## Known Limitations

- Bot joins as a guest and requires manual admission by the meeting host
- Vision-only awareness — no audio or speech-to-text transcription
- No persistent meeting summaries or post-session exports
- Single active session per orchestrator process (no horizontal scaling)
