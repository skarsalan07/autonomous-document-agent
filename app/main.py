"""FastAPI endpoints for agent execution, health, and safe document downloads."""

import logging
import re
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

from app.agent import run_agent
from app.config import Settings, get_settings
from app.exceptions import ConfigurationError, PlanningError, RetryableOperationError
from app.schemas import AgentRequest, AgentResponse, ErrorResponse

logger = logging.getLogger(__name__)
FILENAME_PATTERN = re.compile(r"^document-[0-9a-f]{32}\.docx$")


def create_app(
    settings: Settings | None = None,
    workflow: Callable[..., AgentResponse] | None = None,
) -> FastAPI:
    """Create an app instance; workflow injection is intended for isolated tests."""
    configured = settings or get_settings()
    agent_workflow = workflow or run_agent
    application = FastAPI(title="Autonomous Document Agent", version="1.0.0")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": application.version, "llm": "configured" if configured.groq_api_key and configured.groq_model else "not_configured"}

    @application.post("/agent", response_model=AgentResponse)
    def create_document(payload: AgentRequest) -> JSONResponse:
        execution_id = str(uuid4())
        if len(payload.request) > configured.max_request_length:
            raise HTTPException(
                status_code=422,
                detail={"execution_id": execution_id, "error": "invalid_request", "message": "Request exceeds the configured maximum length."},
            )
        logger.info("execution_id=%s request_received", execution_id)
        try:
            result = agent_workflow(payload.request, configured, execution_id)
        except ConfigurationError as exc:
            return _error_response(503, execution_id, "configuration_error", str(exc))
        except RetryableOperationError:
            return _error_response(503, execution_id, "upstream_unavailable", "The Groq service was temporarily unavailable after bounded retries.")
        except PlanningError as exc:
            logger.warning("execution_id=%s planning_failed type=%s", execution_id, type(exc).__name__)
            return _error_response(502, execution_id, "planning_failed", str(exc))
        except Exception as exc:
            logger.exception("execution_id=%s unexpected_agent_failure type=%s", execution_id, type(exc).__name__)
            return _error_response(500, execution_id, "internal_error", "The request could not be completed.")
        if result.status != "completed":
            return JSONResponse(status_code=502, content=result.model_dump(mode="json"))
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    @application.get("/documents/{filename}")
    def download_document(filename: str) -> FileResponse:
        if not FILENAME_PATTERN.fullmatch(filename):
            raise HTTPException(status_code=400, detail="Invalid document filename.")
        root = configured.generated_documents_dir.resolve()
        target = (root / filename).resolve()
        if target.parent != root:
            raise HTTPException(status_code=400, detail="Invalid document filename.")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Document not found.")
        try:
            from docx import Document

            Document(target)
        except Exception as exc:
            logger.warning("Rejected invalid generated document filename=%s type=%s", filename, type(exc).__name__)
            raise HTTPException(status_code=404, detail="Document not found.") from exc
        return FileResponse(
            path=target,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=filename,
        )

    @application.exception_handler(HTTPException)
    async def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            content = exc.detail
        else:
            content = {"error": "http_error", "detail": exc.detail}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        execution_id = str(uuid4())
        errors = [
            {"location": error.get("loc", []), "message": error.get("msg", "Invalid request.")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"execution_id": execution_id, "error": "invalid_request", "detail": errors},
        )

    return application


def _error_response(status_code: int, execution_id: str, error: str, detail: str) -> JSONResponse:
    body = ErrorResponse(execution_id=execution_id, error=error, detail=detail)
    return JSONResponse(status_code=status_code, content=body.model_dump())


app = create_app()
