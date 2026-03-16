# Vita — AI Visual Health Screening Agent

> **Hackathon Demo** · Built with Gemini Live API + Google Cloud

Vita is a real-time AI health screening assistant that guides users through a visual wellness check-in via their webcam. Using the **Gemini 2.5 Flash Native Audio** model, Vita speaks, listens, and analyzes what she sees through the live camera feed.

---

## Demo Flow

1. Open the app and enter your name
2. An **intro card** shows while the camera warms up (3 seconds)
3. Once ready, a **thumbs-up card** appears — hold 👍 for ~1 second to trigger Vita
4. Vita greets you and asks **"Can I analyze you today?"**
5. Show 👍 (yes) or 👎 (no) using the **consent gesture card** with dual progress rings
6. After consent, Vita gives a **brief 1-2 sentence check** ("I can see dark hair and glasses — late twenties?") and asks you to confirm
7. You confirm verbally or via text → Vita starts the 5-step scan wizard
8. If glasses are detected during the **eye step**, Vita stops and auto-polls every 3 seconds until she confirms they're removed from frame
9. For each step, tap **"I'm Ready"** — 5 fresh frames are sent to Gemini right before the prompt fires, plus a forced first-sentence anchor ("Looking at your sclera right now, I can see...")
10. Each step auto-completes when Vita says "analysis complete"
11. A **pull-out transcript drawer** in the header shows full conversation history
12. At the end, Vita delivers a wellness summary with **cross-body-part pattern recognition** and **severity tiers** (✅ / 👀 / 🩺 / 🚨)

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

Side storage (optional):
  Firestore  ── session history & summaries
  Cloud Storage ── body-part snapshot images
```

**Key technologies:**
| Technology | Role |
|---|---|
| Gemini Live API | Real-time bidirectional multimodal streaming |
| Gemini 2.5 Flash Native Audio | Voice + vision model with VAD interruption support |
| Google GenAI SDK (`google-genai`) | Python client for Live API |
| MediaPipe Tasks Vision | Client-side face + hand landmark detection for UI highlights and gesture input |
| Cloud Firestore | Session history persistence (optional) |
| Cloud Storage (GCS) | Snapshot image storage (optional) |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY=your-gemini-api-key

# Optional — enables session history and image storage
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GCS_BUCKET=your-bucket-name
```

Get a Gemini API key at [aistudio.google.com](https://aistudio.google.com).

> The app runs in **demo mode** without GCP credentials — Gemini still works fully, sessions just aren't persisted.

### 3. Run locally

```bash
python main.py
```

Open **http://localhost:8080**

---

## Deploy to Cloud Run

```bash
gcloud run deploy vita \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=your-key
```

---

## Project Structure

```
├── main.py          # FastAPI backend + Gemini Live session handler
├── static/
│   └── index.html   # Single-page frontend (camera, audio, transcript, CV overlay, step wizard)
├── requirements.txt
├── Dockerfile
└── .env
```

---

## How the Live API Integration Works

The backend maintains a **persistent bidirectional stream** with Gemini for each user session:

- **Audio in**: Browser captures 16kHz PCM from mic → sent continuously (no energy gate, so Gemini's VAD can detect end-of-speech) → base64 → WebSocket → `send_realtime_input(audio=...)`
- **Video in**: Browser captures JPEG frames at ~3fps (333ms) idle, ~4fps (250ms) during active scan → `send_realtime_input(video=...)`
- **Audio out**: Gemini returns 24kHz PCM chunks → browser queues and plays sequentially via Web Audio API; `nextPlayTime` reset to 0 on interruption
- **Transcript**: `output_audio_transcription` config enables real-time text alongside speech
- **Interruption**: User speech triggers Gemini's VAD; `sc.interrupted` signals the UI to reset audio queue. Because audio (including silence) is sent continuously, Gemini's VAD correctly detects turn end and resumes after interruption
- **Text input**: Typed messages forwarded as `send_client_content(turn_complete=True)` — full dual input support

The `receive()` iterator ends after each turn; the backend wraps it in a `while` loop with a `0.01s` yield to keep the session alive.

### Frame resolution
- **Idle / greeting phase**: 640×360 @ 80% JPEG quality
- **Active body part scan**: 1280×720 @ 92% JPEG quality

### Video mirroring
The `<video>` element has CSS `transform: scaleX(-1)` for a natural mirror view. Canvas frame captures apply `ctx.scale(-1, 1)` so frames sent to Gemini match what the user sees. MediaPipe landmark x-coordinates are mirrored (`canvasX = width - landmark.x * width`).

---

## Anti-Hallucination Design

Gemini can describe a person from memory rather than from the current frame. Vita addresses this with multiple layers:

### 1. Camera warm-up + intro card
An intro card shows for ~3 seconds after WebSocket connects before the thumbs-up card appears. This lets the camera auto-expose and settle before any gesture is detected.

### 2. Consent-gated description (two-step thumbs flow)
- First thumbs-up → Vita greets and asks "Can I analyze you today?" — no description yet
- 12 frames are sent over 3.6 seconds before the greeting prompt fires
- User shows 👍 or 👎 on the consent card → only after consent does Vita attempt a visual description
- By this point, Gemini has been watching for 10-15+ seconds — enough context for accurate recognition
- The description is intentionally brief (1-2 sentences) to reduce hallucination surface

### 3. Forced first-sentence anchor on each step
When the user taps "I'm Ready", the backend:
1. Sends 5 fresh frames over 1 second before the text prompt
2. Fires a prompt that mandates a specific opening: `"Your first sentence MUST be: 'Looking at your [body part] right now, I can see that [specific color/feature]...'"` — this forces visual grounding before any generic clinical text

### 4. Glasses auto-polling
During the eye step, Vita checks for glasses every 3 seconds via a `glasses_check` message. Transcript keyword detection auto-dismisses the banner when glasses are confirmed gone.

---

## Greeting & Consent Flow (detailed)

```
ws.onopen
  └─ intro card shown (2.5s camera warm-up)
       └─ intro card fades → thumbs-up card appears
            └─ user holds 👍 for 900ms
                 └─ triggerGreetingScan()
                      └─ sends start_greeting to backend
                           └─ _fire_greeting():
                                ├─ sends 12 frames over 3.6s
                                └─ sends prompt: "greet + ask 'Can I analyze you today?'"
                                     └─ turn_complete → consent card shown (👍/👎 rings)
                                          ├─ user holds 👍 → consent_confirm sent
                                          │    └─ Gemini gives brief 1-2 sentence description
                                          │         └─ turn_complete → "Begin Examination" button
                                          └─ user holds 👎 → consent_decline sent
                                               └─ Gemini acknowledges gracefully
```

---

## UI Components

### Intro card
Shown on app load during camera warm-up. Status dot turns green when camera is ready, then fades into the thumbs-up card.

### Consent gesture card
Appears after Vita asks for consent. Two SVG progress rings (green 👍, red 👎) fill as the gesture is held. Detecting both independently with `isThumbsUp()` and `isThumbsDown()` (MediaPipe hand landmarks).

### Heart loading animation
Replaces typing dots during Gemini's "thinking" phase. An SVG heart fills from bottom to top using `clip-path` + CSS `scaleY` animation on a gradient fill rectangle. Shown in the greeting bubble and scanning state; hides when text starts flowing.

### Transcript drawer
A 390px panel that slides in from the right edge of the screen. Toggle via the "Transcript" button in the header. Shows completed Vita turns and user messages as chat bubbles. Displays an unread badge when new messages arrive while closed. All state resets on session end.

### Step wizard
Two-column layout (camera left, wizard right). State machine:
```
wizardPhase: 'greeting' → 'steps' → 'summary'
greetingSubPhase: 'consent' → 'description'
currentStepIdx: -1 → 0..4
stepIsScanning: false / true
```

---

## CV Overlay & Landmark Highlights

When Vita begins examining a body part:

1. **Scan overlay** — dashed detection bounding box, animated scan line, corner brackets
2. **Landmark highlights** (MediaPipe):
   - **Eyes** → green glowing ellipses around each eye contour
   - **Tongue / Teeth** → gold rounded box around mouth region
   - **Skin** → blue glowing face oval silhouette
   - **Nails** → green ellipses around each fingertip relative to knuckle
3. **Video zoom** — subtle `scale(1.04)` CSS transition on the video element

---

## Clinical Reference & Pattern Recognition

The system prompt includes baked-in clinical reference covering:

- **Eyes**: sclera color, pupil equality, conjunctiva pallor, iris arcus, under-eye color
- **Nails**: color, pitting, clubbing, koilonychia, Beau's lines, lunula, leukonychia
- **Tongue**: coating color/location, glossitis, geographic tongue, scalloping, tremor
- **Teeth & Gums**: gum color, recession, gingivitis/periodontitis, enamel erosion, caries
- **Skin**: pallor, jaundice, malar rash, acanthosis nigricans, ABCDE moles, petechiae

**Cross-body-part patterns** flagged explicitly:
- Pale nails + pale gums + pale tongue + pale conjunctiva → anemia signal
- Yellow sclera + yellow tongue coating + yellowish skin → liver/biliary concern
- Nail pitting + skin plaques → psoriasis triad
- Dry skin + brittle nails + scalloped tongue → thyroid pattern

**Severity tiers**: ✅ All clear | 👀 Worth monitoring | 🩺 See a doctor | 🚨 See a doctor soon

---

## Known Behaviours / Notes

- **No energy gate on mic**: Removed. The original gate (`energy < 0.000001`) caused Gemini's VAD to hang after interruptions because it never received silence frames to detect turn end. Audio is now sent continuously; echo cancellation (enabled on mic constraints) handles Vita's own voice.
- **Interrupt behavior**: After an interrupted event, Gemini re-enters listen mode. Because mic audio (including silence) always flows, VAD correctly detects when the user finishes speaking and generates a new response automatically.
- **Audio context cleanup**: All Web Audio nodes are properly closed and nulled on session end.
- **Session state reset**: `endSession()` resets all state including consent phase, greeting sub-phase, drawer history, and CV overlay.

---

## Disclaimer

Vita is for general wellness tracking only. It is **not a medical device** and does not provide diagnoses. Always consult a licensed healthcare professional for medical concerns.
