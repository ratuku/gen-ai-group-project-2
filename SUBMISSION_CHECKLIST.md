# Submission checklist

**Written report: [PROJECT_REPORT.pdf](PROJECT_REPORT.pdf)**

**Repository: [ratuku/gen-ai-group-project-2](https://github.com/ratuku/gen-ai-group-project-2)**

This guide maps the assignment's required materials to their locations. The video
demo is intentionally left for the team; this update does not record or submit one.
Markdown results are supporting evidence, not competing written reports.

| Requirement | Location / status |
|---|---|
| Source repository, README, requirements and setup | Root README, requirements.txt, requirements-dev.txt, pyproject.toml; fresh-checkout and PowerShell steps included |
| Original planning before implementation | Original init-architecture.drawio2.pdf, first committed in d105843; retained unchanged on report page 5 |
| System description and design decisions | Report page 1; docs/architecture.md |
| At least two LLMs on identical coding tasks | Report page 2; evaluations/model_comparison/results/2026-10-15/ (24 attempts, including failures) |
| Advanced RAG technique and measured insights | Report page 3; evaluations/rag_evaluation/README.md and retained paired experiment |
| Reflection: what worked, failed, and improvements | Report page 4 |
| Updated architecture and reasons for changes | Report page 6; docs/architecture.md |
| State diagram | Report page 7; editable Mermaid in docs/diagrams.md |
| Sequence diagrams: at least two scenarios, three full operations | Report pages 8-10: inspect code, repair/test a bug, documentation-assisted feature; Mermaid in docs/diagrams.md |
| Filesystem, external-resource, and custom advanced-RAG MCP servers | config/mcp.json: filesystem, DeepWiki, and RAG; dynamically discovered |
| File operations and command execution | Filesystem tools plus checks.run_python_check, a separate local Python script/pytest MCP tool |
| Cloud and local provider abstraction | Groq and Ollama adapters; README/provider docs cover setup |
| Visible tool calls, streaming, confirmation and automatic execution | CLI / execution policy implementation and regression tests |
| Video: two non-trivial tasks and visible invocation of three required MCP servers | **Remaining: team video demo (#16), excluded from this work** |

## Evaluation limits to retain in the submission

The completed coding baseline is a valid same-task two-model comparison, with low
pass rates and documented causes. Later current-policy coding retesting is partial
because of Groq's free daily allowance; it is not a clean overall reliability score.
The final Python-check server was added after those trials and is not credited
with changing their outcomes.

The RAG experiment completed all ten retrieval comparisons and five complete answer
pairs before the free daily limit. Untested answers are marked untested. Ratings
are Codex's explicit single-assessor judgments, which the team should review.
These limitations do not remove the recorded comparison, examples, or reflection;
they constrain what can be claimed from them. No paid service upgrade was used.

## Verify and rebuild

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m evaluations.rag_evaluation.score `
  .\evaluations\rag_evaluation\results\2026-10-15
```

To rebuild the PDF, use Python with `reportlab` and `pypdf` installed and run
`scripts/build_submission_report.py`. It loads committed RAG metrics, preserves
the original planning page, and writes the root PDF. It makes no cloud calls.
The static vector figures are generated from scripts/report_diagrams.py; Mermaid
sources are in docs/diagrams.md. The PDF and documentation must be updated together
if the implementation or evidence changes.

Submitting to the course website and recording/uploading the video remain team
actions. Repository changes are prepared for review before merge.
