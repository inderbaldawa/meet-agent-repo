# Demo script (3 minutes)

## Setup (before audience joins)

- Orchestrator + Vite running on laptop A
- Meet open in a browser tab on laptop A (you are host)
- Dashboard open on laptop B / projector
- Three props ready: coffee mug, recognisable book, slide reading "Q3 Revenue"

## Talk track

### 0:00 — Frame the problem
> "Four agents, one Google Meet. They observe what's on screen, research it, react in
> chat, and moderate spam — without any human telling them what to do. Let's deploy them."

### 0:20 — Deploy
- On laptop B's dashboard, paste the Meet URL → click **Deploy**
- Switch to laptop A's Meet tab → click **Admit**

> "The bot just joined as a guest. From here, everything you see on the dashboard is
> driven by what the Meet looks like — no API integration, just a browser and Vision AI."

### 0:50 — Coffee mug
- Hold a coffee mug in front of the camera
- Wait ~6s, then point at the dashboard

> "Context agent sees labels like 'mug', 'beverage'. Research agent kicks in… and Hype
> drops a chat line. Notice the latency: about 8 seconds from object to chat."

### 1:30 — Book
- Hold up a recognisable book cover

> "Now something it has to actually research. The chat line cites the book by name —
> that's Custom Search + Gemini 3.1 Pro distilling a snippet."

### 2:10 — Spam test
- Type 10 emojis into the Meet chat from your own account
- Within 5s the bot replies with the moderator warning

> "Moderator agent. Same listener pattern — emoji count > 5, rate-limited so it only
> warns once per minute."

### 2:30 — Architecture
- Click through the dashboard's Incident Feed

> "Every action is logged: which agent, what action, why. Firestore drives the dashboard
> in real time — onSnapshot listeners, not polling. Each agent is ~80 lines of Python
> calling Gemini with a JSON schema."

### 2:50 — Close
> "Built in 5 days. No ADK, no Cloud Run yet — just a Playwright bot, four agents, and
> Firestore. Open source, plug your own keys in, runs on a laptop."

## Things that can go wrong on stage

| Symptom | Recovery |
|---|---|
| Bot doesn't request admission | Refresh Meet tab on laptop A, click Deploy again |
| Vision returns no labels (object too far) | Hold the object closer, ≥30% of frame |
| Chat line is too generic | That's the LLM — talk over it, demo the spam test instead |
| Network blip → dashboard freezes | onSnapshot reconnects; if not, refresh the dashboard |
