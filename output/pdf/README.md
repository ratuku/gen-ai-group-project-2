# Submission guide

**[Open PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf)**

The submission PDF is stored at the repository root so it is visible immediately
when opening the project folder or GitHub repository. This folder contains its
supporting guide; the root PDF is the submission copy.

This is the consolidated report for the assignment's PDF deliverable.

**Submit only `PROJECT_REPORT.pdf` as the written report.** Markdown files under
`evaluations/` are supporting test records. Their names identify their purpose:
baseline results, diagnostic pilot details, fix notes, or a partial retest.

| Required content | PDF location |
|---|---|
| System description and design decisions | Page 1 |
| At least two LLMs on the same coding tasks | Page 2 |
| Advanced RAG technique and insights | Page 3 |
| Reflection: worked, failed, improvements | Page 4 |
| Original planning architecture diagram | Page 5, original PDF page preserved |
| Updated architecture and reasons for changes | Page 6 |
| State diagram | Page 7 |
| Three complete sequence diagrams | Pages 8-10 |
| Completed OpenAI coding comparison | Page 11 |
| All 20 OpenAI RAG answers and review | Page 12 |

The report includes historical Groq results and the completed OpenAI follow-up:
eight coding slots (seven passes) and all 20 paired RAG answers. The original Groq
checkpoint remains quota-limited. Provider/settings differences and the small
sample prevent treating the follow-up as a controlled improvement estimate.

Supporting traces and results remain in `evaluations/model_comparison/results/`.
The measured retrieval and answer comparison is in `evaluations/rag_evaluation/`;
the report includes the historical five Groq pairs and ten new OpenAI pairs using
the same frozen retrieval evidence. Explicit judgments,
prompt/source hashes, and reproducible metrics are retained. Older three-query
observations in `docs/rag-reranking.md` remain historical context.
The original diagram is `init-architecture.drawio2.pdf` at the repository root.

To rebuild, run `scripts/build_submission_report.py` with Python that has
`reportlab` and `pypdf` installed. It writes `PROJECT_REPORT.pdf` at the repository
root. No Groq calls are made by the report builder.

See [the submission checklist](../../SUBMISSION_CHECKLIST.md) for all required
materials. The video demo remains the team's separate deliverable.
