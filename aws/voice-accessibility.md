# Optional voice assistance

The guided app (`interface/app.py`) supports dictation on Welcome, profile quick-start,
and Assistant, plus read-aloud instructions, checked explanations and assistant answers.
Amazon Transcribe converts recorded WAV audio to text. Amazon Polly reads the text already
shown on screen; it does not rewrite financial explanations. The existing engine still
performs all extraction, portfolio and Guardian checks.

## Enable on the deployed app

The voice changes are integrated with the current main interface, entry point
`interface/app.py`. Add these top-level secrets
alongside the existing event AWS credentials (access key, secret key and session token):

```toml
AF_VOICE_ENABLED = "1"
S3_BUCKET = "alphaforge-datathon-traces-7k2p"
AWS_REGION = "us-east-1"
```

Enable **Voice assistance** in the sidebar. Select the **recording language**, English or French (Canada).
Speech is independent of `LLM_PROVIDER`: offline financial answers can still use AWS speech.
No extra Python packages are needed. Microphones require HTTPS or localhost. The interface
remains in English; the selector controls microphone transcription, not UI translation or playback.
Playback reads the displayed English text with Joanna using Polly's neural engine. Explicitly French
content can use Gabrielle (neural) via `read_aloud(..., language_code="fr-CA")`. No standard-engine
fallback silently degrades voice quality.

## Permissions

Add the following to the credential identity's existing permissions. Adapt the bucket
and account as needed. The bucket and Transcribe job must be in the same region.
No bucket creation, public access or account policy changes are performed by this code.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::alphaforge-datathon-traces-7k2p/voice/*"
    },
    {
      "Effect": "Allow",
      "Action": ["transcribe:StartTranscriptionJob", "transcribe:GetTranscriptionJob", "transcribe:DeleteTranscriptionJob"],
      "Resource": "arn:aws:transcribe:us-east-1:*:transcription-job/alphaforge-voice-*"
    },
    {
      "Effect": "Allow",
      "Action": "polly:SynthesizeSpeech",
      "Resource": "*"
    }
  ]
}
```

Transcribe must be able to read the input and write its transcript to S3. If the bucket
uses a customer-managed KMS key, its key policy and KMS permissions must also allow that
access. The input requests AES256 server-side encryption; bucket policy restrictions
still apply. If speech is unavailable in the event account, leave `AF_VOICE_ENABLED` unset
or `"0"`; typing still works. Offline tests mock AWS and cannot establish live access.

## Interaction and retention

1. Record up to 60 seconds with the native microphone control.
2. Explicitly press **Transcribe recording** to send audio to Amazon Transcribe via S3.
3. The transcript appears automatically (status checked every two seconds); **Discard recording** cleans up.
4. Review/edit names, amounts and percentages, then press **Use this transcript**.
5. Submit with the normal profile/question button. Recognition is fallible; a confirmed
   transcript is treated as user input, not proof of identity or intent.

Random `voice/<uuid>/` objects and the Transcribe job are deleted on successful retrieval,
terminal failure (best effort on AWS errors). Discarding deletes current objects; AWS
batch jobs cannot be stopped while in progress, so a discarded job may still finish and
write a transcript later. Its objects require lifecycle cleanup and its job metadata
requires operator cleanup after completion. Configure an S3
lifecycle rule expiring **only `voice/` objects after one day**, before public voice use,
to cover abandoned sessions, crashes and failed cleanup. Never apply it to `raw/` or
`traces/`. The app warns if cleanup fails. Abandoned Transcribe jobs can require operator
cleanup. No audio is written to local disk, shared caches, logs or git. Confirmed text
still follows the engine's existing trace/log retention.

Polly audio stays in session memory. **Listen** prepares audio and requests playback in one click;
if browser autoplay policy blocks it, the player remains available. Navigation and unrelated reruns
never request autoplay. Native controls pause, seek and replay. Long explanations are split at
sentence boundaries for synthesis, then joined as raw PCM in one WAV recording so duration and
seeking remain correct. Financial text is preserved; SSML only controls delivery and escapes user text.
AWS speech usage is billable to the configured account. This is recorded-message
assistance, not a streaming or hands-free assistant. Keyboard input and screen readers
remain available; speech failure never hides the text.

## Verification

```bash
PYTHONPATH=src python -m pytest -q tests/test_voice.py tests/test_accessible_ui.py tests/test_interface_app.py
AF_VOICE_ENABLED=1 LLM_PROVIDER=mock streamlit run interface/app.py
```

Live event-account checklist: both languages, expired credentials, denied permissions,
cancellation, S3 object/job cleanup, microphone denial, keyboard navigation and playback.
Switch Dark mode and Larger text while filling a profile; answers must remain.
Reduced-motion settings suppress animations. Live AWS speech has not been verified by
the offline tests.

API references checked during implementation:
- https://docs.aws.amazon.com/transcribe/latest/APIReference/API_StartTranscriptionJob.html
- https://docs.aws.amazon.com/polly/latest/dg/API_SynthesizeSpeech.html

- https://docs.aws.amazon.com/transcribe/latest/APIReference/API_DeleteTranscriptionJob.html
