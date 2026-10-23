"""Deterministic sequential orchestration of the validated plan."""

import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.exceptions import ConfigurationError, RetryableOperationError
from app.schemas import ExecutionPlan, TaskResult, TaskStatus
from app.tools import ToolContext, TOOL_REGISTRY

logger = logging.getLogger(__name__)


def execute_plan(plan: ExecutionPlan, request: str, execution_id: str, settings: Settings | None = None) -> list[TaskResult]:
    """Execute ready tasks, retry only known transient failures, and skip blocked tasks."""
    settings = settings or get_settings()
    context = ToolContext(request=request, plan=plan, execution_id=execution_id)
    completed: set[str] = set()

    while any(task.status == TaskStatus.PENDING for task in plan.tasks):
        ready = [
            task for task in plan.tasks
            if task.status == TaskStatus.PENDING and set(task.dependencies).issubset(completed)
        ]
        if not ready:
            for task in plan.tasks:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.SKIPPED
                    task.error_message = "A dependency did not complete."
            break

        task = ready[0]
        if any(plan_task.task_id in task.dependencies and plan_task.status != TaskStatus.COMPLETED for plan_task in plan.tasks):
            task.status = TaskStatus.SKIPPED
            task.error_message = "A dependency did not complete."
            continue

        task.status = TaskStatus.RUNNING
        logger.info("execution_id=%s task_id=%s tool=%s status=running", execution_id, task.task_id, task.tool_name)
        tool = TOOL_REGISTRY[task.tool_name]
        for attempt in range(settings.max_retries + 1):
            context.task_attempts[task.task_id] = attempt + 1
            try:
                result = tool(context)
                if not isinstance(result, dict):
                    raise TypeError("Registered tools must return an object.")
                context.results[task.task_id] = result
                context.results_by_tool[task.tool_name] = result
                task.result = result
                if task.tool_name == "validate_document" and result.get("passed") is False:
                    task.status = TaskStatus.FAILED
                    task.error_message = "The generated document did not pass deterministic quality checks."
                    logger.error("execution_id=%s task_id=%s status=failed quality_check_failed", execution_id, task.task_id)
                else:
                    task.status = TaskStatus.COMPLETED
                    completed.add(task.task_id)
                    logger.info("execution_id=%s task_id=%s status=completed attempts=%s", execution_id, task.task_id, attempt + 1)
                break
            except RetryableOperationError as exc:
                if attempt < settings.max_retries:
                    logger.warning(
                        "execution_id=%s task_id=%s retry=%s/%s reason=%s",
                        execution_id, task.task_id, attempt + 1, settings.max_retries, type(exc).__name__,
                    )
                    time.sleep(min(0.25 * (attempt + 1), 1.0))
                    task.status = TaskStatus.RUNNING
                    continue
                task.status = TaskStatus.FAILED
                task.error_message = str(exc)
            except ConfigurationError:
                raise
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error_message = _safe_error_message(exc)
                break
            if task.status == TaskStatus.FAILED:
                logger.error("execution_id=%s task_id=%s status=failed error=%s", execution_id, task.task_id, task.error_message)

    return [
        TaskResult(
            task_id=task.task_id,
            description=task.description,
            tool_name=task.tool_name,
            expected_output=task.expected_output,
            dependencies=task.dependencies,
            status=task.status,
            result=_public_result(task.tool_name, task.result),
            error_message=task.error_message,
            attempts=context.task_attempts.get(task.task_id, 0),
        )
        for task in plan.tasks
    ]


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, RetryableOperationError):
        return str(exc)
    return f"Tool execution failed ({type(exc).__name__})."


def _public_result(tool_name: str, result: Any) -> Any:
    if tool_name == "generate_document" and isinstance(result, dict):
        return {key: value for key, value in result.items() if key != "path"}
    return result
