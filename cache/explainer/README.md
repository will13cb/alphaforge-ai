# Explainer demo cache (committed)

Real Claude Opus 5.5 texts from the Explainer (Strands agent on Amazon Bedrock), saved with
`make explain P=robert SAVE=1` (or amira/mateo). Each file is keyed by a hash of the facts the Explainer was given,
so the offline demo (`LLM_PROVIDER=mock`) replays the exact text when the pipeline produces the same numbers.
If the numbers change (new data, new rules), the hash changes and the demo falls back to the deterministic template:
re-run the command above while the AWS account is open (it closes Monday).
