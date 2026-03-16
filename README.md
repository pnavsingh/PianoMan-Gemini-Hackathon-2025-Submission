# Vita — AI Visual Health Screening Agent

> **Hackathon Demo** · Built with Gemini Live API + Google Cloud

Vita is a real-time AI health screening assistant that guides users through a visual wellness check-in via their webcam. Using the **Gemini 2.5 Flash Native Audio** model, Vita speaks, listens, and analyzes what she sees through the live camera feed.

---

## Current State (as of last session)

### What's working
- Full 5-step scan flow: Eyes → Nails → Tongue → Teeth & Gums → Skin
- Gemini Live API bidirectional streaming (audio + video)
- MediaPipe face + hand landmark overlays
- Thumbs-up/thumbs-down gesture consent flow
- Transcript drawer with unread badge
- Auto-capture + result cards on step completion
- Cross-body-part pattern recognition in final summary
- Vertex AI enhanced report button (Gemini 1.5 Pro via Vertex AI)
- Firestore session history (optional)
- GCS snapshot storage (optional)

### Recent changes made this session
1. **Zoom removed** — `scale(1.04)` stripped from `.scanning` CSS; camera stays natural size
2. **Frame confirmation thumbnail** — when user taps "I'm Ready", a hi-res snapshot is captured and shown in the scanning panel with a "✓ VITA CAPTURED THIS FRAME" badge so the user can confirm Vita sees them
3. **Follow-up questions after each category** — all 5 step prompts now instruct Vita to ask "Do you have any specific questions about what I've just observed?" after finishing the analysis, wait for the response, answer it, then say "Analysis complete. Moving on."
4. **Cutoff fix** — auto-continuation: if Vita's turn ends mid-analysis (before asking the follow-up or saying "Analysis complete"), the frontend waits 3 seconds and auto-sends "Please continue your analysis." Does NOT fire if Vita already asked the follow-up question.
5. **Vertex AI integration** — `POST /api/generate-report` endpoint uses Vertex AI (Gemini 1.5 Pro) to produce a structured clinical report. Button appears on summary screen. Requires `GOOGLE_CLOUD_PROJECT` in `.env`.

### Known issue fixed
- **Double analysis bug** — was caused by the auto-continuation timer firing when Vita had legitimately paused to ask the follow-up question. Fixed by checking `lb.includes('specific questions') || lb.includes('any questions')` before sending the nudge.

---

## Environment Setup

### .env (project root)
```env
GEMINI_API_KEY=AIzaSyBfMCiy8hEK021Yt5qjPKowOX-ozp-ZiO0
GOOGLE_CLOUD_PROJECT=project-piano-agent-challenge
GCS_BUCKET=your-bucket-name
```

### Python venv
Located at: `C:\Users\aweso\OneDrive\Documents\Resume stuff\projects\venvgemini`

Activate:
```powershell
& "C:\Users\aweso\OneDrive\Documents\Resume stuff\projects\venvgemini\Scripts\Activate.ps1"
```

### GCP / Vertex AI setup status
- Google Cloud SDK installed (gcloud in PATH after opening a new terminal)
- ADC credentials saved: `C:\Users\aweso\AppData\Roaming\gcloud\application_default_credentials.json`
- Quota project: `project-piano-agent-challenge`
- **Vertex AI API must be enabled** in the GCP console for the enhanced report to work
- `vertexai` and `google-cloud-aiplatform` packages need to be installed in the venv:
  ```
  pip install vertexai google-cloud-aiplatform
  ```

### Run locally
```bash
python main.py
```
Open **http://localhost:8080**

---

## Architecture

```
Browser (WebRTC mic + webcam)
        │  WebSocket (audio PCM 16kHz + JPEG frames)
        ▼
FastAPI Server (Python)
        │  Gemini Live API (bidirectional streaming)
        ▼
gemini-2.5-flash-native-audio-preview-12-2025
        │
        ├── Audio response (PCM 24kHz) ──► Browser speaker
        └── Transcript (output_audio_transcription) ──► UI text

Browser (client-side ML):
  MediaPipe FaceLandmarker ── 478-point face landmarks for eye/mouth/face highlights
  MediaPipe HandLandmarker ── landmarks for thumbs-up / thumbs-down gesture detection

GCP services (all optional — app runs in demo mode without them):
  Vertex AI (Gemini 1.5 Pro) ── enhanced structured wellness report at end of session
  Firestore  ── session history & summaries
  Cloud Storage ── body-part snapshot images
```

**Key technologies:**
| Technology | Role |
|---|---|
| Gemini Live API | Real-time bidirectional multimodal streaming |
| Gemini 2.5 Flash Native Audio | Voice + vision model with VAD interruption support |
| Vertex AI / Gemini 1.5 Pro | Structured clinical report generation at session end |
| Google GenAI SDK (`google-genai`) | Python client for Live API |
| MediaPipe Tasks Vision | Client-side face + hand landmark detection |
| Cloud Firestore | Session history persistence (optional) |
| Cloud Storage (GCS) | Snapshot image storage (optional) |

---

## Demo Flow

1. Open the app and enter your name
2. An **intro card** shows while the camera warms up (3 seconds)
3. Once ready, a **thumbs-up card** appears — hold 👍 for ~1 second to trigger Vita
4. Vita greets you and asks **"Can I analyze you today?"**
5. Show 👍 (yes) or 👎 (no) using the **consent gesture card** with dual progress rings
6. After consent, Vita gives a **brief 1-2 sentence check** and asks you to confirm
7. You confirm verbally or via text → Vita starts the 5-step scan wizard
8. For each step, tap **"I'm Ready"** — a **frame confirmation thumbnail** appears showing exactly what Vita is looking at, then 5 fresh frames are sent to Gemini before the prompt fires
9. Vita analyzes, then asks **"Do you have any specific questions?"** — you can ask follow-ups before she moves on
10. Each step auto-completes when Vita says "analysis complete"
11. At the end, Vita delivers a wellness summary with severity tiers
12. Click **"✨ Enhanced Report (Vertex AI)"** to generate a structured clinical report via Gemini 1.5 Pro on Vertex AI

---

## Project Structure

```
├── main.py          # FastAPI backend + Gemini Live session handler + Vertex AI report endpoint
├── static/
│   └── index.html   # Single-page frontend (camera, audio, transcript, CV overlay, step wizard)
├── requirements.txt
├── Dockerfile
└── .env
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves the frontend |
| GET | `/api/history/{user_id}` | Retrieves past sessions from Firestore |
| POST | `/api/generate-report` | Vertex AI enhanced report (needs GCP) |
| WS | `/ws/{user_id}` | Main Gemini Live session WebSocket |

### POST /api/generate-report
```json
{ "summary": "<full session transcript>", "user_name": "Alex" }
```
Returns a structured report with Overall Tier, Findings by Area, Cross-Patterns, Next Steps, Disclaimer.

---

## How the Live API Integration Works

The backend maintains a **persistent bidirectional stream** with Gemini for each user session:

- **Audio in**: Browser captures 16kHz PCM from mic → sent continuously (no energy gate) → `send_realtime_input(audio=...)`
- **Video in**: JPEG frames at ~3fps idle, ~4fps during active scan → `send_realtime_input(video=...)`
- **Audio out**: Gemini returns 24kHz PCM chunks → browser queues and plays via Web Audio API
- **Transcript**: `output_audio_transcription` config enables real-time text
- **Interruption**: User speech triggers Gemini's VAD; `sc.interrupted` resets audio queue
- **Text input**: Typed messages forwarded as `send_client_content(turn_complete=True)`

### Frame resolution
- **Idle / greeting phase**: 640×360 @ 80% JPEG quality
- **Active body part scan**: 1280×720 @ 92% JPEG quality

---

## Anti-Hallucination Design

1. **Camera warm-up** — 3s intro card before any gesture detection
2. **Consent-gated description** — Vita only describes the user after thumbs-up consent; by then Gemini has been watching 10-15+ seconds
3. **Forced first-sentence anchor** — each step prompt mandates `"Looking at your [body part] right now, I can see [specific color/feature]..."` before any generic clinical text
4. **5 fresh frames** sent right before each step prompt fires
5. **Frame confirmation thumbnail** — visible to the user so they can see what Vita captured

---

## Known Behaviours / Notes

- **No energy gate on mic**: Audio sent continuously so Gemini's VAD correctly detects turn end
- **Auto-continuation**: If Vita's turn ends mid-analysis (before asking "any specific questions?"), frontend auto-sends "Please continue your analysis." after 3 seconds
- **Follow-up gate**: The continuation does NOT fire if Vita already asked the follow-up question — she's intentionally waiting for user input
- **Glasses auto-polling**: During eye step, Vita checks for glasses every 3s until confirmed removed
- **Video mirroring**: `scaleX(-1)` on video element for natural mirror; canvas frames apply same flip so Gemini sees correct orientation
- **No zoom on scanning**: CSS `.scanning` class no longer applies `scale(1.04)` — removed to preserve visual quality

---

## Disclaimer

Vita is for general wellness tracking only. It is **not a medical device** and does not provide diagnoses. Always consult a licensed healthcare professional for medical concerns.
