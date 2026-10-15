# Final non-video deliverable validation - 15 October 2026

Supporting verification record for tickets #15 and #17, based on merged main
`031edeb` and the additions on `codex/remaining-deliverables`.

| Check | Observed result |
|---|---|
| Full regression suite, `python -m pytest` | **249 passed** in 28.47 seconds |
| Strict typing, `python -m mypy` | No issues in **65 files** |
| Installed CLI connection check | Four servers, 19 dynamically discovered tools: filesystem 14, DeepWiki 3, checks 1, RAG 1 |
| New command tool's MCP/pytest test | Real subprocess runs the fixture test and returns `1 passed` with exit 0 |
| Python-check error handling | Nonzero exit, timeout, returned-output limit, outside-workspace target rejection, non-Python script rejection, and credential-variable omission covered |
| Production agent-to-command integration | BasicAgentLoop + ToolDispatcher + confirmation policy + actual stdio MCP server + Python subprocess completed with reason `answered`; approval callback called once; real fixture output observed |
| RAG retrieval experiment | All ten question pairs completed through the production stdio server; exact prepared text/metadata verified |
| Controlled generated RAG answers | Five pairs completed; eleventh request stopped by `provider_daily_limit`; nine later answer slots unattempted |
| Scoring reproducibility | Offline scorer checks evidence hashes and recomputes retained metrics |
| Submission PDF | Ten pages; original planning page preserved; authored pages visually checked |

The agent-to-command integration uses a deterministic provider to select the
tool, so it verifies execution plumbing and policy, not a live LLM's decision
quality. The CLI connection check does not invoke tools or an LLM. RAG answer
generation is live and uses the production Groq adapter. Historical coding trials
predate the new check server; their scores are retained without attributing new
capabilities to those trials. Original planning history is preserved rather than
recreated. The separate video demo remains excluded.
