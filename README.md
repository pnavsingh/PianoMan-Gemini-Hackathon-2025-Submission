# Vita — AI Visual Health Screening Agent

> **Hackathon Demo** · Built with Gemini Live API + Google Cloud

Vita is a real-time AI health screening assistant that guides users through a visual wellness check-in via their webcam. Using the **Gemini 2.5 Flash Native Audio** model, Vita speaks to you (or responds to text), analyzes what she sees through the live camera feed, and tracks changes across sessions.

---

## Demo Flow

1. Open the app and enter your name
2. Hold a **thumbs-up** to trigger Vita's greeting (or wait 15s for auto-start)
3. Vita **looks at the current camera frame** and describes what she sees (hair color, age, skin tone, glasses) — you verify before anything starts
4. If you're wearing glasses, Vita **stops and auto-polls** every 3 seconds until she confirms they're removed from frame — no button tap needed
5. Vita walks you through **5 visual checks one at a time** via a step wizard: Eyes → Nails → Tongue → Teeth & Gums → Skin
6. For each step, tap **"I'm Ready"** — Vita injects an explicit "look NOW" prompt so she examines the live frame rather than speaking from memory
7. The UI shows a **CV-style scanning overlay** with real MediaPipe face/hand landmark highlights (green ellipses on eyes, gold box on mouth, blue face oval for skin, green ellipses on fingernails)
8. Each step auto-completes when Vita says "analysis complete" — no manual advancement needed
9. At the end she delivers a detailed wellness summary with **cross-body-part pattern recognition** and **severity tiers** (✅ / 👀 / 🩺 / 🚨)
10. Return users get a comparison to their previous session

---

## Architecture

```
Browser (WebRTC mic + webcam)
        │  WebSocket (audio PCM 16kHz + JPEG frames 640x360 / 1280x720)
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
  MediaPipe HandLandmarker ── finger/knuckle landmarks for nail highlights + thumbs-up detection

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

- **Audio in**: Browser captures 16kHz PCM from mic → energy-gated → base64 → WebSocket → `send_realtime_input(audio=...)`
- **Video in**: Browser captures JPEG frames at 3fps (333ms interval) idle, 4fps (250ms) during active scan → `send_realtime_input(video=...)`
- **Audio out**: Gemini returns 24kHz PCM chunks → browser queues and plays sequentially via Web Audio API; `nextPlayTime` is reset to 0 on interruption so the next response plays immediately
- **Transcript**: `output_audio_transcription` config enables real-time text alongside speech
- **Interruption**: User speaking mid-response triggers Gemini's VAD; `sc.interrupted` signals the UI to reset the audio queue and transcript buffer
- **Text input**: Typed messages forwarded as `send_client_content(turn_complete=True)` — full dual input support

The `receive()` iterator ends after each turn; the backend wraps it in a `while` loop with a `0.01s` yield to keep the session alive without spinning the CPU.

### Frame resolution
- **Idle / greeting phase**: 640×360 @ 80% JPEG quality
- **Active body part scan**: 1280×720 @ 92% JPEG quality — switched automatically when `cvScanning` is true

### Video mirroring
The `<video>` element has CSS `transform: scaleX(-1)` for a natural mirror view. Canvas frame captures apply `ctx.scale(-1, 1)` so the frames sent to Gemini match what the user sees. MediaPipe landmark x-coordinates are mirrored (`canvasX = width - landmark.x * width`) for the same reason.

---

## Anti-Hallucination Design

A core challenge with the Live API is that Gemini may describe a person from memory/context rather than from the current frame. Vita addresses this with a three-layer approach:

### 1. Deferred greeting (thumbs-up trigger)
The greeting is not fired on WebSocket connect. Instead, frames stream silently until the user holds a thumbs-up for 900ms (SVG progress ring confirms hold). This guarantees multiple frames are in the model's buffer before Vita speaks. A 15-second fallback fires if the user doesn't gesture.

### 2. Explicit `step_ready` turns
When the user taps "I'm Ready" for a step, the backend sends an explicit `send_client_content` turn with per-body-part instructions: `"Look at the current frame RIGHT NOW. Do NOT speak from memory."` Each prompt specifies exactly what to observe (sclera color, pupil equality, nail color/texture, etc.).

### 3. Glasses auto-polling
During the eye step, Vita checks for glasses every 3 seconds via a `glasses_check` message → backend injects a "look at the face now, are glasses still present?" turn. Transcript keyword detection (sclera/iris/pupil phrases = glasses gone; "please remove" = still present) auto-dismisses the banner without any user button tap.

---

## CV Overlay & Landmark Highlights

When Vita begins examining a body part, the UI activates:

1. **Scan overlay** — dashed detection bounding box, animated horizontal scan line, frame counter, pulsing confidence bar
2. **Landmark highlights** — drawn on top using real MediaPipe detections:
   - **Eyes** → green glowing ellipses around each eye contour (landmarks 33–246, 362–398)
   - **Tongue / Teeth** → gold rounded box around mouth (landmarks 61–375)
   - **Skin** → blue glowing face oval silhouette (36-point face oval)
   - **Nails** → green ellipses around each fingertip relative to knuckle position
3. **Video zoom** — subtle `scale(1.04)` on the video element with a smooth CSS transition

Hand detection always runs (needed for thumbs-up detection). MediaPipe loads from CDN (`@mediapipe/tasks-vision@0.10.3`) as an ES module. If it fails, the scan overlay still works — landmark highlights degrade gracefully.

---

## Step Wizard UI

The frontend uses a **two-column layout** (camera panel left, wizard panel right) and a state machine:

```
wizardPhase: 'greeting' → 'steps' → 'summary'
currentStepIdx: -1 → 0..4
stepIsScanning: false / true
```

**Steps**: Eyes → Nails → Tongue → Teeth & Gums → Skin

Each step card shows:
- Positioning instructions with tips
- "I'm Ready" button → sends `step_ready` + activates CV overlay
- Auto-completion when Vita says "analysis complete" (detected via transcript, 2.5s debounce)
- Result card appended to results area on completion

---

## Clinical Reference & Pattern Recognition

The system prompt includes baked-in clinical reference tables covering:

- **Eyes**: sclera color, pupil equality, conjunctiva pallor, iris arcus
- **Nails**: color bands, pitting, clubbing, koilonychia, Mees'/Muehrcke's/Lindsay's lines
- **Tongue**: coating color, surface texture, fissuring, geographic tongue, glossitis
- **Teeth & Gums**: gum color, recession, bleeding, enamel erosion, bruxism wear
- **Skin**: pallor distribution, jaundice, cyanosis, rashes, mole irregularity

**Cross-body-part patterns** — Vita flags these explicitly:
- Pale nails + pale gums + pale tongue + pale conjunctiva → anemia signal
- Yellow sclera + yellow skin tone + dark urine mention → liver/bilirubin flag
- Nail pitting + skin plaques + joint mention → psoriasis triad
- Dry skin + brittle nails + puffy face + slow speech → thyroid pattern
- …and more

**Severity tiers**: ✅ All clear | 👀 Worth monitoring | 🩺 See a doctor | 🚨 See a doctor soon

---

## Dual Input (Voice + Text)

For public or quiet environments, Vita supports fully text-based interaction:

- **Mic toggle** button mutes/unmutes the microphone (audio capture continues, energy gate blocks transmission)
- **Text input bar** at the bottom — type a message and press Enter or Send
- Text is forwarded as `send_client_content` to Gemini and displayed as a user chat bubble
- Vita's spoken response is always transcribed and shown in the chat panel regardless of input mode

---

## Session Behavior & Prompt Design

### Opening calibration
Vita's greeting prompt explicitly asks her to check for glasses ("Do NOT default to 'no glasses'"), hair color and length, apparent age, and skin tone — and asks the user to confirm before any examination begins.

### Glasses gate
Before the eye exam, if glasses are detected Vita hard-stops. The UI shows a "Remove glasses" banner. Vita auto-polls every 3 seconds until she confirms glasses are gone from the live frame, then continues automatically.

### Examination pacing (ABSOLUTE RULES in system prompt)
- Only describes what is **currently visible** in the frame — never pre-generates findings
- Completes one body part **100% before** mentioning the next
- Gives positioning instructions → stops talking → waits → then narrates
- Must explain **why** something looks healthy (specific color/texture/feature) — never defaults to vague positives
- If unclear: asks for adjustment rather than guessing

---

## Known Behaviours / Notes

- **No `TURN_INCLUDES_ALL_INPUT`**: Removed. It caused Gemini to race through the protocol from memory rather than waiting to actually see each body part. Explicit `step_ready` turns + deferred greeting replace this.
- **Audio context cleanup**: All Web Audio nodes (`AudioContext`, `ScriptProcessor`) are properly closed and nulled on session end so reconnecting doesn't create duplicate pipelines.
- **Session state reset**: On `endSession()`, all state is fully reset including `vitaBubble`, `vitaBuffer`, `currentBodyPart`, step wizard state, checklist icons, and the CV overlay.
- **Frame buffer race condition**: Fixed by moving from a timed delay (previously 500ms → 1500ms → 3500ms, all insufficient) to gesture-gated greeting, ensuring frames are provably buffered before Gemini speaks.

---

## Disclaimer

Vita is for general wellness tracking only. It is **not a medical device** and does not provide diagnoses. Always consult a licensed healthcare professional for medical concerns.
