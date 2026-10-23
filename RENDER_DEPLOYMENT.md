# Deploy to Render

This repository can be deployed as two Render **Web Services** from the same GitHub repository:

1. **API service** — FastAPI endpoints at `/agent`, `/documents/{filename}`, and `/health`.
2. **UI service** — Streamlit interface for entering requests, viewing task results, previewing documents, and downloading DOCX files.

The services run the same agent code independently. The Streamlit UI calls the workflow directly in its own service; it does not proxy its request through the separate FastAPI service.

## Before deploying

- Push the project to a GitHub repository connected to your Render account.
- Ensure the dependency manifest is committed at `app/requirements.txt`.
- Have a valid Groq API key and a model ID available to your Groq account.
- Rotate any API key previously exposed in a chat or commit. Set only the replacement key in Render's environment settings.

**Do not set `app` as the Render Root Directory.** The Python imports expect the repository root to be the working directory. The dependency file happens to be in the `app` folder, so use `app/requirements.txt` in each build command.

## Create the FastAPI service

In the Render dashboard, select **New + → Web Service**, connect this repository, and configure:

| Field | Value |
|---|---|
| Name | `autonomous-document-agent-api` (or another available name) |
| Branch | `main` |
| Root Directory | Leave blank (repository root) |
| Runtime | Python |
| Build Command | `pip install -r app/requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

Add these environment variables in **Environment**:

| Key | Value |
|---|---|
| `GROQ_API_KEY` | Your rotated Groq API key; enter it only in Render's private environment-variable form |
| `GROQ_MODEL` | A model ID currently available to your Groq account |
| `MAX_TASKS` | `8` |
| `MAX_RETRIES` | `1` |
| `MAX_REQUEST_LENGTH` | `10000` |
| `GENERATED_DOCUMENTS_DIR` | `generated_documents` |

Deploy the service. When its status is **Live**, verify:

```text
https://<api-service-name>.onrender.com/health
https://<api-service-name>.onrender.com/docs
```

The health response should show `"status":"ok"`. It reports configuration presence, not whether Groq credentials or quota have been tested. Submit a short request from `/docs` to test the live LLM integration.

## Create the Streamlit service

Create a second **Web Service** from the same repository and branch:

| Field | Value |
|---|---|
| Name | `autonomous-document-agent-ui` (or another available name) |
| Branch | `main` |
| Root Directory | Leave blank (repository root) |
| Runtime | Python |
| Build Command | `pip install -r app/requirements.txt` |
| Start Command | `streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port $PORT --server.headless true` |

Add the **same environment variables** to the UI service, including the Groq key and model. Each Render service has its own environment settings; variables on the API service are not automatically shared with the UI service.

After deployment, open:

```text
https://<ui-service-name>.onrender.com
```

Enter a request or select a demo, click **Create document**, inspect the execution results, then preview and download the generated Word document.

## Generated document persistence

By default, files are written to `generated_documents` on the service filesystem. Render's ordinary service filesystem is ephemeral: generated files may be lost after a restart or redeploy. Download documents promptly after generation.

The Streamlit interface generates and serves its document within the UI service itself. The API service has a separate filesystem and a separately generated artifact directory. A filename created by the UI service is therefore not automatically available from the API service's `/documents/{filename}` endpoint.

If you need durable document storage, attach and configure a persistent disk on a Render plan that supports it, and set `GENERATED_DOCUMENTS_DIR` to the disk's mounted path. For shared documents across the UI and API services, use an external object store or a shared persistence design; two separate instance filesystems are not shared.

## Security and operational notes

- Never commit `.env`, paste a Groq key into source code, or place a secret in a build/start command.
- Store secrets as Render environment variables and restrict dashboard access.
- The current API does not implement user authentication or per-user authorization. Anyone who can reach the public service can submit requests and consume your Groq quota. Add authentication or otherwise restrict access before using it beyond a controlled demo.
- Set Groq usage limits/alerts where available and monitor Render logs and Groq usage during demonstrations.
- Both services may experience cold starts on free or scaled-to-zero plans. Wait for the service to become **Live** before presenting.
- The app retries only a small number of recognized transient errors. An upstream quota, invalid credential, or unavailable model should produce a reported error, not a fabricated document.

## Troubleshooting

### Build fails because a requirements file is not found

Confirm **Root Directory** is blank and the build command is exactly:

```text
pip install -r app/requirements.txt
```

### Application fails to import `app`

The Render Root Directory was probably set to the `app` folder. Clear it so the process starts from the repository root.

### `/health` is available but generation fails

Verify that both `GROQ_API_KEY` and `GROQ_MODEL` are set on the service receiving the request, the key is valid, the model is enabled for the account, and the account has available quota. Review service logs for the execution ID; never share secret values in logs or screenshots.

### UI opens but generation fails

Set the Groq and agent environment variables on the **UI service**, not only on the API service. The UI executes the workflow locally within its own service.

### Downloaded files disappear

This is expected on an ephemeral filesystem after restart/redeploy. Download files immediately or configure persistent/object storage as described above.
