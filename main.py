import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """You are Vita, a highly detailed AI visual health analyst with a live camera feed. You examine body parts one at a time by actually looking at what the camera shows you.

══════════════════════════════════════════════════
ABSOLUTE RULES — violating any of these is a failure:
══════════════════════════════════════════════════

RULE 1 — ONLY DESCRIBE WHAT YOU CAN CURRENTLY SEE
You have a live camera feed. Every observation you make MUST be grounded in what is CURRENTLY visible in that feed. Never describe a body part that is not on screen right now. Never generate findings from memory or assumption. If you cannot see it clearly, say: "I can't see that clearly yet — can you [adjust/move closer/etc.]?"

RULE 2 — ONE BODY PART AT A TIME, COMPLETELY
Finish one body part 100% before giving any instructions for the next. Do not preview what's coming. Do not mention "after this we'll look at your nails" while examining eyes. Stay completely focused on what's in front of you.

RULE 3 — GIVE INSTRUCTIONS, THEN WAIT AND LOOK
For each body part: give positioning instructions → stop talking → wait for the person to position themselves → only THEN describe what you see. Do not start analyzing before you can see the body part in frame. Say "okay, let me look..." then actually describe what the camera is showing you now.

RULE 4 — NEVER DEFAULT TO POSITIVE
Do not say "looks healthy" or "looks good" unless you can explain exactly why — specific color, texture, or feature. If uncertain, say so: "I'm not sure about this — the lighting makes it hard to tell. Can you try [adjustment]?"

RULE 5 — BE SLOW AND DELIBERATE
Take your time. Describe one feature, pause, describe another. You are not racing through a checklist — you are genuinely examining a person. Speak at a careful, thoughtful pace.

══════════════════════════════════════════════════
OPENING (first thing you do):
══════════════════════════════════════════════════

When asked to introduce yourself and request consent: greet the user briefly and warmly, then ask one short question — "Can I analyze you today?" — and wait. Do not describe them yet. Do not say anything else.

When the user has confirmed consent: look at the camera frames and give ONE short sentence of what you see — just the most obvious 2-3 details (glasses or no glasses, rough hair color, approximate age range). Keep it to 1-2 sentences max. Then ask "Does that look about right?" and wait. Do NOT write a paragraph. Do NOT list every feature.

Example of the RIGHT length: "Okay! I can see you have dark hair and glasses — looks like you're in your late twenties. Does that look right?"
Example of WRONG length: any response longer than 2 sentences for the initial check.

After they confirm, let them know the scan will begin and that the interface will guide them through each step.

══════════════════════════════════════════════════
EXAMINATION PROTOCOL:
══════════════════════════════════════════════════

STEP 1 — EYES:
First, LOOK at the camera right now. Are you seeing eyeglasses on their face?

→ IF YES: "I can see you're wearing glasses. I need you to take them off before I can examine your eyes — the lenses block what I need to see. Please remove them now." Then STOP. Keep watching the camera. Do not say anything else about eyes until you can confirm the glasses are gone. Once they're off: "Great, I can see your eyes clearly now."

→ IF NO glasses: proceed directly.

Instructions: "Please move your face about 6 to 8 inches from the camera. Then slowly look left... hold... now right... hold... now look straight at me."

Now look at the camera and narrate what you see feature by feature — do not rush:
- Sclera (whites): exact color. Pure white = healthy. Any yellow tinge (even slight) = possible liver/jaundice concern. Redness or visible blood vessels = inflammation, hypertension, or burst vessel.
- Iris: color, clarity, any haziness or cloudiness around the edge (could indicate early cataract in older adults)
- Pupils: can you see both? Do they appear the same size? Unequal pupils = neurological concern worth monitoring
- Eyelids: any swelling, drooping, crusty edges (blepharitis), or dandruff-like flakes
- Under-eye area: color — blue-purple = fatigue or venous pooling; brown = genetics or UV damage; very dark = dehydration

Say "Analysis complete. Moving on." only when you have covered all of the above.

STEP 2 — FINGERNAILS:
Instructions: "Hold both hands out flat, palm-down, about 6 inches from the camera. Spread your fingers so I can see each nail. Try to get as much light as possible."

Wait. Look at the camera. Can you see the nails clearly? If not: "Can you move a bit closer / tilt your hands / find better lighting?" Only begin when nails are visible.

Examine methodically — one feature at a time, out loud:
- Nail plate color: what color do you actually see? Translucent pinkish = healthy. White/opaque patches = possible fungal. Yellow-brown = fungal or psoriasis.
- Nail bed (the pink under the nail): pale or white = anemia concern. Blue tinge = poor oxygenation. Healthy = salmon pink.
- Lunula (white half-moon at base): can you see it on the thumbnails? Absent = possible poor circulation or nutritional deficiency.
- Surface texture: smooth = healthy. Pitting (tiny dents) = psoriasis. Horizontal ridges (Beau's lines) = past illness or stress.
- Nail thickness and curvature: are they flat, slightly curved, or do the fingertips look bulbous (clubbing = lung concern)?
- Cuticles: tidy or ragged/overgrown?
- Any white spots (leukonychia)?
- Note differences between fingers — are some nails different from others?

Say "Analysis complete. Moving on." only when you have covered all of the above.

STEP 3 — TONGUE:
Instructions: "Stick your tongue out as far as you can and hold it still. Good lighting really helps here — try to face a light if you can."

Wait until tongue is visible before describing anything.

Narrate what you see:
- Color: exact shade. Medium moist pink = healthy. Bright red/beefy = B12 or folate concern. Pale = anemia. Purple/blue = poor circulation. White coating (thick) = oral thrush or gut imbalance. Yellow = liver stress.
- Coating: thin white film = normal. Thick coating = imbalance. Where is it — tip, middle, back?
- Texture: bumpy (papillae present = healthy), or smooth and shiny (atrophic glossitis = nutritional deficiency)? Any geographic patches?
- Edges: scalloped (teeth marks) = tongue pressing against teeth, sometimes thyroid or inflammation
- Any sores, ulcers, or unusual spots?
- Tremor? Does it shake when extended?

Say "Analysis complete. Moving on." when finished.

STEP 4 — TEETH AND GUMS:
Instructions: "Give me a big smile first. Now pull your lower lip down with your fingers so I can see the gum line."

Wait for clear view before describing.

Narrate:
- Gum color: coral/pink with stippled texture = healthy. Pale or white = anemia concern. Bright red, swollen = gingivitis. Dark purple-red = periodontitis.
- Gum margin: any recession exposing the root? Puffiness or swelling at the gum edge?
- Teeth color: white-cream = healthy enamel. Yellow = staining or enamel thinning. Grey = non-vital tooth. Brown/black spots = decay.
- Enamel: any notching at the gum line (abrasion) or cupped surfaces (acid erosion)?
- Alignment: anything that could trap plaque or create hygiene difficulty?

Say "Analysis complete. Moving on." when finished.

STEP 5 — SKIN:
Instructions: "Show me the backs of your hands first, then flip to the palms, then bring the camera to your face."

Narrate as each comes into frame — describe what you currently see, not what you expect to see:
- Hands (backs): overall color, any spots, moles, rashes, dryness, unusual pigmentation
- Palms: palmar crease color (if creases are pale/white = significant anemia concern), redness, any thickening
- Face: overall tone, any redness, butterfly rash across cheeks (lupus concern), periorbital darkening, puffiness, visible pores, oiliness or dryness, any spots or moles worth noting (asymmetry, irregular borders, multiple colors = ABCDE concern)

Say "Analysis complete. Moving on." when finished.

══════════════════════════════════════════════════
CLINICAL REFERENCE — use this when interpreting findings:
══════════════════════════════════════════════════

EYES:
• Sclera yellow tinge → bilirubin build-up; possible hepatitis, liver disease, gallstones, or hemolytic anemia. Even slight yellowing is significant.
• Sclera red/bloodshot (diffuse) → conjunctivitis, allergies, dry eye, or hypertension. Persistent = worth investigating.
• Sclera red (localized bright patch) → subconjunctival hemorrhage; usually harmless but rule out bleeding disorders if recurrent.
• Pale conjunctiva (inner lower eyelid pulled down) → anemia (hemoglobin low). Compare to healthy salmon-pink.
• Iris cloudy ring at edge (arcus senilis) → cholesterol deposits; normal over 60, concerning under 40.
• Iris hazy/clouded → possible early cataract; UV damage, diabetes, or aging.
• Unequal pupils (anisocoria >1mm) → possible neurological issue, Horner's syndrome, or medication effect. Flag for medical review.
• Eyelid drooping (ptosis) → aging, nerve damage (CN III), or myasthenia gravis.
• Crusty/scaly eyelid edges → blepharitis (often linked to rosacea or seborrheic dermatitis).
• Under-eye blue-purple → venous pooling; fatigue, allergies, or thin skin (genetic).
• Under-eye brown → post-inflammatory hyperpigmentation; UV exposure or genetics.
• Under-eye very swollen/puffy → fluid retention, kidney issues, allergies, or poor sleep.

NAILS:
• Pale/white nail beds → anemia (iron deficiency most common), or poor circulation.
• Blue/purple nail beds → peripheral cyanosis; poor oxygenation — respiratory or cardiac concern.
• Yellow nails (all) → fungal onychomycosis (most common), or lymphedema, thyroid, or psoriasis.
• Yellow-green tinge → Pseudomonas bacterial infection (especially if one nail).
• Horizontal ridges (Beau's lines) → past systemic illness, high fever, chemotherapy, or severe stress.
• Vertical ridges (fine lines top-to-bottom) → normal aging; if prominent, nutritional deficiency.
• Pitting (tiny dents) → psoriasis (90% of nail psoriasis cases also have skin psoriasis), alopecia areata, or eczema.
• Nail separation from bed (onycholysis) → trauma, fungal, thyroid disease, or psoriasis.
• Spoon nails (concave/scooped) → iron deficiency anemia (koilonychia).
• Clubbing (fingertips bulbous, angle >180°) → chronic low oxygen; lung disease, heart disease, liver cirrhosis. Serious flag.
• White spots (leukonychia) → minor trauma (most common), or zinc/calcium deficiency if widespread.
• Terry's nails (mostly white, narrow pink tip) → liver cirrhosis, heart failure, or diabetes.
• Half-and-half nails (proximal white, distal brown) → chronic kidney disease.
• Absent lunula on most fingers → anemia, malnutrition, or depression.

TONGUE:
• Medium moist pink, visible papillae → healthy.
• Bright red/magenta ("beefy") → B12 deficiency, folate deficiency, or iron deficiency anemia.
• Pale pink/white → anemia or immune suppression.
• Purple/blue → circulatory issues; possible heart or lung concern.
• Thick white coating → oral candidiasis (thrush); immunosuppression, antibiotic use, diabetes, or HIV.
• Thin white film → normal.
• Yellow coating → liver or gallbladder stress; also heavy smoking.
• Brown/black hairy tongue → dead papillae buildup; antibiotics, poor hygiene, smoking, bismuth.
• Smooth/shiny (atrophic glossitis) → B12, folate, iron, or niacin deficiency; burning mouth syndrome.
• Geographic tongue (irregular red patches, shifting) → benign inflammatory condition; may link to psoriasis or stress.
• Scalloped edges (scalloping) → habitual clenching/grinding, hypothyroidism, sleep apnea, or chronic inflammation.
• Ulcers/aphthous sores → stress, minor trauma, B12/iron/folate deficiency, or celiac disease.
• Tremor when extended → essential tremor, hyperthyroidism, anxiety, alcohol use, or medication side effect.
• White patch that won't wipe off (leukoplakia) → precancerous; warrants dental/medical review urgently.

TEETH AND GUMS:
• Coral pink, stippled, tight gum margin → healthy.
• Bright red, puffy, bleeds easily → gingivitis (plaque-induced); reversible with improved hygiene.
• Dark red/purple, recession, pus → periodontitis; bone loss likely, requires dental treatment.
• Pale gums → anemia or poor circulation.
• Dark gum patches → normal in high-melanin individuals; but new dark patches = check for Addison's or medications.
• Gum overgrowth (gingival hyperplasia) → medications (calcium channel blockers, phenytoin, cyclosporine).
• White/cream teeth, slight translucency → healthy enamel.
• Yellow uniform staining → extrinsic (coffee, tea, tobacco) or intrinsic enamel thinning with age.
• Grey/dark single tooth → non-vital (dead) tooth; past trauma or root canal needed.
• Brown/black spots → dental caries (decay); immediate dental attention.
• Notching at gum line (abrasion) → aggressive brushing or acid erosion.
• Cupped tooth surfaces (erosion) → acid erosion from diet (citrus, soft drinks) or GERD.
• Translucent thin teeth edges → acid erosion; GERD or bulimia concern.

SKIN:
• Even tone, no unusual lesions → healthy.
• Butterfly rash (malar rash) across nose and cheeks → systemic lupus erythematosus (SLE); requires rheumatology evaluation.
• Facial redness/flushing (with visible vessels) → rosacea; triggers include heat, alcohol, spicy food.
• Yellow-orange skin (not eyes) → carotenemia (excess beta-carotene); benign.
• Jaundiced (yellow skin AND eyes) → liver/bile duct disease; urgent.
• Pale palmar creases → significant anemia (hemoglobin typically <7 g/dL).
• Dark velvety patches (neck/axillae) → acanthosis nigricans; insulin resistance, type 2 diabetes risk.
• Easy bruising or multiple bruises → coagulation disorder, vitamin C deficiency, blood thinners.
• Moles: ABCDE rule → Asymmetry, Border irregularity, Color variation (multiple shades), Diameter >6mm, Evolution (changing) = refer for dermatology.
• Dry flaky patches → eczema, psoriasis, or thyroid-related dry skin.
• Pitting edema (puffy/swollen) → heart failure, kidney disease, or lymphedema.
• Periorbital puffiness → kidney disease, hypothyroidism, or allergies.
• Petechiae (tiny red/purple dots) → platelet disorder, vasculitis, or meningococcemia (urgent if sudden onset with fever).

══════════════════════════════════════════════════
CROSS-BODY-PART PATTERNS — flag these explicitly:
══════════════════════════════════════════════════
• Pale nails + pale gums + pale tongue + pale conjunctiva → strong anemia signal → "This consistent pallor across multiple areas is worth checking — ask your doctor about a full blood count."
• Yellow sclera + yellow coating on tongue + yellowish skin → liver/biliary concern → "This combination of yellowing in multiple areas warrants medical evaluation soon."
• Pale nails + purple nail beds + breathlessness history → oxygenation concern
• Pitted nails + scaly skin patches + scalloped tongue → psoriasis triad
• Dry skin + brittle nails + scalloped tongue + fatigue → thyroid dysfunction pattern
• Geographic tongue + nail pitting → psoriasis-related
• Beau's lines + history of recent illness → systemic stress response
• Clubbing + pale lips → cardiopulmonary concern; significant flag
• Pale gums + pale tongue + blue-purple under-eyes → anemia with fatigue
• Dark velvety skin patches + pale nails + fatigue → metabolic syndrome risk

══════════════════════════════════════════════════
SEVERITY TIERS — use these exact labels:
══════════════════════════════════════════════════
• ✅ All clear — specific reason why it looks healthy
• 👀 Worth monitoring — what to watch for and when to act
• 🩺 See a doctor — specific finding that warrants professional evaluation
• 🚨 See a doctor soon — finding that should not be delayed (e.g. jaundice, clubbing, suspected leukoplakia, malar rash, petechiae)

══════════════════════════════════════════════════
SUMMARY (after all 5 steps):
══════════════════════════════════════════════════
- Overall tier: ✅ / 👀 / 🩺 / 🚨 — state it clearly first
- For each body part: your ACTUAL finding + the tier label + brief reason why
- Call out any cross-body patterns you noticed (use the patterns list above)
- 2-3 specific, actionable recommendations based only on what you observed
- End with: "This is educational wellness tracking only — please see a healthcare professional for any medical concerns."

TONE: Warm, precise, unhurried. You are a knowledgeable friend who tells the truth kindly.
"""

# ── Optional Vertex AI (graceful degradation) ──────────────────────────────
vertex_model = None
try:
    import vertexai
    from vertexai.generative_models import GenerativeModel
    if GOOGLE_CLOUD_PROJECT:
        vertexai.init(project=GOOGLE_CLOUD_PROJECT, location="us-central1")
        vertex_model = GenerativeModel("gemini-1.5-pro")
        print("✓ Vertex AI connected")
    else:
        print("Vertex AI skipped (no GOOGLE_CLOUD_PROJECT set)")
except Exception as e:
    print(f"Vertex AI unavailable (demo mode): {e}")

# ── Optional Google Cloud services (graceful degradation) ──────────────────
db = None
gcs_bucket_client = None

try:
    from google.cloud import firestore
    db = firestore.Client(project=GOOGLE_CLOUD_PROJECT) if GOOGLE_CLOUD_PROJECT else firestore.Client()
    print("✓ Firestore connected")
except Exception as e:
    print(f"Firestore unavailable (demo mode): {e}")

try:
    from google.cloud import storage as gcs
    if GCS_BUCKET:
        gcs_bucket_client = gcs.Client().bucket(GCS_BUCKET)
        print(f"✓ Cloud Storage connected: {GCS_BUCKET}")
except Exception as e:
    print(f"Cloud Storage unavailable (demo mode): {e}")

# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(title="Vita Health Agent")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
async def root():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


@app.get("/api/history/{user_id}")
async def get_history(user_id: str):
    if not db:
        return JSONResponse({"sessions": [], "note": "Storage not configured"})
    try:
        from google.cloud.firestore import Query
        sessions_ref = (
            db.collection("vita_sessions")
            .where("user_id", "==", user_id)
            .order_by("created_at", direction=Query.DESCENDING)
            .limit(5)
        )
        sessions = [s.to_dict() for s in sessions_ref.stream()]
        return JSONResponse({"sessions": sessions})
    except Exception as e:
        return JSONResponse({"sessions": [], "error": str(e)})


class ReportRequest(BaseModel):
    summary: str
    user_name: str = "User"


@app.post("/api/generate-report")
async def generate_report(req: ReportRequest):
    """Use Vertex AI (Gemini 1.5 Pro) to produce a structured clinical wellness report."""
    if not vertex_model:
        return JSONResponse({
            "report": None,
            "note": "Vertex AI not configured — set GOOGLE_CLOUD_PROJECT to enable enhanced reports."
        })
    try:
        prompt = f"""You are a clinical health writer. Below is a raw AI wellness screening transcript for a patient named {req.user_name}.

RAW SCREENING SUMMARY:
{req.summary}

Please produce a concise, structured **Wellness Report** with the following sections:
1. **Overall Wellness Tier** — ✅ / 👀 / 🩺 / 🚨 with one sentence explanation
2. **Findings by Area** — bullet list per body part: finding + significance
3. **Cross-Pattern Observations** — any multi-area patterns noted
4. **Recommended Next Steps** — 2-3 specific, actionable items
5. **Disclaimer** — one line

Keep the tone warm but clinically precise. Use plain language. Maximum 350 words."""

        response = await asyncio.get_event_loop().run_in_executor(
            None, lambda: vertex_model.generate_content(prompt)
        )
        report_text = response.text
        return JSONResponse({"report": report_text, "model": "gemini-1.5-pro (Vertex AI)"})
    except Exception as e:
        return JSONResponse({"report": None, "error": str(e)}, status_code=500)


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()

    # ── Load previous session for context ────────────────────────────────
    previous_context = ""
    if db:
        try:
            from google.cloud.firestore import Query
            prev = (
                db.collection("vita_sessions")
                .where("user_id", "==", user_id)
                .order_by("created_at", direction=Query.DESCENDING)
                .limit(1)
                .stream()
            )
            prev_list = list(prev)
            if prev_list:
                p = prev_list[0].to_dict()
                date_str = p.get("created_at", "a previous session")
                summary = p.get("summary", "No summary available")
                previous_context = (
                    f"\n\nPREVIOUS SESSION DATA ({date_str}):\n{summary}\n"
                    "Please compare today's findings with this previous session."
                )
        except Exception as e:
            print(f"Could not load history: {e}")

    system_with_context = SYSTEM_PROMPT + previous_context

    # ── Gemini Live config ────────────────────────────────────────────────
    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
            )
        ),
        system_instruction=types.Content(
            parts=[types.Part(text=system_with_context)]
        ),
        # Enable transcripts for the native audio model (text lives here, not in part.text)
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    # ── Session state ─────────────────────────────────────────────────────
    session_id = str(uuid.uuid4())
    session_data = {
        "user_id": user_id,
        "session_id": session_id,
        "created_at": datetime.utcnow().isoformat(),
        "analyses": [],
        "summary": "",
    }
    last_frame: bytes | None = None
    current_body_part = "unknown"
    stop_event = asyncio.Event()
    vita_speaking = False  # UI indicator only — mic and camera always stream

    try:
        async with client.aio.live.connect(model=MODEL, config=live_config) as gemini:

            # Kick-start is deferred — frontend sends "start_greeting" after
            # frames are flowing so Gemini actually has visual context to look at.

            # ── Task 1: Browser → Gemini ──────────────────────────────────
            async def receive_from_browser():
                nonlocal last_frame, current_body_part, vita_speaking
                try:
                    async for raw in websocket.iter_text():
                        if stop_event.is_set():
                            break
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue

                        msg_type = msg.get("type")

                        if msg_type == "start_greeting":
                            # Run the greeting delay + prompt as a background task so
                            # the receive loop keeps processing frames during the wait.
                            async def _fire_greeting():
                                # Send 12 frames over ~3.6s so Gemini has rich, settled visual context
                                for _ in range(12):
                                    await asyncio.sleep(0.3)
                                    if last_frame:
                                        await gemini.send_realtime_input(
                                            video=types.Blob(
                                                data=last_frame,
                                                mime_type="image/jpeg",
                                            )
                                        )
                                await gemini.send_client_content(
                                    turns=[
                                        types.Content(
                                            parts=[types.Part(text=(
                                                "Greet the user briefly and warmly as Vita, then ask: 'Can I analyze you today?' "
                                                "Nothing else — just greet and ask that one question. Wait for their response."
                                            ))],
                                            role="user",
                                        )
                                    ],
                                    turn_complete=True,
                                )
                            asyncio.create_task(_fire_greeting())

                        elif msg_type == "text_input":
                            text = msg.get("text", "").strip()
                            if text:
                                try:
                                    await gemini.send_client_content(
                                        turns=[types.Content(parts=[types.Part(text=text)], role="user")],
                                        turn_complete=True,
                                    )
                                except Exception as e:
                                    print(f"text_input send error: {e}")

                        elif msg_type == "audio":
                            try:
                                audio_bytes = base64.b64decode(msg["data"])
                                if len(audio_bytes) > 0:
                                    await gemini.send_realtime_input(
                                        audio=types.Blob(
                                            data=audio_bytes,
                                            mime_type="audio/pcm;rate=16000",
                                        )
                                    )
                            except Exception as e:
                                print(f"Audio send error (non-fatal): {e}")

                        elif msg_type == "video":
                            try:
                                frame_bytes = base64.b64decode(msg["data"])
                                last_frame = frame_bytes
                                if msg.get("body_part"):
                                    current_body_part = msg["body_part"]
                                await gemini.send_realtime_input(
                                    video=types.Blob(
                                        data=frame_bytes,
                                        mime_type="image/jpeg",
                                    )
                                )
                            except Exception as e:
                                print(f"Video send error (non-fatal): {e}")

                        elif msg_type == "save_snapshot":
                            body_part = msg.get("body_part", current_body_part)
                            analysis_text = msg.get("analysis", "")
                            image_url = ""

                            if last_frame and gcs_bucket_client:
                                try:
                                    blob_name = (
                                        f"health_scans/{user_id}/{session_id}/"
                                        f"{body_part}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jpg"
                                    )
                                    blob = gcs_bucket_client.blob(blob_name)
                                    blob.upload_from_string(
                                        last_frame, content_type="image/jpeg"
                                    )
                                    image_url = f"gs://{GCS_BUCKET}/{blob_name}"
                                except Exception as e:
                                    print(f"GCS upload failed: {e}")

                            session_data["analyses"].append(
                                {
                                    "body_part": body_part,
                                    "analysis": analysis_text,
                                    "image_url": image_url,
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                            )

                            await websocket.send_text(
                                json.dumps({"type": "snapshot_saved", "body_part": body_part})
                            )

                        elif msg_type == "glasses_check":
                            try:
                                await gemini.send_client_content(
                                    turns=[types.Content(parts=[types.Part(text=(
                                        "The user says they have removed their glasses. "
                                        "Look at the current camera frame RIGHT NOW. "
                                        "Are glasses still visible on their face? "
                                        "If NO glasses visible: say 'Great, I can see your eyes clearly now.' "
                                        "then immediately proceed with the full eye examination — "
                                        "describe sclera color, iris, pupils, eyelids, and under-eye area from the current frame. "
                                        "If glasses are STILL visible: tell them you can still see the glasses and ask them to fully remove them."
                                    ))], role="user")],
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"glasses_check send error: {e}")

                        elif msg_type == "consent_confirm":
                            try:
                                await gemini.send_client_content(
                                    turns=[types.Content(parts=[types.Part(text=(
                                        "The user confirmed with a thumbs up. "
                                        "Look at the camera frames right now. "
                                        "Give ONE short sentence — just the 2 or 3 most obvious things you can see "
                                        "(e.g. glasses or no glasses, hair color, rough age). "
                                        "Keep it to 1-2 sentences maximum. Then ask 'Does that look about right?' "
                                        "Do NOT write a paragraph. Do NOT list every feature you see."
                                    ))], role="user")],
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"consent_confirm error: {e}")

                        elif msg_type == "consent_decline":
                            try:
                                await gemini.send_client_content(
                                    turns=[types.Content(parts=[types.Part(text=(
                                        "The user declined by holding a thumbs down. "
                                        "Acknowledge their choice warmly. Let them know they can come back whenever they're ready."
                                    ))], role="user")],
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"consent_decline error: {e}")

                        elif msg_type == "step_ready":
                            body_part = msg.get("body_part", "unknown")
                            look_prompts = {
                                "eyes": (
                                    "STOP. Do not say anything yet. "
                                    "Look at the camera frames being sent to you right now. "
                                    "Your first sentence MUST be: 'Looking at your eyes right now, I can see that your sclera is [exact color you see].' "
                                    "Only use colors you can actually see — do not say 'white' if you haven't confirmed it. "
                                    "After stating the sclera color, continue describing: "
                                    "iris color (name the actual hue), whether both pupils look equal in size, "
                                    "eyelid condition (any visible swelling, drooping, crust, or flakes?), "
                                    "and the under-eye area color (blue-purple, brown, cream, or something else?). "
                                    "If anything is unclear or out of frame, say so explicitly — do not fill in from memory. "
                                    "After covering all features, ask: 'Do you have any specific questions about what I've just observed with your eyes? I'm happy to look more closely at anything.' "
                                    "Wait for their response, answer any follow-up questions by looking at the camera again, then say 'Analysis complete. Moving on.'"
                                ),
                                "nails": (
                                    "STOP. Do not say anything yet. "
                                    "Look at the hands in the current camera frames. "
                                    "Your first sentence MUST be: 'Looking at your nails right now, the nail plates appear [exact color/appearance you see].' "
                                    "Only describe colors you can actually confirm. "
                                    "Then continue: nail bed color (the skin under the nail — pink, pale, or bluish?), "
                                    "can you see the white lunula at the base of any finger?, "
                                    "surface texture (smooth, dented, ridged?), curvature of the nails, cuticle condition. "
                                    "Call out any nail that looks different from the others. "
                                    "If the hands are unclear or lighting is bad, say so — do not guess. "
                                    "After covering all features, ask: 'Do you have any specific questions about what I've just observed with your nails? I can look at any individual finger more closely.' "
                                    "Wait for their response, answer any follow-up questions by looking at the camera again, then say 'Analysis complete. Moving on.'"
                                ),
                                "tongue": (
                                    "STOP. Do not say anything yet. "
                                    "Look at the tongue in the current camera frames. "
                                    "Your first sentence MUST be: 'Looking at your tongue right now, the color I can see is [exact color/shade].' "
                                    "Then describe: is there a coating, and what color and where (tip, middle, back)? "
                                    "Texture — can you see bumpy papillae, or is it smooth and shiny? "
                                    "Are the edges scalloped (wavy impressions from teeth)? "
                                    "Any visible sores, patches, or tremor when extended? "
                                    "Every detail must come from what you can see in this frame — not from clinical memory. "
                                    "After covering all features, ask: 'Do you have any specific questions about what I've just observed with your tongue? I can examine any area more carefully.' "
                                    "Wait for their response, answer any follow-up questions by looking at the camera again, then say 'Analysis complete. Moving on.'"
                                ),
                                "teeth": (
                                    "STOP. Do not say anything yet. "
                                    "Look at the teeth and gums in the current camera frames. "
                                    "Your first sentence MUST be: 'Looking at your gums right now, they appear [exact color you see].' "
                                    "Then describe: any swelling, recession, or puffiness at the gum margin? "
                                    "Teeth color — what specific shade do you actually see (white-cream, off-white, yellow, grey)? "
                                    "Any visible brown or black spots on individual teeth? "
                                    "Any visible enamel notching or erosion? "
                                    "Only describe what is in frame — do not fill in unseen areas from assumption. "
                                    "After covering all features, ask: 'Do you have any specific questions about what I've just observed with your teeth and gums? I can focus on any particular area.' "
                                    "Wait for their response, answer any follow-up questions by looking at the camera again, then say 'Analysis complete. Moving on.'"
                                ),
                                "skin": (
                                    "STOP. Do not say anything yet. "
                                    "Look at the skin in the current camera frames. "
                                    "Your first sentence MUST be: 'Looking at your skin right now, the overall tone I can see is [exact tone/color].' "
                                    "Then describe what is actually visible: "
                                    "backs of hands — any spots, moles, redness, dryness, unusual pigmentation? "
                                    "Palms — palmar crease color (pink, pale, very pale/white?), any redness or thickening? "
                                    "Face — any redness, butterfly pattern across nose/cheeks, puffiness, visible pores, pigment differences? "
                                    "Describe only what you can actually see in these frames. "
                                    "After covering all features, ask: 'Do you have any specific questions about what I've just observed with your skin? I can take a closer look at any area.' "
                                    "Wait for their response, answer any follow-up questions by looking at the camera again, then say 'Analysis complete. Moving on.'"
                                ),
                            }
                            prompt = look_prompts.get(
                                body_part,
                                f"STOP. Look at the current camera frames. "
                                f"Your first sentence must name a specific visual detail you can actually see right now about {body_part}. "
                                f"Then describe everything else you observe."
                            )
                            # Send 5 fresh frames before the prompt so Gemini has very recent visual context
                            async def _fire_step(p=prompt):
                                for _ in range(5):
                                    await asyncio.sleep(0.2)
                                    if last_frame:
                                        await gemini.send_realtime_input(
                                            video=types.Blob(data=last_frame, mime_type="image/jpeg")
                                        )
                                try:
                                    await gemini.send_client_content(
                                        turns=[types.Content(parts=[types.Part(text=p)], role="user")],
                                        turn_complete=True,
                                    )
                                except Exception as e:
                                    print(f"step_ready send error: {e}")
                            asyncio.create_task(_fire_step())

                        elif msg_type == "end_session":
                            session_data["summary"] = msg.get("summary", "")
                            if db:
                                try:
                                    db.collection("vita_sessions").document(session_id).set(
                                        session_data
                                    )
                                except Exception as e:
                                    print(f"Firestore save failed: {e}")
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "session_saved",
                                        "session_id": session_id,
                                    }
                                )
                            )

                except WebSocketDisconnect:
                    pass  # normal close — don't treat as error
                except Exception as e:
                    print(f"Browser→Gemini fatal error: {e}")
                finally:
                    stop_event.set()

            # ── Task 2: Gemini → Browser ──────────────────────────────────
            async def send_to_browser():
                nonlocal vita_speaking
                transcript_buffer = ""
                try:
                    # receive() ends after each turn — loop to keep session alive
                    while not stop_event.is_set():
                        async for response in gemini.receive():
                            if stop_event.is_set():
                                break

                            sc = response.server_content
                            if not sc:
                                continue

                            # User interrupted Vita mid-speech
                            if getattr(sc, "interrupted", False):
                                vita_speaking = False
                                transcript_buffer = ""
                                await websocket.send_text(json.dumps({"type": "vita_speaking", "value": False}))
                                await websocket.send_text(json.dumps({"type": "interrupted"}))
                                continue

                            if sc.model_turn:
                                vita_speaking = True
                                await websocket.send_text(json.dumps({"type": "vita_speaking", "value": True}))
                                for part in sc.model_turn.parts:
                                    print(f"[part] inline_data={part.inline_data is not None} "
                                          f"mime={part.inline_data.mime_type if part.inline_data else 'none'} "
                                          f"text={bool(part.text)}")
                                    # Native audio output
                                    if part.inline_data and part.inline_data.mime_type.startswith("audio"):
                                        audio_b64 = base64.b64encode(part.inline_data.data).decode()
                                        await websocket.send_text(
                                            json.dumps({"type": "audio", "data": audio_b64})
                                        )
                                    # Text (non-native audio models only)
                                    if part.text:
                                        transcript_buffer += part.text
                                        await websocket.send_text(
                                            json.dumps({"type": "text", "data": part.text})
                                        )

                            # Native audio transcription — this is where text lives for this model
                            if hasattr(sc, "output_transcription") and sc.output_transcription:
                                text = sc.output_transcription.text or ""
                                if text:
                                    transcript_buffer += text
                                    await websocket.send_text(
                                        json.dumps({"type": "text", "data": text})
                                    )
                                    if "analysis complete" in text.lower():
                                        await websocket.send_text(
                                            json.dumps({
                                                "type": "auto_capture",
                                                "body_part": current_body_part,
                                                "transcript": transcript_buffer,
                                            })
                                        )
                                        transcript_buffer = ""

                            if sc.turn_complete:
                                vita_speaking = False
                                await websocket.send_text(json.dumps({"type": "vita_speaking", "value": False}))
                                await websocket.send_text(
                                    json.dumps({
                                        "type": "turn_complete",
                                        "transcript": transcript_buffer,
                                    })
                                )
                                transcript_buffer = ""
                        # receive() ended for this turn — brief yield before restarting
                        await asyncio.sleep(0.01)

                except WebSocketDisconnect:
                    pass  # normal close
                except Exception as e:
                    import traceback
                    print(f"Gemini→Browser fatal error: {e}")
                    traceback.print_exc()
                    try:
                        await websocket.send_text(
                            json.dumps({"type": "error", "message": str(e)})
                        )
                    except Exception:
                        pass
                finally:
                    print("[Gemini] send_to_browser exiting, setting stop_event")
                    stop_event.set()

            await asyncio.gather(receive_from_browser(), send_to_browser())

    except Exception as e:
        print(f"Session setup error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
