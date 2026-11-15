"""Optional AWS speech transport. No financial logic, credentials, or audio on local disk.

Transcribe jobs and S3 objects use a separate voice/ prefix. They are removed on completion,
explicit cancellation, or a terminal failure. Configure an S3 lifecycle as crash protection.
"""
from __future__ import annotations

import io
import json
import os
import re
import uuid
import wave
from xml.sax.saxutils import escape

LANGUAGES = {"English (Canada)": "en-CA", "Français (Canada)": "fr-CA"}
MAX_SECONDS = 60
MAX_BYTES = 4_000_000
MAX_SPEECH = 2800


class VoiceError(Exception):
    """A short, actionable message safe to show in the interface."""


def enabled() -> bool:
    return os.getenv("AF_VOICE_ENABLED", "0") == "1"


def _client(service):
    import boto3
    from botocore.config import Config
    return boto3.client(service, region_name=os.getenv("AWS_REGION", "us-east-1"),
                        config=Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 1}))


def _require():
    if not enabled():
        raise VoiceError("Voice is not enabled on this app. You can still type your answers.")


def validate_recording(audio: bytes) -> None:
    if not audio or len(audio) > MAX_BYTES:
        raise VoiceError("Please record a short message, up to 60 seconds.")
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            seconds = wav.getnframes() / wav.getframerate()
            if wav.getnchannels() != 1 or wav.getcomptype() != "NONE" or not 0 < seconds <= MAX_SECONDS:
                raise VoiceError("Please use a mono recording, up to 60 seconds.")
    except (wave.Error, EOFError, ZeroDivisionError) as e:
        raise VoiceError("This recording could not be read. Please record it again.") from e


def cancel(ticket: dict) -> bool:
    """Discard objects; running batch jobs cannot be stopped and need lifecycle cleanup.

    True means object deletion succeeded and job deletion either succeeded or was deferred
    for an in-progress job. It never implies that AWS stopped processing a running job.
    """
    ok = True
    try:
        _client("transcribe").delete_transcription_job(TranscriptionJobName=ticket["job"])
    except Exception:
        try:
            state = _client("transcribe").get_transcription_job(
                TranscriptionJobName=ticket["job"])["TranscriptionJob"]["TranscriptionJobStatus"]
            if state not in ("IN_PROGRESS", "QUEUED"):
                ok = False
        except Exception:
            ok = False
    for key in (ticket["input_key"], ticket["output_key"]):
        try:
            _client("s3").delete_object(Bucket=ticket["bucket"], Key=key)
        except Exception:
            ok = False
    return ok


def start(audio: bytes, language: str) -> dict:
    _require()
    validate_recording(audio)
    if language not in LANGUAGES.values():
        raise VoiceError("Please choose English or French (Canada).")
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise VoiceError("Voice recording is unavailable until the app's storage is configured. You can still type.")
    ident = uuid.uuid4().hex
    ticket = dict(bucket=bucket, job=f"alphaforge-voice-{ident}",
                  input_key=f"voice/{ident}/input.wav", output_key=f"voice/{ident}/transcript.json")
    try:
        _client("s3").put_object(Bucket=bucket, Key=ticket["input_key"], Body=audio,
                                 ContentType="audio/wav", ServerSideEncryption="AES256")
        _client("transcribe").start_transcription_job(
            TranscriptionJobName=ticket["job"], LanguageCode=language, MediaFormat="wav",
            Media={"MediaFileUri": f"s3://{bucket}/{ticket['input_key']}"},
            OutputBucketName=bucket, OutputKey=ticket["output_key"])
        return ticket
    except Exception as e:
        cancel(ticket)
        raise VoiceError("Voice transcription could not start. Check AWS speech permissions and session expiry, "
                         "or type your message.") from e


def poll(ticket: dict) -> tuple[str, str]:
    """One bounded status check; the UI never waits in a polling loop."""
    _require()
    try:
        job = _client("transcribe").get_transcription_job(TranscriptionJobName=ticket["job"])["TranscriptionJob"]
        state = job["TranscriptionJobStatus"]
        if state == "FAILED":
            raise VoiceError("The recording could not be transcribed. Please try again or type your message.")
        if state != "COMPLETED":
            return "pending", ""
        obj = _client("s3").get_object(Bucket=ticket["bucket"], Key=ticket["output_key"])
        with obj["Body"] as body:
            result = json.loads(body.read(MAX_BYTES))
        text = result["results"]["transcripts"][0]["transcript"].strip()
        cleaned = cancel(ticket)
        if not cleaned:
            raise VoiceError("Transcription finished, but temporary recording cleanup failed. Ask the app owner "
                             "to clear voice/ storage and check delete permissions before trying again.")
        if not text:
            raise VoiceError("No speech was detected. Please try again or type your message.")
        return "done", text
    except VoiceError:
        cancel(ticket)
        raise
    except Exception as e:
        cancel(ticket)
        raise VoiceError("The transcript could not be retrieved. Check AWS access or type your message.") from e


def plain_text(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s+(.+?)[.:]?\s*$", r"\1. ", text)
    return re.sub(r"\s+", " ", re.sub(r"[*#_`|]", " ", text)).strip()


def passages(text: str) -> list[str]:
    """Split at sentence boundaries without dropping or changing financial facts."""
    remaining = plain_text(text)
    parts = []
    while remaining:
        end = min(len(remaining), MAX_SPEECH)
        if end < len(remaining):
            boundary = max(remaining.rfind(". ", 0, end), remaining.rfind("? ", 0, end), remaining.rfind("! ", 0, end))
            end = boundary + 1 if boundary >= end // 2 else (remaining.rfind(" ", 0, end) or end)
        parts.append(remaining[:end])
        remaining = remaining[end:].lstrip()
    return parts


def _synthesize(text: str, language: str, output: str) -> bytes:
    # Both voices support the neural engine in the deployment region us-east-1.
    response = _client("polly").synthesize_speech(
        Text="<speak><prosody rate='95%'>" + escape(text) + "</prosody></speak>",
        TextType="ssml", OutputFormat=output, SampleRate="16000" if output == "pcm" else "24000",
        Engine="neural", VoiceId="Gabrielle" if language == "fr-CA" else "Joanna")
    with response["AudioStream"] as stream:
        return stream.read()


def speak(text: str, language: str) -> bytes:
    _require()
    if language not in LANGUAGES.values():
        raise VoiceError("Please choose English or French (Canada).")
    text = plain_text(text)
    if not text:
        raise VoiceError("There is no text to read yet.")
    if len(text) > MAX_SPEECH:
        raise VoiceError("This passage is too long. Please choose a shorter section to read.")
    try:
        return _synthesize(text, language, "mp3")
    except Exception as e:
        raise VoiceError("Read aloud is unavailable. Check Amazon Polly permissions and AWS session expiry. "
                         "The full text remains on screen.") from e


def narrate(text: str, language: str = "en-CA") -> tuple[bytes, str]:
    """One playable recording, even for a long explanation. No MP3 concatenation.

    A WAV container joins raw PCM passages so seeking and duration stay correct.
    Short text uses MP3 to keep preparation fast. Language describes the displayed
    text, independently of the language selected for microphone transcription.
    """
    parts = passages(text)
    if len(parts) <= 1:
        return speak(text, language), "audio/mp3"
    _require()
    if language not in LANGUAGES.values():
        raise VoiceError("Please choose English or French (Canada).")
    try:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for part in parts:
                wav.writeframes(_synthesize(part, language, "pcm"))
        return output.getvalue(), "audio/wav"
    except Exception as error:
        raise VoiceError("Audio could not be prepared. Try again; the full text remains on screen.") from error
