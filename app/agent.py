"""Reusable orchestration service for the autonomous document agent."""

import logging
from uuid import uuid4

from app.config import Settings, get_settings
from app.executor import execute_plan
from app.planner import generate_plan
from app.schemas import (
    AgentResponse,
    DocumentMetadata,
    ExecutionSummary,
    QualityCheck,
    QualityResult,
    TaskResult,
    TaskStatus,
)

logger = logging.getLogger(__name__)


def run_agent(request: str, settings: Settings | None = None, execution_id: str | None = None) -> AgentResponse:
    """Plan, execute, and verify one document-generation request."""
    settings = settings or get_settings()
    execution_id = execution_id or str(uuid4())
    logger.info("execution_id=%s request_received length=%s", execution_id, len(request))
    plan = generate_plan(request, settings)
    logger.info(
        "execution_id=%s planning_completed task_count=%s document_type=%s",
        execution_id, len(plan.tasks), plan.document_type,
    )
    task_results = execute_plan(plan, request, execution_id, settings)
    tasks_by_tool = {task.tool_name: task for task in task_results}
    generated = tasks_by_tool.get("generate_document")
    validation = tasks_by_tool.get("validate_document")
    quality = _quality_result(validation)
    completed_count = sum(task.status == TaskStatus.COMPLETED for task in task_results)
    failed_count = sum(task.status == TaskStatus.FAILED for task in task_results)
    skipped_count = sum(task.status == TaskStatus.SKIPPED for task in task_results)
    summary = ExecutionSummary(
        total_tasks=len(task_results),
        completed_tasks=completed_count,
        failed_tasks=failed_count,
        skipped_tasks=skipped_count,
    )

    document: DocumentMetadata | None = None
    if (
        generated is not None
        and generated.status == TaskStatus.COMPLETED
        and generated.result
        and quality.passed
    ):
        filename = generated.result["filename"]
        document = DocumentMetadata(
            filename=filename,
            size_bytes=int(generated.result["size_bytes"]),
            download_url=f"/documents/{filename}",
        )
    complete = document is not None and completed_count == len(task_results)
    status = "completed" if complete else ("partial_failure" if completed_count else "failed")
    message = (
        "The document was generated and validated successfully."
        if complete
        else "The workflow did not produce a document that passed all deterministic quality checks."
    )
    logger.info(
        "execution_id=%s workflow_status=%s completed=%s failed=%s skipped=%s quality_passed=%s",
        execution_id, status, completed_count, failed_count, skipped_count, quality.passed,
    )
    return AgentResponse(
        execution_id=execution_id,
        status=status,
        request=request,
        document_type=plan.document_type,
        plan=task_results,
        execution_summary=summary,
        quality_check=quality,
        document=document,
        message=message,
    )


def _quality_result(validation: TaskResult | None) -> QualityResult:
    if validation and validation.result:
        return QualityResult.model_validate(validation.result)
    return QualityResult(
        passed=False,
        checks=[QualityCheck(
            name="document_validation",
            passed=False,
            details=validation.error_message if validation and validation.error_message else "Document validation did not complete.",
        )],
        character_count=0,
        file_size_bytes=0,
    )
