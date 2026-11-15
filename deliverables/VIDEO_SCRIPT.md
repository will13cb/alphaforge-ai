# Video script (~5 minutes, brief p.15)

End-to-end example: the problem, the role of each agent, data and tools, the result, the explanation shown to the
user. Two contrasting investor situations (brief suggests it). Show AWS doing real work (qualifying requirement).

| t | What's on screen | Says |
|---|---|---|
| 0:00 | Title | The problem in one sentence, why it matters to an investor |
| 0:30 | Architecture graph (`aws/architecture.png`) | Four Strands agents on Bedrock (Extractor, Critic, Explainer, Analyst) choose what to check and how to say it; code (Profiler, Portfolio, Guardian) sets every limit and number; S3 keeps every run |
| 1:15 | App: Robert's profile → "25% in Tesla" | Profiler sets his limits (with reasons); the request doesn't fit them: Tesla's worst drop, what 25% alone would have cost, how much fits; he decides |
| 2:15 | Trace + strategies | Hand-off by hand-off: limits, Guardian checks; up to 3 strategies at different risk levels (most growth his limits allow → least in stocks), each saying which constraint set its split (for Robert: the horizon rule, a stated judgment); the Critic's tool calls and what happened to each objection |
| 3:00 | App: Amira, free text → Extractor | Typed in her own words; the Extractor fills the profile, asks what's missing; different profile → different, justified answer (adaptability) |
| 3:45 | Explanation + sources, one follow-up | Every number traced; data sources and dates; one Analyst what-if ("what if 10% in NVDA?") re-running the pipeline |
| 4:10 | Validation + limits | 16 test profiles / correct verdicts; past ≠ prediction; simulation only |
| 4:30 | Guided interface (`make ui`), 15 s | The same engine for a client: one question at a time, results essentials-first, the Analyst as a chat |
| 4:45 | Close | Benefit for the user, next steps |

Record a draft Sunday before 16:00 on site. Re-record once, not five times.
