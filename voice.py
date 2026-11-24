"""Connect the browser, speech services, model and the appointment functions."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner


PHONE = {"type": "string", "description": "Phone number spoken and confirmed in this call."}
CONFIRMED = {"type": "boolean", "description": "True only after readback and affirmative caller confirmation."}
TOOLS = ToolsSchema(standard_tools=[
    FunctionSchema(
        name="check_doctor_availability",
        description="Look up available appointment slots. Use returned slot IDs.",
        properties={"doctor": {"type": "string", "description": "Doctor name or surname."},
                    "date": {"type": "string", "description": "Optional date in YYYY-MM-DD."}},
        required=[],
    ),
    FunctionSchema(
        name="book_appointment",
        description="Book the selected free slot after confirming the caller's phone number aloud.",
        properties={"slot_id": {"type": "string", "description": "Slot ID returned by availability."},
                    "phone": PHONE, "confirmed": CONFIRMED},
        required=["slot_id", "phone", "confirmed"],
    ),
    FunctionSchema(
        name="cancel_appointment",
        description="Cancel the active appointment for the caller's number after reading it back and getting confirmation.",
        properties={"phone": PHONE, "confirmed": CONFIRMED},
        required=["phone", "confirmed"],
    ),
])


def register_tools(llm, appointments):
    async def availability(params):
        args = params.arguments
        await params.result_callback(appointments.available(args.get("doctor", ""), args.get("date", "")))

    async def book(params):
        args = params.arguments
        result = appointments.book(args.get("slot_id"), args.get("phone"), args.get("confirmed"))
        await params.result_callback(result)

    async def cancel(params):
        args = params.arguments
        await params.result_callback(appointments.cancel(args.get("phone"), args.get("confirmed")))

    llm.register_function("check_doctor_availability", availability)
    llm.register_function("book_appointment", book)
    llm.register_function("cancel_appointment", cancel)


async def run_call(connection, appointments):
    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    speech_key = os.environ["ELEVENLABS_API_KEY"]
    stt = ElevenLabsRealtimeSTTService(api_key=speech_key)
    tts = ElevenLabsTTSService(
        api_key=speech_key,
        settings=ElevenLabsTTSService.Settings(
            voice=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
            model="eleven_flash_v2_5",
        ),
    )
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    llm = GoogleLLMService(
        api_key=os.environ["GOOGLE_API_KEY"],
        settings=GoogleLLMService.Settings(
            model=os.getenv("GOOGLE_MODEL", "gemini-3.5-flash-lite"),
            system_instruction=(
                f"You are the Cedar Clinic demo receptionist. Today is {today} in India. "
                "You check doctor availability and book or cancel demo appointments. "
                "Speak in short natural sentences without markdown. Offer up to three slots at a time, in IST. "
                "Call the availability tool before offering a slot. Ask for a phone number out loud. "
                "Before booking or cancelling, read the number back digit by digit and wait for the caller to confirm. "
                "If corrected, read the new number back and wait again. Pass confirmed=true only after their yes. "
                "Only say an action succeeded when its tool returns ok=true. Never invent doctors or bookings. "
                "Decline medical advice and use fictional contact details for this demo."
            ),
        ),
    )
    register_tools(llm, appointments)
    context = LLMContext(tools=TOOLS)
    user, assistant = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    worker = PipelineWorker(
        Pipeline([transport.input(), stt, user, llm, tts, transport.output(), assistant]),
        params=PipelineParams(enable_metrics=True),
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def greet(_transport, _client):
        context.add_message({"role": "developer", "content": "Greet the caller and ask how you can help."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def stop(_transport, _client):
        await runner.cancel()

    await runner.run()
