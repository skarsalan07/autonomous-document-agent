# Autonomous Document Agent

A single-agent Python service that accepts a natural-language document request, asks a Groq-hosted language model for a validated execution plan, executes only registered Python tools, drafts structured content, and creates a checked Microsoft Word document.

The live workflow requires a Groq API key and a model name enabled for your account. No LLM response is mocked in normal application execution. Unit tests use controlled dependency injection and do not contact Groq.

## Features

- FastAPI endpoints for agent execution, health checks, and DOCX downloads.
- LangChain structured output for both execution plans and document drafts.
- Pydantic validation of tasks, tool allowlists, dependencies, and content sections.
- Sequential execution with explicit `pending`, `running`, `completed`, `failed`, and `skipped` states.
- Bounded retries for recognized transient upstream failures only.
- Editable, formatted DOCX output with heading styles, bullets, tables, metadata, and page numbers.
- Deterministic artifact checks for file validity, content, title, outline headings, placeholders, and size.
- Two runnable demonstration requests in `demo_requests.json`.

## Architecture

```text
FastAPI (app/main.py)
  -> reusable workflow (app/agent.py)
     -> Groq plan generation and validation (app/planner.py)
     -> dependency-aware registered-tool executor (app/executor.py)
        -> analysis, local context, outline, drafting, generation, validation (app/tools.py)
     -> DOCX formatting (app/document_generator.py)
     -> artifact checks (app/quality_checker.py)
```

The LLM returns the request-specific task list and outline. Python validates task IDs, the registered tool names, task dependencies, cycles, task limits, and mandatory document-production stages before executing anything. No model-generated Python, shell commands, or filesystem paths are executed.

`research_context` returns clearly labeled deterministic local guidance; it does not browse the web. Cost ranges and other estimates in the document are illustrative unless supplied by the user.

## Agent workflow and engineering improvement: multi-step planning

A dynamically generated plan is more flexible than asking one prompt to write the whole document: the request can drive an appropriate document type, audience, outline, assumptions, and optional research/context steps. Pydantic validates the structured plan, while `planner.validate_plan` checks tool permissions, task limits, dependency references, cycles, and required document stages.

The executor selects a task only after its dependencies complete. It resolves tools from the explicit registry and passes completed results through a per-execution context to later operations. Tool execution remains deterministic even though the plan is adaptive. Only recognized transient upstream errors are retried, and only up to `MAX_RETRIES` times after the initial attempt. Invalid plans, validation errors, and other permanent failures are not retried.

On failure, the task is marked failed; its dependent tasks are skipped, and independent ready tasks may continue. A document download URL is returned only when the generated file passes deterministic checks. This is a single-agent architecture: one LLM plans and drafts, while Python controls permissions, ordering, retries, and artifact validation.

## Project structure

```text
app/
  agent.py
  config.py
  document_generator.py
  exceptions.py
  executor.py
  main.py
  planner.py
  quality_checker.py
  schemas.py
  tools.py
generated_documents/
tests/
app/requirements.txt
streamlit_app.py
.env.example
demo_requests.json
```

## Prerequisites

- Python 3.11 or later (Python 3.13 is a good choice).
- A Groq API key and a model name currently enabled for your Groq account.
- Internet connectivity for the live Groq planning and drafting calls.

Set up from Windows PowerShell in the project directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r app\requirements.txt
Copy-Item .env.example .env
```

Render deployment steps for the FastAPI and Streamlit services are in [RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md).

If `py -3.13` is unavailable, replace it with the command for another installed Python 3.11+ interpreter. If PowerShell blocks activation for this terminal, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again.

Edit `.env` and set:

```dotenv
GROQ_API_KEY=the_key_from_your_groq_account
GROQ_MODEL=the_model_id_available_to_your_account
```

The application deliberately does not guess a model ID because availability varies by account and changes over time. The key is read from the environment and is never returned in API responses or written to application logs. Keep `.env` private; it is ignored by Git.

Other settings can be adjusted in `.env`:

| Setting | Default | Meaning |
|---|---:|---|
| `MAX_TASKS` | `8` | Maximum plan size (4–20) |
| `MAX_RETRIES` | `1` | Retries after the initial attempt (0–3) |
| `MAX_REQUEST_LENGTH` | `10000` | Maximum request characters (100–50000) |
| `GENERATED_DOCUMENTS_DIR` | `generated_documents` | Generated artifact directory |

## Start the API

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Open Swagger UI at <http://127.0.0.1:8000/docs>. Health is available at <http://127.0.0.1:8000/health>.

## Use the Streamlit interface

The Streamlit page provides a text box for your request, optional selectors that load either demonstration request, a task-by-task execution view, document quality checks, an in-page text preview, and a DOCX download button. It calls the same agent workflow directly, so you do not need the FastAPI server running to use this UI.

In another PowerShell terminal from the project directory:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run streamlit_app.py
```

Open <http://localhost:8501>, enter your own document request (or select a demo), and click **Create document**. Keep the FastAPI server command above only if you also want to use the REST API at `/docs`.

## Run the demos

In Swagger UI, choose `POST /agent` and paste either request below. The same exact strings are stored in `demo_requests.json`.

### Demo 1: Standard business request

> Create a professional project implementation plan for launching an AI-powered customer support chatbot for a mid-sized e-commerce business. Include project objectives, scope, architecture, implementation phases, timeline, team responsibilities, risks, estimated budget assumptions, success metrics, and next steps. Clearly label any assumptions and use illustrative estimates rather than claiming they are verified.

### Demo 2: Complex, ambiguous request

> Prepare a technical and business proposal for a company that wants to automate its customer support using AI. The company has a limited budget, wants to launch quickly, has an existing support team, and is concerned about data privacy and inaccurate AI answers. No budget amount, deadline, technology stack, or company size has been provided. Decide what information is missing, make reasonable assumptions instead of blocking unnecessarily, compare a simple RAG-based approach with a more advanced agentic approach, recommend a practical phased implementation, and explain the trade-offs, risks, estimated costs, evaluation metrics, and rollout plan.

PowerShell can load both examples from the JSON file and submit each:

```powershell
$demo = Get-Content .\demo_requests.json -Raw | ConvertFrom-Json
$body1 = @{ request = $demo[0].request } | ConvertTo-Json
$result1 = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/agent -ContentType 'application/json' -Body $body1
$result1 | ConvertTo-Json -Depth 10

$body2 = @{ request = $demo[1].request } | ConvertTo-Json
$result2 = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/agent -ContentType 'application/json' -Body $body2
$result2 | ConvertTo-Json -Depth 10
```

The successful response includes a generated filename and `download_url`. Download the artifact using:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/documents/<filename-from-response> -OutFile .\generated-plan.docx
```

Only generated filenames in the configured document directory are accepted.

## API and error behavior

- `POST /agent` accepts `{"request": "..."}`. Pydantic rejects missing, blank, or over-limit requests with `422`.
- A successful workflow returns `200`, the validated plan and task results, task counts, quality checks, document metadata, and a download URL.
- A failed workflow returns a truthful non-2xx response. Planning/upstream/configuration problems return structured errors with an execution ID; incomplete execution returns the execution summary and failure states rather than a successful download URL.
- Missing documents return `404`; invalid filenames (including traversal-shaped names) return `400`.
- `GET /health` reports application/version and whether the Groq settings are configured. It does not test or reveal credentials.
- Unexpected server exceptions are logged with an execution ID; internal stack traces and credentials are not exposed to the caller.

## Tests

Run all automated tests from an activated virtual environment:

```powershell
python -m pytest -q
```

The tests cover request validation, plan/tool/dependency checks, dependency-ordered execution, failure states, retry boundaries, DOCX generation/reopening, quality checks, health, and download guards. They do not make live Groq calls. A live integration can be verified by configuring `.env`, starting the server, and submitting either demonstration request through `/docs`.

## Video demonstration outline (8–10 minutes)

### Part A — Live demo (3–4 minutes)

1. Start the API and open `/docs`.
2. Submit Demo 1; show terminal planning/task logs and the response plan.
3. Download and open its DOCX.
4. Submit Demo 2; show how missing information, assumptions, and the plan differ.
5. Point out its successful quality-check results and download link.

Prepare request text in advance and avoid spending the video waiting for an LLM response.

### Part B — What was built (2–3 minutes)

Explain the FastAPI request lifecycle and the responsibilities of `planner.py`, `executor.py`, `tools.py`, `document_generator.py`, and `quality_checker.py`. Demonstrate that LangChain calls Groq for actual planning and drafting; Python validates and runs only registered tools.

### Part C — Debugging insight (1–2 minutes)

Use an observed issue from your own run. For example, if a Groq structured response fails Pydantic validation, show the actual validation error, explain that the model response did not meet the declared schema, and demonstrate the resulting truthful planning error. Do not claim an issue occurred unless it happened during your implementation or demo.

### Part D — Engineering trade-off (1–2 minutes)

Explain that LLM planning offers request-specific flexibility, while deterministic Python execution provides explicit tool permissions, dependency order, retry limits, and artifact verification. The design is easier to reason about than autonomous code execution, but its plan/draft quality depends on the configured model and it does not conduct external research.

## Known limitations and future improvements

- No external search, vector database, persistent memory, background job queue, or multi-agent orchestration is implemented.
- The synchronous API request remains open while Groq generates the plan and draft.
- Groq quotas, authentication, model availability, and account-specific structured-output support can affect live calls; use a currently available model ID in `.env`.
- The local knowledge base is deterministic guidance, not factual research.
- Quality checks are deterministic structural/content checks, not a guarantee that every business recommendation is correct.
- Future work could add authenticated users, cleanup/retention policies, external-source citations, request-level timeouts, and a lightweight human review step.
