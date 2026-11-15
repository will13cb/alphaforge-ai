"""Speech transport tests: real WAV validation, mocked AWS, no network or credentials."""
import io
import json
import wave

import pytest

from interface.core import voice


def recording(seconds=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0\0" * 16000 * seconds)
    return out.getvalue()


class AWS:
    def __init__(self):
        self.calls = []
        self.state = "IN_PROGRESS"
        self.fail = None

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            if name == self.fail:
                raise RuntimeError("AccessDenied")
            if name == "get_transcription_job":
                return {"TranscriptionJob": {"TranscriptionJobStatus": self.state}}
            if name == "get_object":
                return {"Body": io.BytesIO(json.dumps({"results": {"transcripts": [{"transcript": "15% in Tesla"}]}}).encode())}
            if name == "synthesize_speech":
                return {"AudioStream": io.BytesIO(b"\x00\x00" * 160 if kwargs.get("OutputFormat") == "pcm" else b"mp3")}
            return {}
        return call


@pytest.fixture
def aws(monkeypatch):
    fake = AWS()
    monkeypatch.setenv("AF_VOICE_ENABLED", "1")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setattr(voice, "_client", lambda service: fake)
    return fake


def test_disabled_never_contacts_aws(aws, monkeypatch):
    monkeypatch.delenv("AF_VOICE_ENABLED")
    with pytest.raises(voice.VoiceError, match="not enabled"):
        voice.start(recording(), "en-CA")
    assert not aws.calls


def test_invalid_and_long_audio_never_uploaded(aws):
    for audio in (b"invalid", recording(61), b""):
        with pytest.raises(voice.VoiceError):
            voice.start(audio, "en-CA")
    assert not aws.calls


def test_complete_job_uses_private_output_and_cleans_up(aws):
    ticket = voice.start(recording(), "fr-CA")
    start = next(kw for name, kw in aws.calls if name == "start_transcription_job")
    assert start["LanguageCode"] == "fr-CA"
    assert start["OutputKey"] == ticket["output_key"]
    assert ticket["input_key"].startswith("voice/")
    assert voice.poll(ticket) == ("pending", "")
    assert not [c for c in aws.calls if c[0] == "delete_object"]
    aws.state = "COMPLETED"
    assert voice.poll(ticket) == ("done", "15% in Tesla")
    deleted = [kw["Key"] for name, kw in aws.calls if name == "delete_object"]
    assert deleted == [ticket["input_key"], ticket["output_key"]]
    assert any(name == "delete_transcription_job" for name, _ in aws.calls)


def test_start_failure_cleans_up_and_keeps_error_safe(aws):
    aws.fail = "start_transcription_job"
    with pytest.raises(voice.VoiceError, match="could not start"):
        voice.start(recording(), "en-CA")
    assert any(name == "delete_object" for name, _ in aws.calls)


def test_failed_job_cleans_up(aws):
    ticket = voice.start(recording(), "en-CA")
    aws.state = "FAILED"
    with pytest.raises(voice.VoiceError, match="could not be transcribed"):
        voice.poll(ticket)
    assert any(name == "delete_transcription_job" for name, _ in aws.calls)


def test_polly_reads_plain_text_only_and_does_not_truncate(aws):
    assert voice.speak("**Worst drop**: 15%", "fr-CA") == b"mp3"
    kw = aws.calls[-1][1]
    assert "Worst drop : 15%" in kw["Text"]
    assert kw["VoiceId"] == "Gabrielle" and kw["Engine"] == "neural" and kw["TextType"] == "ssml"
    with pytest.raises(voice.VoiceError, match="too long"):
        voice.speak("x" * 3000, "en-CA")


def test_delete_failure_is_visible(aws):
    ticket = voice.start(recording(), "en-CA")
    aws.state = "COMPLETED"
    aws.fail = "delete_object"
    with pytest.raises(voice.VoiceError, match="cleanup failed"):
        voice.poll(ticket)


def test_discarding_running_batch_job_defers_job_cleanup(aws):
    ticket = voice.start(recording(), "en-CA")
    aws.fail = "delete_transcription_job"
    assert voice.cancel(ticket)  # S3 removal succeeds, running job cleanup is deferred
    assert any(name == "get_transcription_job" for name, _ in aws.calls)
    assert len([name for name, _ in aws.calls if name == "delete_object"]) == 2


def test_narration_preserves_long_text_in_one_seekable_recording(aws):
    text = "The worst historical loss was 15%. " * 180
    audio, mime = voice.narrate(text)
    calls = [kwargs for name, kwargs in aws.calls if name == "synthesize_speech"]
    assert len(calls) > 1
    assert all(c["OutputFormat"] == "pcm" and c["Engine"] == "neural" for c in calls)
    from xml.etree import ElementTree
    spoken = " ".join("".join(ElementTree.fromstring(c["Text"]).itertext()) for c in calls)
    assert spoken == voice.plain_text(text)
    assert mime == "audio/wav"
    with wave.open(io.BytesIO(audio)) as recording:
        assert recording.getnframes() == 160 * len(calls)
        assert recording.getnchannels() == 1
        assert recording.getframerate() == 16000


def test_neural_speech_escapes_user_text_instead_of_executing_ssml(aws):
    voice.speak("Return < 3% & <break time='10s'/>", "en-CA")
    from xml.etree import ElementTree
    root = ElementTree.fromstring(aws.calls[-1][1]["Text"])
    assert root.find(".//break") is None
    assert "Return < 3%" in "".join(root.itertext())
