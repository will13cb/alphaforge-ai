# AlphaForge AI

## Invest within your own limits, and understand why.

William Caron-Bastarache · Joud Katbe · PolyFinances Datathon 2026 · National Bank × AWS

[alphaforge-ai-wj.streamlit.app](https://alphaforge-ai-wj.streamlit.app/) · [github.com/will13cb/alphaforge-ai](https://github.com/will13cb/alphaforge-ai)

### The problem, through one investor
Robert plans to retire in four years. He wants **25% of his savings in Tesla**, while accepting a maximum loss of **15%**. Tesla’s historical decline (**−70.9%**) would have cost **17.7% of his portfolio from that position alone**. AlphaForge explains the conflict and shows a calculated **3.1% cap**, under the model’s assumptions. The client keeps the decision; no trades occur.

### An answer the client can examine
The client describes their situation in **French or English**, answers guided questions or enters existing holdings. The application compares **up to three options**, showing investments, weights and CAD amounts. It explains limits, trade-offs and historical results. The Assistant answers follow-ups and recalculates “what if” scenarios. Existing portfolios can be reviewed and compared with the proposed options.

### Agents investigate; code checks
Four Strands agents: the **Extractor** structures client text; the **Critic** investigates using tools; the **Explainer** presents results; the **Analyst** handles follow-ups. Code calculates limits and allocations. The **Guardian** applies the checks. A Critic revision is recalculated and checked again. Explanation numbers are inserted by code; answers and their sources remain inspectable. Missing ETF holdings data is disclosed.

### AWS with a concrete role
**Amazon Bedrock** runs the agents; the **Strands Agents SDK** provides their tools. **Amazon S3** supplies data and receives analysis traces, with local storage as a fallback if unavailable. Optional **Transcribe** and **Polly** provide dictation and neural speech. **Streamlit Community Cloud** hosts the application outside AWS. Live, cached and fallback answers are distinguished. **AgentCore Runtime is not deployed.**

### Documented data and evaluation
Market baseline: **31 assets, November 12, 2021 to November 12, 2026**, organizer-provided Yahoo Finance prices and Bank of Canada exchange rates and rates; returns in CAD. A separate March 2020 replay tests the same weights outside this period. The held-to-maturity path uses a sourced Canada/U.S. fixed-income catalogue; prices and availability require confirmation.

Documented offline evaluation: **16/16 profiles**, **217/217 checked numbers** in template texts, **200/200 deliberately injected false numbers detected**, and **10/10 adversarial cases**. These results evaluate controls, not future investment returns.

### A measured limitation
In the synthetic-market calibration test, the accepted loss is exceeded in **19 out of 100 cases**, against a target of **10**. The model needs to be more conservative. A lower-equity improvement was tested **but is not integrated**. Scenarios, available data and assumptions limit the scope of the results.

*Fictional-profile simulation · No investment advice · No real transactions.*

*Evidence: results.csv · deliverables/EVALUATION.md · Source: alphaforge-ai/main, c172b92.*
