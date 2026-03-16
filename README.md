# Vita — AI Visual Health Screening Agent

> **Hackathon Submission** · Built with Gemini Live API + Google Cloud

Vita is a real-time AI health screening assistant that guides users through a visual wellness check-in via their webcam. Using **Gemini 2.5 Flash Native Audio**, Vita speaks, listens, and analyzes what she sees through a live camera feed — all in a single continuous bidirectional stream.

---

## What It Does

Vita performs a structured 5-step visual wellness scan:

1. **Eyes** — sclera clarity, redness, signs of jaundice
2. **Nails** — color, texture, capillary indicators
3. **Tongue** — coating, color, hydration
4. **Teeth & Gums** — gum color, visible dental concerns
5. **Skin** — tone, texture, visible conditions

After each step, Vita asks if you have follow-up questions before moving on. At the end, she delivers a cross-pattern wellness summary with severity tiers and an **Enhanced Report** generated via Vertex AI (Gemini 1.5 Pro).

**Returning users** see their previous session data on the intro screen and Vita explicitly compares today's findings to last time.

---

## Key Features

- **Gemini Live API** bidirectional streaming — real-time audio + video to/from the model
- **Gesture-based consent flow** — thumbs-up / thumbs-down via MediaPipe hand landmarks
- **MediaPipe face + hand overlays** — 478-point face mesh and hand landmark visualization
- **Frame confirmation thumbnail** — user sees exactly what Vita captured before each scan step
- **Fully auto-progressive UX** — no manual button clicks required; Vita drives the entire flow
- **`vitaSpeaking` state tracking** — all auto-progression gates on Vita's silence so she never talks over herself
- **Auto-continuation logic** — if Vita's turn ends mid-analysis, the frontend nudges her to continue (but not if she's intentionally waiting for a user question)
- **"Ready to continue?" gate** — Vita explicitly asks after each analysis and waits for user confirmation before moving on
- **Vertex AI enhanced report** — structured clinical report with findings, cross-patterns, and next steps; saved to Firestore automatically
- **Firestore session history** — `users/{userId}/sessions/{sessionId}` subcollection structure; no composite index required
- **Previous session comparison** — Vita's system prompt is injected with last session's findings and told to explicitly call out changes
- **Previous session banner** — returning users see last scan date, tier, per-area summary, and optionally full prior report on the intro screen
- **GCS snapshot storage** — body-part JPEGs stored at `health_scans/{userId}/{sessionId}/{part}_{timestamp}.jpg`

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
  Firestore  ── users/{userId}/sessions/{sessionId} subcollection
  Cloud Storage ── health_scans/{userId}/{sessionId}/{bodyPart}_{ts}.jpg
```

**Tech stack:**

| Technology | Role |
|---|---|
| Gemini Live API | Real-time bidirectional multimodal streaming |
| Gemini 2.5 Flash Native Audio | Voice + vision model with VAD interruption support |
| Vertex AI / Gemini 1.5 Pro | Structured clinical report generation at session end |
| Google GenAI SDK (`google-genai`) | Python client for Live API |
| MediaPipe Tasks Vision | Client-side face + hand landmark detection |
| FastAPI | WebSocket server + REST endpoints |
| Cloud Firestore | `users/{userId}/sessions/{sessionId}` session history |
| Cloud Storage (GCS) | Per-session body-part JPEG snapshots |

---

## Demo Flow

1. Open the app and enter your name
2. **Returning users** see a previous session banner: last scan date, overall wellness tier, per-area findings, and optionally the full prior clinical report
3. An **intro card** shows while the camera warms up (3 seconds)
4. Once ready, a **thumbs-up card** appears — hold 👍 for ~1 second to trigger Vita
5. Vita greets you and asks **"Can I analyze you today?"**
6. Show 👍 (yes) or 👎 (no) using the **consent gesture card** with dual progress rings
7. After consent, Vita gives a brief 1-2 sentence check and asks you to confirm
8. **No click needed** — `beginExamination()` fires automatically once Vita finishes speaking
9. For each step, a **3-second countdown** starts and the step fires automatically (or tap the button to skip the wait)
10. A **frame confirmation thumbnail** shows exactly what Vita captured, then 5 fresh frames are sent to Gemini before the prompt fires
11. Vita analyzes and explicitly compares to any previous session findings
12. Vita asks **"Do you have any other questions, or are you ready to continue?"** — she only moves on after you confirm
13. Each step completes when Vita says "Analysis complete."
14. At the end, Vita delivers a wellness summary with severity tiers
15. Click **"✨ Enhanced Report (Vertex AI)"** to generate a structured clinical report via Gemini 1.5 Pro — saved to Firestore automatically

---

## Firestore Structure

```
users/
  {userId}/
    sessions/
      {sessionId}/
        user_id: string
        created_at: ISO timestamp
        analyses: { eyes, nails, tongue, teeth, skin }  ← written during scan
        summary: string                                  ← written on session end
        report: string                                   ← written after Vertex AI call
        report_generated_at: ISO timestamp
        snapshots: { eyes: gs://..., nails: gs://..., ... }
```

---

## Anti-Hallucination Design

1. **Camera warm-up** — 3s intro card before any gesture detection; Gemini has 10-15+ seconds of video context by first analysis
2. **Consent-gated description** — Vita only describes the user after explicit thumbs-up
3. **Forced first-sentence anchor** — each step prompt mandates `"Looking at your [body part] right now, I can see [specific color/feature]..."` before any generic clinical text
4. **5 fresh frames** sent immediately before each step prompt fires
5. **Frame confirmation thumbnail** — visible to the user so they can verify what Vita captured
6. **Previous session grounding** — when comparison context is injected, Vita must explicitly reference what changed vs. last time (prevents generic responses)

---

## Project Structure

```
├── main.py          # FastAPI backend + Gemini Live session handler + Vertex AI report endpoint
├── static/
│   └── index.html   # Single-page frontend (camera, audio, transcript, CV overlay, step wizard)
├── requirements.txt
├── Dockerfile
└── .env             # GEMINI_API_KEY, GOOGLE_CLOUD_PROJECT, GCS_BUCKET
```

---

## Setup & Run

**1. Create a `.env` file in the project root:**
```env
GEMINI_API_KEY=your_gemini_api_key_here
GOOGLE_CLOUD_PROJECT=your_gcp_project_id   # optional, for Vertex AI
GCS_BUCKET=vita-health-scans               # optional, for snapshot storage
```

**2. Install dependencies:**
```bash
pip install -r requirements.txt
# For GCP features:
pip install vertexai google-cloud-aiplatform google-cloud-firestore google-cloud-storage
```

**3. (One-time) Create GCS bucket:**
```bash
gcloud storage buckets create gs://vita-health-scans \
  --project=your_gcp_project_id --location=us-central1
```

**4. Run:**
```bash
python main.py
```

Open **http://localhost:8080**

> GCP services (Vertex AI, Firestore, Cloud Storage) are optional — the core scanning experience works with just a Gemini API key.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Serves the frontend |
| GET | `/api/history/{user_id}` | Retrieves past sessions from Firestore |
| POST | `/api/generate-report` | Vertex AI enhanced report + saves to Firestore |
| WS | `/ws/{user_id}` | Main Gemini Live session WebSocket |

### WebSocket message types (Server → Client)

| Type | Payload | Description |
|---|---|---|
| `session_ready` | `{ session_id }` | Sent before Gemini connects; frontend stores for report API |
| `previous_session` | `{ date, analyses, summary, report }` | Last session data for the banner UI |
| `vita_speaking` | `{ value: bool }` | Tracks Vita's audio state for auto-progression gating |
| `auto_capture` | `{ step, image_b64 }` | Frame thumbnail after "I'm Ready" |
| `turn_complete` | — | Vita's turn ended |
| `interrupted` | — | User interrupted; reset audio queue |
| `step_ready` | `{ step }` | Backend ready for next step prompt |
| `end_session` | — | Session complete |

---

## Hackathon Proof (GCP Logs)

Evidence of GCP service usage is visible in:

- **Cloud Storage** → GCS console → `vita-health-scans` bucket → `health_scans/` prefix — JPEG body-part snapshots per user per session
- **Firestore** → Firebase console → `users` collection → subcollections with timestamped session documents including analyses, summaries, and reports
- **Vertex AI** → GCP console → Vertex AI → Gemini API usage logs (one call per "Enhanced Report" click)
- **Cloud Logging** → All three services emit structured logs visible in GCP Cloud Logging

---

## Known Behaviours / Notes

- **No energy gate on mic**: Audio sent continuously so Gemini's VAD correctly detects turn end
- **Auto-continuation**: If Vita's turn ends mid-analysis (before "any other questions?"), frontend auto-sends "Please continue your analysis." after 3 seconds
- **Follow-up gate**: Continuation does NOT fire if Vita already asked the follow-up question — she's intentionally waiting
- **`vitaSpeaking` flag**: Set by `vita_speaking` WS messages; gates all auto-progression so Vita never interrupts herself
- **Auto-markReady silence-aware**: If Vita is still speaking at T+3s, the auto-ready timer polls every 200ms and fires as soon as she goes silent
- **markReady guard**: `if (stepIsScanning) return;` prevents double-firing from simultaneous button click + auto-timer
- **Glasses auto-polling**: During eye step, Vita checks for glasses every 3s until confirmed removed
- **Video mirroring**: `scaleX(-1)` on video element for natural mirror; canvas frames apply same flip so Gemini sees correct orientation
- **No zoom on scanning**: CSS `.scanning` class does not apply `scale()` — removed to preserve visual quality

---

## Disclaimer

Vita is for general wellness tracking only. It is **not a medical device** and does not provide diagnoses. Always consult a licensed healthcare professional for medical concerns.
