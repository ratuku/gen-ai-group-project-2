# Completed OpenAI coding follow-up

All eight planned slots completed on October 15, 2026. GPT-4.1 mini
(`gpt-4.1-mini-2025-04-14`) passed 3/4 tasks; GPT-4.1
(`gpt-4.1-2025-04-14`) passed 4/4. See TEST_RESULTS.md and results.json for all
outcomes, errors, exact prompts, grading output, and tool traces.

Both used the unchanged four task definitions, isolated fresh workspaces,
production OpenAIProvider -> BasicAgentLoop -> dispatcher -> execution policy ->
MCP pipeline, all four configured servers (19 tools), auto mode, eight model
iterations and a 180-second active deadline. The hidden behavioral grader remained
outside each model's filesystem root. Execution success requires passing code,
successful source read/edit, required tool calls and normal agent completion.

The existing OpenAI adapter uses streamed Chat Completions, SDK-default
temperature, max_completion_tokens=4096, store=false, a 30,000-byte model context
view, and at most two retries after temporary errors. Both GPT-4.1 models use no
explicit reasoning_effort. Metadata records these settings and source hashes;
source_snapshot preserves the 45 executed production/harness source files.

## Failure and explanation review

Mini's unique_words accepted the Kelvin sign after lowercasing converted it to
ASCII k. The required ASCII-only boundary check failed on `café K İ hello`.
Valid syntax and a confident final response did not establish behavior. The full
model's implementation passed the same hidden case.

Both documentation implementations passed behavior and integration checks.
Mini nevertheless misrepresented its evidence: local RAG returned pathlib-related
read/configuration passages, not Path.write_text's encoding/return contract.
Its two DeepWiki content calls failed (stream size and unexpected head/tail
arguments); a wiki-structure call succeeded but supplied no API details. Its final
claim that retrieval confirmed write_text was ungrounded, and the claim that no
existing code was present was misleading because the starter function existed.
This is retained as a machine coding pass with a failed manual grounding review.

GPT-4.1 queried DeepWiki directly for write_text, obtained encoding and return
details, and explicitly acknowledged the local RAG gap. All three required MCP
server types were actually invoked during each documentation task. No behavioral
check-server invocation was required by these historical task definitions; checks
were run independently by the evaluator after agent completion.

## Interrupted first batch

The earlier `../2026-10-15-openai/` directory retains two scored bugfix passes and
an interrupted feature workspace. A UnicodeDecodeError in the Windows grader
prevented that feature from receiving a recorded score. The isolated child
ignored PYTHONUTF8 and wrote cp1252 while the parent decoded UTF-8. The grader now
sets `-X utf8` on the child and explicit UTF-8 decoding on the parent. A regression
test exercises an accented traceback. The replacement batch started all eight
slots fresh. No failed scored task was retried to obtain a better score.

## Limits and validation

One attempt per task/model is a small descriptive comparison. Changes in provider,
generation settings, implementation and external service state prevent attributing
the difference from the original Groq baseline solely to model quality. Model
failures remain failures, and the Groq checkpoint remains paused. No Groq API
calls were made during this follow-up. Token cost was not measured.

Final local checks: 277 pytest tests passed; strict mypy passed for 67 files.
The complete report is PROJECT_REPORT.pdf at the repository root, pages 11-12.
The required video demo remains a separate team deliverable.
