# Video script (≤ 5 minutes, brief p.15)

Two contrasting clients (brief p.15): **Robert** (59, cautious, asks for 25% in Tesla) and **Amira** (26, high risk,
AI and crypto), both in the demo app where the agents' hand-offs are visible; then the guided interface reviewing a
portfolio someone already holds. Show AWS doing real work (slide 7: qualifying). About 700 spoken words: ~4:45 at a
calm pace, 15 s of margin. Every agent answer shown is one `make warm` saved (Bedrock replayed, no live call needed).

**Numbers said aloud** (rule 3, all in `results.csv`): Tesla's worst drop −70.9%, 25% alone −17.7%, fits up to 3.1%
(`persona-request`); Robert's loss limit 15% (`persona-limits`); first strategy 15% in stocks, worst drop −8.6%,
2022 −5.8% (`persona-strategies`); 16 of 16 test profiles (`guardian-scenarios`). Anything else: let the screen show
it, don't say it. Re-check these four rows after the final `make log-personas`.

## Before recording

1. `make warm` with valid AWS keys, then commit `cache/` (the demo replays the real Bedrock answers; without it the
   texts fall back to the template and the Critic to its rule-based version).
2. Demo app (`make app`): run "Robert asks for 25% in Tesla" and "Amira" once each. Guided interface (`make ui`):
   Welcome → "I already have a portfolio" → "Try with an example client" + "Try an example portfolio (mostly
   Canadian)". These are exactly what `make warm` cached; another client or question would run live (or fall back).
3. Browser at 125% zoom, one window, notifications off. Have `aws/architecture.en.png` open in a tab. Optional: the S3
   console on `traces/` for the 3:55 cut.

## Script

| Time | Screen | Voice-over (read as written) |
|---|---|---|
| **0:00–0:25** · Problem | Title card: "AlphaForge AI — an investment analyst that can say no, and shows why". Then Robert's persona card. | "Investors can see every price, but not what a portfolio means for *them*: how much they can lose, how long they have, whether a hyped stock fits. Meet Robert. He's 59, retires in four years, and wants to put 25% of his savings in Tesla. A good advisor wouldn't just say yes, or no. They'd show him why." |
| **0:25–1:05** · Architecture | `aws/architecture.en.png`. Point at each box as you name it: Extractor, Profiler, Portfolio, Guardian, Critic, Explainer, Analyst; then the AWS box. | "AlphaForge is a team of specialised agents in a fixed order. Four of them are Strands agents running Claude on Amazon Bedrock: the Extractor reads the client's own words, the Critic challenges the proposals, the Explainer writes the answer, and the Analyst handles follow-up questions. They decide what to check and how to say it. But every limit and every number comes from code: the Profiler, the Portfolio and the Guardian, seventeen rules modelled on Canadian know-your-client duties. The agents argue; code enforces. And every run is saved to Amazon S3, so any answer can be audited." |
| **1:05–1:50** · Robert's limits | Demo app, "Robert asks for 25% in Tesla". Tab **Profile & limits**: scroll the Profiler's reasons; stop on the Tesla request. | "Here's Robert. The Profiler turns his answers into limits, each with its reason. His loss limit is 15%: the most cautious of what he told us and what his situation allows. Now his request. Tesla's worst drop in the data was minus 70.9%. At 25%, that alone would have cost 17.7% of his whole portfolio, more than his entire loss limit. So the system doesn't refuse him. It tells him Tesla fits his limits up to 3.1%, and the choice stays his." |
| **1:50–2:35** · Strategies + Critic | Tab **Strategies**: the first strategy's card (split, worst drop, what set the split). Then tab **Activity & evidence**: scroll to "Critic → Portfolio". | "The Portfolio proposes up to three strategies at different risk levels. The first holds 15% in stocks. Its worst historical drop was 8.6%, and in 2022 it lost 5.8%, The final portfolio also passes a simulated loss check based on stated assumptions, not a future guarantee. The card says what set that split: here, his four-year horizon. Then the Critic steps in. It doesn't just give an opinion: it calls tools first, correlations, each holding's share of the risk, the checks closest to their limit, and every objection must cite a result it obtained. If it proposes a fix, code recomputes the whole strategy and the Guardian checks it again." |
| **2:35–3:05** · Explanation | Tab **Explanation**: the text, then the G11–G13 checks under it. | "The Explainer writes for Robert in plain language. It never types a number itself: it writes placeholders, and code fills in the computed values. The Guardian then checks the text: the disclaimer is there, every number is traced, and his Tesla request is answered. If the text fails, a template replaces it, and the trace says why." |
| **3:05–3:35** · Amira | Demo app, "Amira": **Profile & limits** (her limits and reasons), **Strategies** (the first card), then **Follow-up (Analyst)**: the cached question "NVDA et QQQ, c'est le même pari ?". | "Now a very different client. Amira is 26, has fifteen years ahead of her, and is interested in AI and crypto. Same engine, different limits, so a different and justified answer: more room for growth. Crypto is even considered only because she asked for it, and it stays only if her profile allows it and the data agrees; the trace says which. She can ask follow-ups, even in French: the Analyst checks whether Nvidia and the Nasdaq ETF are the same bet by calling the correlation tool, and every number in its answer must come from that tool." |
| **3:35–4:20** · Existing portfolio | Guided interface: Welcome → "I already have a portfolio" → example client + example portfolio → **Your results**: "The portfolio you already have" (checks, fees, the rebuild moves in $). Then **Assistant**: "What if I add 40,000 $ of XSP to my current portfolio?". Optional cut: S3 console, the run's JSON in `traces/`. | "Many clients don't start from zero. In the guided interface, a client enters what they already hold, or describes it in their own words. The same checks and the same Guardian review it: concentration, sectors, geography, fees. Then the system shows how to rebuild it into a strategy that fits their limits, with each move in dollars. Ask about a fund we have no data for, like XSP, and it's measured with a labelled stand-in, never silently. And this run, like every run, is saved to Amazon S3." |
| **4:20–4:40** · Validation, limits | Terminal: `make scenarios` ending "16/16". Then the tech doc's limitations list. | "We validate it with sixteen test profiles, including deliberate traps, like an explanation with an invented number. All sixteen get the right verdict. And we're clear about the limits: these numbers describe the past, not the future, and this is a simulation, not advice." |
| **4:40–4:55** · Close | Title card + team names + repo link. | "AlphaForge: an analyst that adapts to each investor, says no when it must, and always shows why. Thank you." |

## Cut list if over time

1. Drop the S3 console cut (4:20): the sentence alone is enough.
2. Shorten the explanation beat (2:35) to its first two sentences.
3. Never cut: Robert's Tesla numbers, the Critic's tool calls, "the agents argue; code enforces", the AWS sentences.

Record a draft first, watch it once, re-record once. Upload to Google Drive (link shared with "anyone with the link"),
send Monday before 14:00 to logiciel@polyfinances.ca, subject "Datathon - Équipe XX".
