# Final architecture and workflow diagrams

The original planning diagram is preserved in [its original PDF](../init-architecture.drawio2.pdf)
and on page 5 of [PROJECT_REPORT.pdf](../PROJECT_REPORT.pdf). The updated component
diagram and the reasons for changes are on page 6. Pages 7-10 contain static vector
versions of the state and three sequence diagrams below. These describe implemented
control flow and example tool choices; they are not recorded successful live runs.

## State diagram: one task in the interactive session

```mermaid
stateDiagram-v2
    [*] --> Connect: load config
    Connect --> Ready: connect servers / discover tools
    Connect --> Exit: connection error
    Ready --> Model: user task / retain history
    Model --> Model: bounded provider recovery
    Model --> Validate: model requests tools
    Model --> Finish: final text / no tool calls
    Model --> Failed: provider error or iteration limit
    Validate --> Observe: unknown name / invalid arguments
    Validate --> Approval: valid call / confirm mode
    Validate --> Execute: valid call / auto mode
    Approval --> Execute: user approves
    Approval --> Observe: reject or EOF / tool_rejected
    Execute --> Observe: MCP result or tool error
    Observe --> SyntaxRead: Python file was edited
    SyntaxRead --> Observe: policy-controlled read / parse result
    Observe --> Model: append results / next iteration
    Finish --> Failed: unresolved Python syntax validation
    Finish --> Ready: completed(answered)
    Failed --> Ready: show failure
    Ready --> Exit: exit / interrupt / EOF
    Exit --> [*]: close all MCP clients
```

Syntax validation runs once after each edited path in a tool batch, not recursively
after its own read. Rejected or failed reads leave syntax unverified. The 40-step
agent limit and bounded Groq retries prevent unbounded model/tool loops.

## Operation 1: inspect and explain existing code (confirmation)

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Agent
    participant LLM
    participant Tools as Dispatcher / policy / MCP client
    participant FS as Filesystem MCP
    User->>CLI: Explain solution.py
    CLI->>Agent: run(task)
    Agent->>Tools: Discover schemas
    Tools-->>Agent: Qualified tool definitions
    Agent->>LLM: Messages + tools
    LLM-->>Agent: Select read_text_file(path)
    Agent->>Tools: Validate name and arguments
    Tools->>CLI: Request approval / display tool
    CLI->>User: Execute tool? [y/N]
    User-->>CLI: yes
    CLI-->>Tools: Approve this call
    Tools->>FS: MCP call_tool
    FS-->>Tools: Existing code
    Tools-->>Agent: Retain complete tool result
    Agent->>LLM: Observe code / next step
    LLM-->>Agent: Stream explanation / no tools
    Agent-->>CLI: Text + completed(answered)
    CLI-->>User: Done / next prompt
```

Rejection follows the state diagram's `tool_rejected` branch without an FS call.

## Operation 2: repair a Python bug (automatic)

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Agent
    participant LLM
    participant Tools as Dispatcher / auto policy / MCP
    participant FS as Filesystem MCP
    participant Checks as Python-check MCP
    User->>CLI: Fix mean and empty-input handling
    CLI->>Agent: run(task)
    Agent->>LLM: Task + discovered tool schemas
    LLM-->>Agent: Select filesystem read
    Agent->>Tools: Validate / auto permit
    Tools->>FS: Read existing source
    FS-->>Agent: Tool result via MCP client
    Agent->>LLM: Observe existing source
    LLM-->>Agent: Select edit_file or write_file
    Agent->>Tools: Validate / auto permit
    Tools->>FS: Save repaired source
    FS-->>Agent: Edit result via MCP client
    Agent->>Tools: Policy-controlled read of edited Python path
    Tools->>FS: Read saved text
    FS-->>Agent: Source via MCP client
    Note over Agent: Parse syntax locally / retain feedback
    Agent->>LLM: Observe edit and syntax results
    LLM-->>Agent: Select checks.run_python_check(path, mode=pytest)
    Agent->>Tools: Validate / auto permit
    Tools->>Checks: Execute workspace tests / bounded duration
    Checks-->>Agent: Exit status and output via MCP client
    Agent->>LLM: Observe behavioral checks / repair or finish
    LLM-->>Agent: Final explanation
    Agent-->>CLI: Complete if syntax verified
    CLI-->>User: Result / next prompt
```

Invalid saved syntax is fed back for repair. Unresolved syntax prevents normal
completion. The separate check tool executes trusted workspace code; tests prove
only the behavior they actually check. This tool was added after the historical
coding comparison, whose evaluator-owned tests were separate.

## Operation 3: documentation-assisted feature (confirmation)

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Agent
    participant LLM
    participant Tools as Dispatcher / policy / MCP
    participant FS as Filesystem MCP
    participant RAG as Custom RAG MCP
    participant Wiki as DeepWiki MCP
    User->>CLI: Implement a feature using local and external docs
    CLI->>Agent: run(task) / discover configured servers
    Agent->>LLM: Task + tool schemas
    LLM-->>Agent: Select filesystem read
    Agent->>Tools: Validate / request per-call approval
    Tools->>CLI: Show tool and arguments / ask User
    User-->>CLI: yes
    CLI-->>Tools: Approve
    Tools->>FS: Read existing code
    FS-->>Agent: Tool result via client
    Agent->>LLM: Observe code
    LLM-->>Agent: Select rag.search_docs
    Agent->>Tools: Validate + per-call approval through CLI
    Tools->>RAG: stdio call_tool search_docs
    Note over RAG: Query embedding / Chroma candidates / cross-encoder
    RAG-->>Agent: Original text + source/page/chunk IDs
    Agent->>LLM: Observe retrieved passages
    LLM-->>Agent: Select deepwiki.ask_wiki_question for missing API detail
    Agent->>Tools: Validate + per-call approval through CLI
    Tools->>Wiki: HTTP MCP call / public repo question
    Wiki-->>Agent: External documentation answer
    Agent->>LLM: Observe combined evidence
    LLM-->>Agent: Select filesystem edit
    Agent->>Tools: Validate + per-call approval through CLI
    Tools->>FS: Save feature
    FS-->>Agent: Edit result
    Agent->>Tools: Approved read-back for Python syntax validation
    Tools->>FS: Read saved source
    FS-->>Agent: Source / parse feedback
    Agent->>LLM: Observe changes and validation
    LLM-->>Agent: Final explanation with citations
    Agent-->>CLI: Text + completed(answered)
    CLI-->>User: Done / next prompt
```

All valid calls require approval in confirmation mode, including retrieval and
syntax-check reads. The model selects order and tools; a real run can instead
decline, fail, or need more iterations. DeepWiki is hosted; filesystem and RAG
are local stdio processes. A fourth local stdio server executes Python checks, as
shown in operation 2. No arbitrary shell interface is exposed by this configuration.
