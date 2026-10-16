# OpenAI provider

Juniper supports OpenAI alongside Groq and Ollama. Set `OPENAI_API_KEY` in your environment and ensure your API project has billing/credits. Never commit or paste the key into a task. On Windows the provider also reads a saved User or System environment variable when the terminal was opened before the key was saved.

Launch from the project directory:

```powershell
.\.venv\Scripts\coding-assistant.exe --provider openai
```

The default model is `gpt-5.4-mini`. Override it with `$env:OPENAI_MODEL = 'your-model-id'`. The startup banner displays the active provider and model. Use `--execution-mode auto` only when you want tools to execute without individual confirmations. Tool requests on GPT-5.4 mini/nano use `reasoning_effort="none"` for Chat Completions compatibility.

The adapter uses the official OpenAI SDK and streamed Chat Completions. It reuses Juniper's chat-format conversion, bounded context, tool aliases, optional-null cleanup, and repeated-read finalization. Tool dispatch still validates original MCP schemas and follows the selected execution policy. No Groq calls or Groq-specific request options are sent by this provider.

Temporary connection, rate-limit, and server errors get at most two retries, with waits capped at 30 seconds each. Insufficient credits stop immediately with a billing message. A partially emitted response is never replayed. Completed edits remain on disk after an API failure. API access and limits depend on your OpenAI project.

Official references: [model](https://developers.openai.com/api/docs/models/gpt-5.4-mini), [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
