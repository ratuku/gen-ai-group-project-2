# Submission report

**[Open PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf)**

The submission PDF is stored at the repository root so it is visible immediately
when opening the project folder or GitHub repository. This folder contains its
supporting guide; the root PDF is the submission copy.

This is the consolidated report for the assignment's PDF deliverable.

| Required content | PDF location |
|---|---|
| System description and design decisions | Page 1 |
| At least two LLMs on the same coding tasks | Page 2 |
| Advanced RAG technique and insights | Page 3 |
| Reflection: worked, failed, improvements | Page 4 |
| Original planning architecture diagram | Page 5, original PDF page preserved |
| Updated architecture and reasons for changes | Page 6 |

The report includes the baseline, intermediate diagnostics, and partial free-tier
live results. The final
reliability policy still needs a complete live retest; the PDF states this
limitation. It does not automatically incorporate later runs made in PowerShell.
Update the evidence and rebuild before submission if new results become available.

Supporting traces and results remain in `evaluations/model_comparison/results/`.
The recorded retrieval observations are documented in `docs/rag-reranking.md`.
The original diagram is `init-architecture.drawio2.pdf` at the repository root.

To rebuild, run `scripts/build_submission_report.py` with Python that has
`reportlab` and `pypdf` installed. It writes `PROJECT_REPORT.pdf` at the repository
root. No Groq calls are made by the report builder.
