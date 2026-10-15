# Groq Cloud provider

The Groq adapter implements the `ModelProvider` contract. It streams text,
assembles fragmented function calls, preserves tool-call IDs, and sends a bounded
view of conversation and MCP results to the cloud model. Full results remain in
agent history and CLI events.

## API key

Current limits and model availability can change, so check the official
[Groq rate-limit documentation](https://console.groq.com/docs/rate-limits).

1. Create or sign in to a Groq Cloud account.
2. Create an API key in the Groq Console.
3. Store the key only in your environment. Never place it in source code, Git,
   screenshots, logs, or committed configuration files.

In Windows PowerShell:

```powershell
$env:GROQ_API_KEY = "your-key"
```

The variable applies only to the current PowerShell process and its children. This
repository does not contain or load a committed key file.

## Model configuration

The default is `openai/gpt-oss-20b`, a tool-capable model. Override it when another
enabled model is preferred:

```powershell
$env:GROQ_MODEL = "openai/gpt-oss-20b"
```

Model availability is controlled by Groq and may change independently of this
project. A missing or unavailable model produces an actionable CLI error.

## Install and run

Install the project dependencies and the filesystem MCP server from the repository
root:

```powershell
python -m pip install -r requirements-dev.txt
npm.cmd ci
```

Run a single task:

```powershell
coding-assistant `
  --config .\config\mcp.json `
  --workspace . `
  --provider groq `
  --execution-mode confirm `
  --task "List the top-level project files using the filesystem tool."
```

Omit `--task` for the interactive prompt.

The standard `config/mcp.json` connects filesystem, hosted DeepWiki, and the local
custom RAG server. It needs internet access and a prepared RAG index; see the RAG
setup documentation. The RAG subprocess uses `${pythonExecutable}` so it runs in
the same Python environment as the assistant.

## Data and tool-call flow

Conversation messages, MCP tool definitions, and tool results sent back for model
reasoning leave the local machine and are processed by Groq Cloud. Do not submit
secrets or private repository content unless that use is permitted by your team and
Groq's applicable terms.

MCP tools still execute through this application's existing dispatcher. The model
requests a tool; the dispatcher validates its exact name and JSON arguments. The
default confirmation policy then waits for approval before invoking the configured
MCP server. Rejections and results are added to conversation history. Groq does not
directly execute the local filesystem tool. Pass `--execution-mode auto` only when
unattended execution is intended.

Groq streams tool-call IDs, names, and JSON arguments in fragments. The adapter
assembles and validates a complete object before emitting the provider-neutral
`tool_call` event expected by `BasicAgentLoop`.

## Reliability and request limits

The API sees flat, collision-safe aliases such as `filesystem__read_text_file`.
The adapter maps them back to the exact discovered MCP tool. An unqualified name
can resolve only when exactly one discovered tool has that basename. Unknown or
ambiguous names trigger bounded regeneration before any tool in that response is
executed. Optional null arguments are omitted only when the discovered schema
forbids null; required and nullable fields still reach local validation.

Groq's remote tool-presence validation is disabled so generation can be inspected
and repaired locally. The dispatcher still validates the original tool name and
schema, and confirmation/auto policy still gates execution. The entire returned
batch is parsed and checked before it is exposed to the agent. Python edit text
normalizes CRLF and lone carriage returns to LF to avoid the filesystem server's
fuzzy-match indentation fallback observed on Windows.

Requests use temperature 0, up to 2,048 completion tokens, and low reasoning effort
for GPT-OSS models. Tool descriptions and duplicated result envelopes are compacted.
The model-facing payload targets 18,000 UTF-8 bytes. This is an approximate size
budget, not an exact token count. Older completed interactions can become explicit
outcome summaries; oversized recent edits can also be summarized as completed
actions. Call/result pairs are retained together, and the current task is kept.
If required context cannot fit, the request fails clearly. The original history
is not modified. Large source/result excerpts can require targeted rereads.

Production requests now use a rolling per-model pacer with a default estimated
7,000-token minute allowance and a 2.1-second minimum start interval. It reserves
payload UTF-8 bytes / 3 rounded up, plus 2,048 maximum output tokens, and reduces
the payload byte budget to fit that estimate. Reservations remain for 60 seconds,
even on failed requests. Wait statuses update in steps of at most five seconds
and support cancellation. This is a conservative heuristic, not exact tokenizer
accounting; external usage and daily allowance are unknown, so 429 handling is
still necessary. Evaluation batches share a pacer per model across tasks.

Each model turn permits at most five API attempts. Short HTTP 429 waits follow
`Retry-After` (or a numeric seconds hint), with each wait capped at 60 seconds.
HTTP 413 reduces the model context budget before retrying. Recoverable generation
errors, including errors inside HTTP 200 event streams, receive corrective
feedback; transient connection/server failures use bounded backoff. Waits and
repairs appear as CLI status events and remain cancellable. Once response text
has been exposed, the stream is not replayed. Executed MCP operations are never
automatically retried by this recovery mechanism.

Daily limits and longer waits stop with an actionable message; completed edits
remain on disk. The assistant cannot increase the account's allowance. Model
output can still be semantically wrong, so run project tests and review edits.
Daily-limit errors are not retried even when a short retry hint is present.
Provider rate/daily/capacity error codes survive the agent loop so the evaluation
runner can checkpoint and pause. See [free-tier run/resume instructions](../evaluations/model_comparison/README.md#free-tier-pacing-and-resume).

See Groq's [tool API reference](https://console.groq.com/docs/api-reference),
[local tool calling](https://console.groq.com/docs/tool-use/local-tool-calling),
and [rate-limit guidance](https://console.groq.com/docs/rate-limits), and the
[validation record](../evaluations/model_comparison/results/2026-10-15-fixes/REPORT.md).

## Troubleshooting

- **Missing key:** set `GROQ_API_KEY` in the same terminal used to start the CLI.
- **Authentication failure:** create an active key and replace the environment value.
- **Rate limit:** short waits retry visibly; daily/long limits require waiting for
  the account allowance to reset before running another task.
- **Context too large:** use targeted reads or fewer MCP tools. The full local
  conversation is retained even when the model-facing view is compacted.
- **Model unavailable:** set `GROQ_MODEL` to a tool-capable model enabled for the
  account.
- **Connection failure:** confirm internet access and Groq service availability.
