# Cedar Clinic voice appointment demo

A browser call and live transcript, a schedule of fictional doctors and times, and a booking list that refreshes as the call changes it. Pipecat runs the voice conversation, ElevenLabs handles speech in both directions, and Google Gemini handles conversation and tool selection. The dashboard is plain JavaScript and CSS. Everything runs locally except calls to the model and speech APIs.

## Run it locally

Use Python 3.11 through 3.14 with `pip` available in a virtual environment, and a current Node.js version with npm. The install commands fetch packages, including native dependencies for WebRTC and the frontend bundler. On Linux, use your usual Python setup with `venv` and `pip` support.

From this folder, create `.env` from `.env.example` and put your ElevenLabs and Google API keys in it. `GOOGLE_MODEL` defaults to `gemini-3.5-flash-lite`, a model with a documented [free tier](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite). Set another tool-capable Gemini model if needed for your account. Use fictional numbers and data in the call.

In terminal one:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 7860
```

In terminal two:

```sh
cd web
npm install
npm run dev
```

Open the local URL printed by Vite and allow microphone access. For a single-server build, run `npm run build` from `web` then restart Uvicorn and open `http://127.0.0.1:7860`.

## Start with the three files you need to explain

1. **`appointments.py`** is the business logic. Read `book` first. It checks the confirmation flag and phone format, looks up the slot and updates the shared appointment store. A lock makes validation and booking one operation. The same caller rebooking the same slot gets the same confirmation. Only the last four digits are displayed in the dashboard. The data resets when the server restarts.
2. **`voice.py`** is the AI integration. The tool schemas tell Gemini what functions are available. `register_tools` maps those names to Python functions. `run_call` wires the browser audio into ElevenLabs transcription, passes the text to Gemini, and sends the spoken response back through ElevenLabs. Each call gets its own conversation context. The test's spoken confirmation rule is in the agent instructions and the mutation tools also require a confirmation flag. The flag is reported by the model. A spoken number and a confirmation flag are insufficient to verify identity in a real clinic.
3. **`server.py` and `web/src.js`** connect the pieces. The browser negotiates WebRTC using `/api/offer`, listens for transcript events and polls `/api/schedule`. The schedule and actual booking callbacks use the same store. The appointment list changes after the backend changes state.

## Verify and record the demo

`python -m unittest -v` checks the appointment logic without any provider keys. When the app is running, do this in the browser before recording:

1. Start a call and wait for the greeting. Ask for Dr. Rao's next available slot.
2. Pick one of the times and provide the fictional number `+1 202 555 0147`. Wait for readback and confirm. Check that the slot is marked booked and the appointment appears in the dashboard.
3. Ask to cancel using the same number and confirm after readback. Check that the appointment disappears and the slot reopens.

Record the booking portion for the assignment. Keep the video under three minutes. Write the pipeline description in your own words. Explain which parts AI helped implement and which parts you personally checked. Review the brief's submission instructions before sharing the repo or video.

## Prepare for the next round

The brief describes round one only. Ask the recruiter what format round two takes and whether it includes live coding or DSA. First, make sure you can trace a call from the microphone to the confirmation. Be ready to explain what happens if two people pick the same slot, why appointments use the tool result rather than generated text, and what needs to change if the app runs across multiple servers.
