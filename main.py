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

Greet the user warmly and say: "Give me just a moment to take a good look at you..." — then actually PAUSE and look at the camera frames before saying anything else.

Now look at the camera and describe EXACTLY what you see right now:
- Hair: exact color you see (not assumed), texture if visible, length
- Approximate age based on visible features (be specific: "mid-twenties", "early thirties", etc.)
- Skin tone: describe the actual color and undertone you observe
- Face shape or notable features visible
- Whether they are wearing glasses RIGHT NOW
- Any other immediately visible details (facial hair, jewelry, clothing color)

After your description, ask: "Does that sound right? I want to make sure I'm seeing you accurately." Wait for their confirmation before proceeding.

Then let them know: "Great — the interface will guide you through each step. Just follow the instructions on screen and click 'I'm Ready' when you're in position. I'll examine each area carefully when you tell me you're set."

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
                                                "Multiple live camera frames have been streaming to you for the last several seconds. "
                                                "Before you say anything descriptive, take a moment to look at all those frames carefully. "
                                                "Greet the user warmly as Vita and say 'Give me just a moment to take a good look at you...' "
                                                "Then PAUSE, review the visual context, and only after that describe what you see. "
                                                "Base your description ONLY on what is consistently visible across multiple frames — "
                                                "do NOT guess or answer from memory. "
                                                "Specifically examine carefully: "
                                                "1) GLASSES: Look at their face across ALL frames. Are there glasses frames, lenses, or nose pads visible? "
                                                "Check every frame — glasses are easy to miss at first. If yes, say so. Do NOT default to 'no glasses' unless you are certain across multiple frames. "
                                                "2) Hair: actual color and length you observe (short/medium/long). "
                                                "3) Age: your best estimate from visible features. "
                                                "4) Skin tone: what you actually see. "
                                                "5) Any other clearly visible details (facial hair, earrings, clothing color). "
                                                "If you are unsure about any attribute, say so honestly. "
                                                "Ask: 'Does that sound right?' and wait for confirmation. "
                                                "Do NOT begin any body part examination yet."
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

                        elif msg_type == "step_ready":
                            body_part = msg.get("body_part", "unknown")
                            look_prompts = {
                                "eyes": (
                                    "The user has just positioned their face in front of the camera for the eye examination. "
                                    "Fresh camera frames are being sent RIGHT NOW. Look at the current frame immediately. "
                                    "Do NOT speak from memory or assumption. "
                                    "Describe exactly what you see: sclera color (pure white, yellowish, or red?), "
                                    "iris color and clarity, pupil size and whether both look equal, "
                                    "eyelid condition (any swelling, drooping, or crusting?), "
                                    "and the color of the under-eye area (blue-purple, brown, or normal?). "
                                    "Be specific — name the actual colors and features visible in this frame right now."
                                ),
                                "nails": (
                                    "The user has just held their hands up to the camera for nail examination. "
                                    "Fresh camera frames are being sent RIGHT NOW. Look at the current frame immediately. "
                                    "Do NOT speak from memory. "
                                    "Describe what you actually see: nail plate color (translucent pink, white patches, yellow-brown?), "
                                    "nail bed color (pink, pale, bluish?), whether you can see the white lunula at the base, "
                                    "surface texture (smooth, pitted, ridged?), curvature, and cuticle condition. "
                                    "Go finger by finger if you can see them clearly."
                                ),
                                "tongue": (
                                    "The user has just stuck their tongue out in front of the camera. "
                                    "Fresh camera frames are being sent RIGHT NOW. Look at the current frame immediately. "
                                    "Do NOT describe what a tongue typically looks like — describe this person's tongue. "
                                    "What exact color do you see (pink, red, pale, purple, white-coated, yellow-coated)? "
                                    "Is there a coating, and where (tip, middle, back)? "
                                    "What does the texture look like (bumpy papillae, smooth and shiny)? "
                                    "Any scalloped edges, sores, or tremor? Cite the specific colors you observe right now."
                                ),
                                "teeth": (
                                    "The user is showing their teeth and gums to the camera right now. "
                                    "Fresh camera frames are being sent. Look at the current frame immediately. "
                                    "Describe what you actually see: gum color (coral-pink, pale, bright red, dark purple-red?), "
                                    "any swelling or recession at the gum margin, "
                                    "teeth color (white-cream, yellow, grey, brown spots?), "
                                    "and any enamel issues visible. Be specific about what is currently in the frame."
                                ),
                                "skin": (
                                    "The user is showing their skin to the camera right now. "
                                    "Fresh camera frames are being sent. Look at the current frame immediately. "
                                    "Describe what you actually see on their hands and face: "
                                    "overall skin tone and undertone, any visible spots, moles, redness, dryness, "
                                    "unusual pigmentation, or texture differences. "
                                    "For the face: any butterfly rash, puffiness, periorbital darkening, oiliness? "
                                    "Describe only what is currently visible — do not assume."
                                ),
                            }
                            prompt = look_prompts.get(
                                body_part,
                                f"The user is ready for {body_part} examination. Fresh camera frames are being sent right now. "
                                f"Look at the current frame and describe exactly what you see."
                            )
                            try:
                                await gemini.send_client_content(
                                    turns=[types.Content(parts=[types.Part(text=prompt)], role="user")],
                                    turn_complete=True,
                                )
                            except Exception as e:
                                print(f"step_ready send error: {e}")

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
