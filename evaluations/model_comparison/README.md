# Model comparison (ticket #14)

## Completed OpenAI follow-up

[Current findings](results/2026-10-15-openai-complete/OPENAI_FOLLOWUP.md) cover
all eight coding slots: GPT-4.1 mini passed 3/4 and GPT-4.1 passed 4/4. The original
Groq checkpoint and interrupted first OpenAI batch remain preserved.

Run a separate OpenAI batch with an existing `OPENAI_API_KEY` in the environment:

```powershell
.\.venv\Scripts\python.exe -m evaluations.model_comparison.run --provider openai --models gpt-4.1-mini-2025-04-14 gpt-4.1-2025-04-14 --output evaluations/model_comparison/local/new-openai-run --max-iterations 8 --timeout 180
```

This uses the existing OpenAI adapter: SDK-default sampling, 4,096 completion
tokens, bounded context and retries. Model/provider/settings are saved with source
snapshots; results are not merged with historical Groq trials.

These are supporting test records. The single written submission report is
[PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf) at the repository root.

The [baseline model results](results/2026-10-15/BASELINE_MODEL_RESULTS.md) contain 24 live runs,
observed model differences, failure investigation, and retained evidence.
The [reliability fix notes](results/2026-10-15-fixes/RELIABILITY_FIX_NOTES.md) record subsequent
code changes, diagnostic live runs, and the daily quota that limited further testing.

| Supporting record | Purpose |
|---|---|
| [BASELINE_MODEL_RESULTS.md](results/2026-10-15/BASELINE_MODEL_RESULTS.md) | Reviewed original two-model results and failure analysis |
| [BASELINE_RUN_DETAILS.md](results/2026-10-15/BASELINE_RUN_DETAILS.md) | Original machine-generated per-attempt details |
| [RELIABILITY_FIX_NOTES.md](results/2026-10-15-fixes/RELIABILITY_FIX_NOTES.md) | Fixes, diagnostics, and remaining limitations |
| [PILOT_1_RUN_DETAILS.md](results/2026-10-15-fixes/pilot-1/PILOT_1_RUN_DETAILS.md) | First intermediate diagnostic batch |
| [PILOT_2_RUN_DETAILS.md](results/2026-10-15-fixes/pilot-2/PILOT_2_RUN_DETAILS.md) | Second intermediate diagnostic batch |
| [PARTIAL_RETEST_RESULTS.md](results/2026-10-15-free-tier/PARTIAL_RETEST_RESULTS.md) | Latest published quota-paused batch |
| [BASELINE_SETUP_CHECKS.md](BASELINE_SETUP_CHECKS.md) | Historical setup and smoke-check record |
| [FREE_TIER_TESTING_NOTES.md](FREE_TIER_TESTING_NOTES.md) | Historical pacing validation, resume, and syntax validation notes |

New local runs write `TEST_RESULTS.md`. Historical metadata keeps the filenames
that existed when each run was captured; those snapshots are not navigation links.

Run the same fixed tasks through two **real Groq models**, using the production
`GroqProvider`, `BasicAgentLoop`, schema-validating dispatcher, execution policy
in auto mode, and live MCP servers. Each task/model/repeat receives a fresh
workspace and conversation. No scripted provider is used for comparison results.

## Setup and run

### Free-tier limits and resume

For the configured Windows project, this wrapper finds the virtual environment
and loads the saved environment variable without displaying it. Continue
an existing batch created with the current code with:

```powershell
.\scripts\run_model_comparison.ps1 -Resume
```

If capacity is exhausted, the batch saves its results and exits with code **3**.
Wait for capacity, then use the same resume command. For an independent new batch:

```powershell
.\scripts\run_model_comparison.ps1 -OutputDirectory 'evaluations/model_comparison/local/my-new-run'
# Resume that new batch later using the same path:
.\scripts\run_model_comparison.ps1 -Resume -OutputDirectory 'evaluations/model_comparison/local/my-new-run'
```

The default directory is `local/free-tier-validation-live`, containing the earlier
partial live batch. After changing source code, use `-OutputDirectory` with a new
path. The wrapper recovers the saved
configuration path on resume; `-ConfigPath` can choose a configuration for a new
batch. These checkpoints apply only to
new-format runs; historical baseline/pilot folders cannot be resumed.

The equivalent Python command accepts `--resume` with the original `--output`,
models, repeats, scope, config, timeout, and iteration limit.
Source/config hashes and the Python version must match. Changed code needs a new
batch so implementations are not mixed silently. An OS lock prevents two runners
from writing to the same batch. Completed coding or assistant failures are retained
and skipped just like passes. Only provider-blocked slots are retried, in fresh
workspaces, with all prior attempts retained. An interrupted unscored workspace is
also preserved, but its task restarts rather than resuming an agent mid-tool-call.

The runner sends requests without local pacing or a startup reservation on
resume. The former `--tokens-per-minute` / `-TokensPerMinute` options have been
removed. Short API rate-limit responses still produce visible, bounded retries;
the application cannot increase Groq's account limits. Batches recorded before
this change require a new output directory because the source hashes differ.

Explicit provider retry waits do not consume the active task timeout;
reported elapsed time still includes those waits. Provider capacity errors pause
the batch immediately, rather than attempting the remaining tasks against an
exhausted allowance. Daily-cap errors are not retried even with a short wait hint.

Reports distinguish `coding_failure`, `assistant_failure`, and `provider_blocked`.
They retain code-check results and show latest-slot completion, planned coverage,
and the success rate across **all** attempts, including quota-blocked retries.
These are descriptive categories, not a claim that all incomplete code is a
model reasoning error. Inspect the checks and trace together.

Saved Python edits now receive an automatic syntax read/check through the normal
dispatcher and execution policy. Invalid or unverified syntax prevents normal
completion, and feedback allows a later model turn to repair it. This does not
execute generated code or reveal hidden behavioral checks. Behavioral grading
remains independent after each task; valid syntax does not establish correctness.

See [free-tier validation](FREE_TIER_TESTING_NOTES.md) for implementation coverage
and the remaining live-validation limitation.

From the repository root, activate the project's virtual environment:

```powershell
python -m pip install -r requirements-dev.txt -e '.[rag]'
npm ci
python -m rag_server.prepare
python -m rag_server.index
```

Configure `GROQ_API_KEY` in Windows Environment Variables. A terminal opened before
that change may need to load the saved User or Machine variable:

```powershell
$env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'User')
if (-not $env:GROQ_API_KEY) {
    $env:GROQ_API_KEY = [Environment]::GetEnvironmentVariable('GROQ_API_KEY', 'Machine')
}
```

The entire `local/` directory is ignored by Git. Never put credentials in results
or commit them. `--api-key-file` is an optional fallback for a local file containing
only the key; Windows environment variables are sufficient.

```powershell
python -m evaluations.model_comparison.run --models openai/gpt-oss-20b openai/gpt-oss-120b --output evaluations/model_comparison/local/full-run --repeats 3
```

These model IDs are listed in [Groq's model documentation](https://console.groq.com/docs/models).
Confirm both are enabled for your account. Both run through the same provider;
this compares LLMs, and does not compare local versus cloud execution.

The default configuration connects filesystem, DeepWiki, and custom RAG. It
requires internet access, a prepared Chroma index, and cached or downloadable
embedding/reranking models. The RAG subprocess uses the running assistant's Python
interpreter. Use the project virtual environment. See [RAG setup](../../docs/rag-retrieval.md).

For a narrower initial coding comparison, add `--filesystem-only`. This runs
three coding tasks and omits the documentation task and its external/RAG servers.
Record that limitation; a filesystem-only run is not a full integration test.
Use a new `--output` directory for each run; existing runs are never overwritten.
The timeout covers connections and agent work; transport cleanup can extend the
reported elapsed time slightly beyond it.
Exit codes: 0 = all tasks passed; 1 = completed batch with failures; 2 = setup
failed; 3 = saved batch paused because provider capacity is unavailable.

## Tasks and success criteria

| Task | Requested change | Evaluator checks |
|---|---|---|
| bugfix | Repair arithmetic mean and empty-input handling | Multiple values, singleton, negative values, fractions, empty error |
| feature | Extract unique lowercase ASCII words in first-seen order | Case, repeats, ordering, punctuation/digit separators, empty input |
| refactor | Share region aggregation while preserving sales summaries | Existing and arbitrary regions, fractions, negatives, empty input, no input mutation, helper presence |
| documentation | Implement UTF-8 greeting writer using retrieved documentation | File contents/count, overwrite, Path/string paths, non-ASCII name; successful custom-RAG and DeepWiki calls |

Task definitions and checks live in `tasks.py`. Tests remain outside the model's
filesystem root. The evaluator executes generated Python locally in a subprocess
with a 15-second limit, without passing credential environment variables. This is
an evaluation fixture, not an operating-system sandbox. MCP file operations are
restricted to that run's fixture directory.

A pass requires behavioral checks, successful filesystem read and edit calls,
the required integration calls, and normal agent completion. A claimed final
answer alone is insufficient. Recovered tool errors are counted without
automatically failing the task. Every run uses the same prompts except for the
absolute workspace path. Models alternate order between repeats. Sampling and
reasoning settings use the production adapter: temperature 0, GPT-OSS low reasoning,
and 2,048 maximum completion tokens. Current runs include a request-size budget and
bounded provider recovery. These are changes from the original baseline; metadata
records the policy and production source hashes for new runs.

## Evidence and analysis

The output directory contains:

- `metadata.json`: timestamp, revision, task/config hashes, runtime, models,
  repeats, timeout, iteration limit, server scope, and production source hashes.
- `dependencies.txt`: installed Python package versions for reproduction.
- `results.json`: prompts, initial source hashes, discovered tools, streamed
  events, tool arguments/results, errors, completion reason, correctness checks,
  elapsed seconds, timestamped events, and ordered tool calls for every attempted run.
- `workspaces/`: final source files, separated by model, task, and repeat.
- `TEST_RESULTS.md`: generated outcome table, failure evidence, and interpretation limits.

Results are saved after each task so interrupted batches retain completed evidence.
Elapsed time includes server discovery and tool work, but excludes grading; it is
not tokens/second. API token usage and cost are not exposed by the adapter.

Before calling ticket #14 complete, inspect both models' final code and explanations.
Add a written discussion to the retained report: compare success counts, tool
selection, recovery from errors, unnecessary calls, and observed latency. For each
failure, identify the failing check or trace event, distinguish environment/provider
failures from coding failures, and document any diagnostic rerun separately.
For the documentation task, verify retrieved snippets support the claims and
citations; successful tool invocation alone does not prove source grounding.
Do not infer advanced-RAG improvements here; that comparison belongs to ticket #15.

Copy the reviewed report and sanitized supporting results into a tracked results
directory for the team. Include the evaluated revision and any uncommitted changes.
Small synthetic tasks and a few repeats support observations about this task set,
not broad claims that one model is better. A run with unavailable credentials or
servers does not establish model quality.

## Harness validation

```powershell
python -m pytest tests/test_model_comparison.py
python -m mypy
```

These tests check the grading rules and exercise the runner with a scripted
response and the real filesystem server. They validate evaluation plumbing;
they are not evidence that either LLM completed the tasks.
