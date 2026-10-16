# Submission verification - October 15, 2026

| Required item | Verified result |
|---|---|
| Public GitHub repository | https://github.com/ratuku/gen-ai-group-project-2 exists and is public. Default branch: main. |
| Planning before implementation | Commit d10584307ff7c6a05396a333a0d3700d8adbf4e6 adds both planning PDFs on October 1. First src commit 364918a is October 5; planning commit is its ancestor. |
| Planning documents included | ProjectPlan.pdf and init-architecture.drawio2.pdf are in repository history and copied here. |
| Setup and code structure | README, requirements.txt, requirements-dev.txt, pyproject.toml, Node package/lock files and modular CLI/agent/provider/MCP/RAG code are present. |
| Local regression checks | 277 pytest tests passed in the latest run; strict mypy passed for 67 source files. No cloud inference used in these checks. |
| Video | Completed per user; not reviewed or copied. Ensure it shows two non-trivial completed tasks and actual filesystem/RAG/external tool calls. |
| System and design decisions | Report page 1. |
| Same-task two-model comparison | Historical Groq comparison on page 2; completed OpenAI comparison on page 11 (GPT-4.1 mini 3/4, GPT-4.1 4/4). |
| Advanced RAG insights | Historical relevance/answer evaluation page 3; all 20 OpenAI paired answers and reviewed grounding on page 12. |
| Reflection | Report page 4, plus failure/limitations discussion pages 11-12. |
| Original architecture | Report page 5 and original PDF in supporting materials. |
| Updated architecture and change explanation | Report page 6. |
| State diagram | Report page 7. |
| Sequence diagrams | Pages 8-10 show inspection, bug repair/checking and documentation-assisted feature implementation. Three distinct end-to-end operations across confirmation/auto scenarios. |
| Separate diagram file | Architecture_and_Workflow_Diagrams.pdf extracts report pages 5-10, preserving vector diagrams. |

## Remaining publication step

The latest changes are committed on codex/submission-openai-followup for a
pull request into main. The twelve-page report, OpenAI provider, evaluation
updates and results reach the default branch when that PR is merged. The latest
main-branch dependency-installation fix is incorporated into the PR branch.
The video/course submission remains a user action.
Local changes from other chats were preserved. No grade guarantee is implied by
passing tests; code documentation and rubric judgment remain qualitative.

## Planning evidence

Planning: https://github.com/ratuku/gen-ai-group-project-2/commit/d10584307ff7c6a05396a333a0d3700d8adbf4e6
First implementation: `364918a` (October 5, 2026).

## Package contents

The source ZIP contains current project files with their repository-relative paths,
including uncommitted source/evaluation changes. It excludes .git, environments,
dependencies, caches, temporary rehearsals, generated vector stores, and this
submission package. GitHub retains the commit history. Do not replace Git history
with the ZIP. The report and extracted diagrams are byte/content verified, and a
SHA256SUMS.txt manifest records every packaged file.
