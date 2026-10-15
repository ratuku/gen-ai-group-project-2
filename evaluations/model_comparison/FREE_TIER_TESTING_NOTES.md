# Free-tier testing notes

Supporting test record. The single submission report is [PROJECT_REPORT.pdf](../../PROJECT_REPORT.pdf).

The application now paces requests, checkpoints evaluation batches, and checks
saved Python syntax. None of these changes raises Groq's account limits or
guarantees correct model-generated logic. No paid plan or billing change is needed.

## Implemented and checked

| Change | Verification |
|---|---|
| Rolling estimated per-model token reservations and request spacing | Simulated-clock test checks minute-window enforcement, short progress updates, and request spacing without API calls |
| Cancellation while waiting | Cancelled pacing sends no API request and closes the SDK client |
| Daily quota stops promptly | A daily-limit response is not retried even when its retry hint is short; the structured error reaches the agent |
| Batch pauses on exhausted provider capacity | Runner test verifies exit code 3, checkpoint persistence, and no further task attempts |
| Resume skips completed passes and genuine failures | Runner test retains a coding failure, retries only the blocked slot, preserves all attempt records, and finishes the remaining plan |
| Existing evidence cannot be overwritten silently | Atomic result writes, OS output lock, code/config/settings checks, saved-source hash verification, and fresh retry workspaces |
| Interrupted work is preserved | Cancellation/resume test leaves both unscored partial workspaces intact; the incomplete task starts fresh |
| Python syntax feedback comes from saved source | Real filesystem MCP tests show invalid indentation either repaired on a later turn or blocking normal completion |
| Validation follows permissions | Denied automatic read never reaches the underlying client and produces unverified syntax, not a pass |
| Pacing does not consume the active coding deadline | A real filesystem-server test finishes the model turn after an explicit wait longer than the active timeout |
| Provider blocks remain visible in scores | Reports show latest task-slot completion, planned coverage, and all-attempt completion, retaining blocked attempts and failed code checks |

The full regression suite passed **242 tests**; strict type checking passed for
**59 files**. These checks include scripted providers and real filesystem MCP
transport. They are implementation validation, not a live LLM success-rate result.

## Partial live validation on October 15

The new production implementation ran against both selected Groq models with
all three MCP servers. **Both models passed the same bug-fix task end to end**,
including independent behavioral grading and the automatic saved-syntax check.
The next slot, 20B's feature task, encountered the daily allowance before any
tool calls. The runner saved its evidence and paused with exit code 3, leaving
five slots unattempted. There were no coding or assistant failures in the three
attempted slots, but the feature's unchanged stub still failed its code checks.

That is **2/3 attempted slots, 2/8 planned slots**, with one provider block.
This partial batch does not establish a complete new success rate or a general
model ranking. The original 3/8 and 2/8 pilots remain separate evidence.

Sanitized [live evidence](results/2026-10-15-free-tier/PARTIAL_RETEST_RESULTS.md) includes results,
metadata, state, saved code, dependencies, and source hashes. Raw checkpoints are
in the ignored `local/free-tier-validation-live` directory. After quota is
available, continue from the project directory with:

```powershell
.\scripts\run_model_comparison.ps1 -Resume
```

The wrapper retrieves the saved local configuration path and keeps completed
slots. It uses only the configured account and makes no billing changes.

## External and remaining limitations

Groq controls organization quotas, capacity, and service availability. The pacer
uses an approximate token estimate, does not know other programs' requests, and
cannot guarantee that a request avoids 429. Daily exhaustion requires waiting for
available allowance. The application does not switch models or providers silently.

Syntax validation does not execute generated code, prove semantic correctness,
or replace project tests. The evaluator's behavioral checks remain independent
and are not supplied to the model for repair. Saved code can parse and still fail.

The original baseline and two intermediate pilots remain separate. A new batch
is required for these changes; older reports cannot be resumed with the new runner.
See [run/resume instructions](README.md#free-tier-pacing-and-resume).
