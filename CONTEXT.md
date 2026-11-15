# CONTEXT — shared facts

Two lists. Move a line from **Assumed** to **Verified** only after someone checked it (say who and how).
Agents: never state an Assumed item as fact in code comments or deliverables.

## Verified
Source: polyfinances.ca/datathon page, pasted by Will on 2026-11-12.
- PolyFinances Datathon 2026, Polytechnique Montréal. Teams of 4, "a financial problem that calls on your technical skills".
- Partners: AWS, Valnet, BeeQuest, CGI, Mag Energy Solutions, La Caisse, Finance Montréal, Desjardins, Banque Nationale, CFA Montréal.
- The networking-night ticket is titled "Datathon Banque Nationale du Canada x AWS", so **Banque Nationale + AWS look like the headline sponsors** (the challenge owner is not confirmed).
- Schedule:
  | When | What | Where |
  |---|---|---|
  | Fri Nov 6, 14:00 | AWS workshop (online) | |
  | Sat Nov 14, 9:00 | Check-in + brunch | Galerie Rolland, main pavilion |
  | Sat 10:00 | Opening ceremony | Amphitheatre, main pavilion |
  | Sat 10:30 | **Challenge presentation** | Amphitheatre |
  | Sat 11:00 | Workshop 1 | Amphitheatre |
  | Sat 12:00 | **Datathon starts** + Q&A | |
  | Sat 14:00 | Workshop 2 | M-1020, Lassonde |
  | Sun Nov 15, 16:00 | End of on-site datathon | |
  | **Sun 23:59** | **Deliverables due: GitHub repo + application** | |
  | **Mon Nov 16, 13:59** | **AWS accounts closed, data destroyed** (but see below: the event dashboard points to ~11:30) | |
  | **Mon 14:00** | **Submission due: video, one-pager, technical documentation** | |
  | Fri Nov 20, 14:00 | Finalist pitches | M-5519, Lassonde |
  | Fri 17:00 / 18:00 | Jury deliberation / networking night | Atrium, Lassonde |

## Verified (organizers' reminder, pasted by Will on Sun Nov 15)
- **Sun 23:59, on Devpost:** public link to the deployed tool; GitHub repo link (installation guide in the README);
  team number. **No change after 23:59, or disqualification** (repo and deployed tool frozen).
- **Mon before 14:00, email to logiciel@polyfinances.ca**, subject "Datathon - Équipe XX": demo video (5 min max,
  Google Drive link), technical documentation (PDF), one-pager (PDF).
- **AWS accounts close Mon 13:59** (this replaces the dashboard's ~11:30 estimate). One member submits for the team.

## Verified (official challenge brief PDF, in `Datathon2026Infos/`, read 2026-11-14)
- Challenge: "AlphaForge AI", owned by Banque Nationale + AWS. Agentic, self-explaining solution on public financial data for different investor profiles.
- Entirely simulation: no real transactions, no personalized financial advice; separate facts / assumptions / fictional scenarios; state uncertainty.
- Three personas: Amira, Mateo, Robert (see CLAUDE.md). Teams are free to choose assets, use case, architecture, output format.
- Starter dataset optional: 31 assets, 2021-11-12 to 2026-11-12. Prices in listing currency (.TO = CAD, else USD); use `adj_close` for returns; macro monthly data is dated by reference month, not release date (avoid look-ahead); survivorship bias; no ESG/news/fundamentals.
- Judging and deliverables: see CLAUDE.md. Submission platforms/formats "to be confirmed in official logistics".

## Verified (team notes from the challenge presentation, Nov 14)
- Grading weights: 20% solution, 20% agentic, 20% data, 10% UX/UI, 15% AWS, 15% pitch (Will's notes; confirmed on slide 10 of `Presentation_AlphaForge_AI_Participants - EN V2.pptx`).
- **AWS is a qualifying requirement** (slide 7): "AWS must make a real and demonstrable contribution to the functioning of the solution. Lack of effective integration = project not eligible for final evaluation." Also: choose services that really serve the case, show AWS's real role in the flow, make the architecture understandable and scalable, best practices (security, access, data, resource efficiency), "Don't multiply services to impress. Justify each choice."
- Brief p.17: explanations faithful to sources and observable actions, "without inventing justifications or exposing detailed internal model reasoning". Simulation only; no real transactions; not personalized financial advice.
- Emphasis on multi-agent design with specialised agents, explainability, cited public sources, contrast between personas.
- AWS account: one shared account per team, valid 72h (email from AWS); all services except Route 53 domains and large GPU instances.
- **AWS closing time: plan for Mon Nov 16 ~11:30, not 13:59.** The AWS Workshop Studio event dashboard (seen by Will, Sat Nov 14) shows start 11/13/2026 11:30 AM, duration 72 hours, and a countdown consistent with Mon ~11:30. The official schedule says 13:59. Use the earlier one: `make backup` and every AWS export **before 11:00 Monday**.

## Verified (ETF holdings files, checked 2026-11-14 by `scripts/build_holdings.py`)
- SPY (State Street daily holdings xlsx, downloaded 2026-11-14): as of 2026-11-12, 503 holdings after merging GOOG into GOOGL, weights sum to 99.97%, cash 0.10%. Contains AAPL 7.90%, NVDA 6.14%, MSFT 5.93%, GOOGL 4.82%, AMZN 4.01%, TSLA 1.71%, JPM 1.39%, XOM 1.07%, JNJ 1.04%, PG 0.60%.
- QQQ, ESGV, XIU: not loaded yet (issuer pages need a browser; download by hand, see `data/README.md`).

## Verified (AWS setup, `make bedrock-check` ALL PASS on 2026-11-14)
- Region us-east-1. Bedrock model `global.anthropic.claude-opus-5-5` (Claude Opus 5.5) enabled: text replies and tool use (Converse, `toolChoice` auto) both work. It rejects `temperature`, so `dh.llm.ask` sends it only when asked.
- S3 bucket `alphaforge-datathon-traces-7k2p` (us-east-1): put/get/delete work. For run traces and input profiles (decision #14).
- Credentials are event session tokens: they expire. Fresh keys into `.env`, then `make bedrock-check`.

## Assumed, not yet checked (confirm at the 10:30 challenge presentation)
- Whether Kiro counts / is expected (mentioned at the presentation, unclear). The AWS requirement itself is Verified above.
- Judging criteria. In 2025 (from search snippets) they were financial relevance & explainability + use of AWS (architecture quality, scalability), with judges from La Caisse and AWS.
- "Application" = a working app/demo the judges can run or view. Confirm the format (URL? repo + instructions?).
- Prizes: 2025 had >$4,500 total, including an AWS prize (architecture) and Nova prizes (women in AI & finance). Sponsor-specific prizes in 2026 are unknown.
- Each team gets an AWS account. Which Bedrock models are enabled is unknown.
- Past winning projects used Bedrock (agents, knowledge bases), S3, Textract, Comprehend.

## Open questions for organizers / mentors
- Exact judging grid and weights? Is there a scored metric / leaderboard, or judging only?
- Who owns the challenge (Banque Nationale?), and are there sponsor-specific prizes?
- What counts as the "application"? Must it be deployed on AWS?
- Video max length? One-pager format? Is the GitHub repo public or shared with judges?
- External data allowed? Rules on AI coding tools?
