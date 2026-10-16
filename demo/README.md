# Two-task Juniper video demo

These are deliberately unfinished fixtures. Juniper should complete them during
the recording. The checks currently fail; the repository's normal tests do not
collect these check scripts. The prompts below match this computer's project path.

## Prepare

Open PowerShell in `C:\Users\bdods\Documents\ChatGPT\Group Project 2`.
Ensure the normal project setup, Groq key, local RAG index, and model downloads
are ready as described in the root README. Use a new Juniper process to load
the removal of automatic pacing. Actual provider rate-limit errors can still wait.

To restore the two unfinished implementations before a rehearsal or new take:

```powershell
.\.venv\Scripts\python.exe .\demo\reset_demo.py
```

This explicitly overwrites `demo/task1_cart/cart.py` and
`demo/task2_export/exporter.py`, including any solutions from a previous take.

Launch:

```powershell
.\.venv\Scripts\coding-assistant.exe --provider groq --execution-mode auto
```

Paste each task as one prompt. Wait for its final response before the next task.
If the conversation becomes large, exit and relaunch before task 2.

## Task 1: repair cart calculations

Paste:

```text
Fix calculate_total in C:\Users\bdods\Documents\ChatGPT\Group Project 2\demo\task1_cart\cart.py. Read that file and C:\Users\bdods\Documents\ChatGPT\Group Project 2\demo\task1_cart\check_cart.py. Use checks.run_python_check in script mode on check_cart.py to show the failure before editing. Calculate price times quantity, apply discount_percent to the subtotal, then apply tax_percent to the discounted amount, and round the final result to two decimal places. Empty carts return zero. Negative prices, non-positive or non-integer quantities, discounts outside 0-100, and negative tax rates must raise ValueError. Preserve the input and public function signature. Only edit cart.py; do not edit the checks. Run check_cart.py again using checks.run_python_check in script mode, fix any remaining failures, and summarize the result. Use the exact paths above without searching the workspace.
```

Capture the initial failure, filesystem reads/edits, and the final
`ALL CART CHECKS PASSED` output with a successful exit status.

## Task 2: implement documentation-assisted order export

Paste:

```text
Implement export_orders in C:\Users\bdods\Documents\ChatGPT\Group Project 2\demo\task2_export\exporter.py. Read it and C:\Users\bdods\Documents\ChatGPT\Group Project 2\demo\task2_export\check_export.py. Before editing, call rag.search_docs with query "Python pathlib create parent directories and write UTF-8 text files", top_k=3, mode="rerank". Also call deepwiki.ask_wiki_question for repoName="python/cpython" asking how pathlib creates parent directories and writes UTF-8 text using exclusive creation to avoid overwriting existing files. Then implement the feature: accept a string or Path output directory, create missing parents, and write each complete order as UTF-8 JSON named <id>.json, preserving readable Unicode. IDs must be nonempty strings containing only ASCII letters, digits, underscores, or hyphens; otherwise raise ValueError. Return Path objects in input order. Empty input still creates the directory and returns []. Raise FileExistsError rather than overwrite an existing export. Preserve input orders. Only edit exporter.py; do not edit the checks. Run check_export.py using checks.run_python_check in script mode and fix failures. Finish with the check result and a brief explanation of what the retrieved sources actually support, including source identifiers. Use the exact file paths without searching the workspace.
```

Capture successful calls and returned results from `rag.search_docs`,
`deepwiki.ask_wiki_question`, and the filesystem tools, plus
`ALL EXPORT CHECKS PASSED` and a successful exit status.

The external tool's schema is dynamically discovered. If its argument names differ,
Juniper should use the supplied schema. Local snippets may only partly support
the feature; the final explanation should acknowledge gaps and use the external
documentation for missing details. A connection banner alone does not demonstrate
that a server was invoked.

## Finish

Show both completed files or their changes and the passing check output. These
are suggested demo tasks, not a guarantee that a live model completes them in one
attempt. Rehearse before recording. A provider error, failed check, or exhausted
eight-step task is not a completed task; resolve it and repeat the take.
