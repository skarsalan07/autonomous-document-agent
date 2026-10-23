from app.config import Settings
from app.executor import execute_plan
from app.exceptions import RetryableOperationError
from app.planner import validate_plan
from app.schemas import ExecutionPlan, PlanTask, TaskStatus
from app.tools import TOOL_REGISTRY


def _plan() -> ExecutionPlan:
    return validate_plan(ExecutionPlan(
        objective="Produce a test document for stakeholders.",
        document_type="Test Plan",
        audience="Stakeholders",
        tasks=[
            PlanTask(task_id="analysis", description="Analyze the request", tool_name="analyze_request", expected_output="Analysis"),
            PlanTask(task_id="draft", description="Draft the content", tool_name="draft_content", expected_output="Draft", dependencies=["analysis"]),
            PlanTask(task_id="generated", description="Generate the document", tool_name="generate_document", expected_output="DOCX", dependencies=["draft"]),
            PlanTask(task_id="validated", description="Validate the document", tool_name="validate_document", expected_output="Validation", dependencies=["generated"]),
        ],
        outline=[
            {"title": "Purpose", "description": "Purpose of the work"},
            {"title": "Approach", "description": "How to deliver"},
        ],
        success_criteria=["Validation passes"],
    ))


def test_executor_runs_tasks_in_dependency_order(monkeypatch):
    order = []

    def make_tool(name):
        def tool(context):
            order.append(name)
            return {"tool": name}
        return tool

    for name in ("analyze_request", "draft_content", "generate_document", "validate_document"):
        monkeypatch.setitem(TOOL_REGISTRY, name, make_tool(name))
    results = execute_plan(_plan(), "Create a document.", "exec-1", Settings(max_retries=0))
    assert order == ["analyze_request", "draft_content", "generate_document", "validate_document"]
    assert all(result.status == TaskStatus.COMPLETED for result in results)


def test_dependent_tasks_are_skipped_after_failure(monkeypatch):
    def fail(_context):
        raise ValueError("invalid operation")

    called = []

    def should_not_run(_context):
        called.append(True)
        return {}

    monkeypatch.setitem(TOOL_REGISTRY, "analyze_request", fail)
    monkeypatch.setitem(TOOL_REGISTRY, "draft_content", should_not_run)
    results = execute_plan(_plan(), "Create a document.", "exec-2", Settings(max_retries=2))
    assert results[0].status == TaskStatus.FAILED
    assert results[1].status == TaskStatus.SKIPPED
    assert called == []


def test_transient_tool_error_retries_only_within_configured_limit(monkeypatch):
    attempts = []

    def flaky(_context):
        attempts.append(1)
        if len(attempts) == 1:
            raise RetryableOperationError("temporarily unavailable")
        return {"ok": True}

    monkeypatch.setitem(TOOL_REGISTRY, "analyze_request", flaky)
    monkeypatch.setitem(TOOL_REGISTRY, "draft_content", lambda _context: {})
    monkeypatch.setitem(TOOL_REGISTRY, "generate_document", lambda _context: {})
    monkeypatch.setitem(TOOL_REGISTRY, "validate_document", lambda _context: {})
    results = execute_plan(_plan(), "Create a document.", "exec-3", Settings(max_retries=1))
    assert len(attempts) == 2
    assert results[0].attempts == 2
    assert results[0].status == TaskStatus.COMPLETED


def test_permanent_failure_is_not_retried(monkeypatch):
    attempts = []

    def permanent(_context):
        attempts.append(1)
        raise ValueError("permanent validation issue")

    monkeypatch.setitem(TOOL_REGISTRY, "analyze_request", permanent)
    results = execute_plan(_plan(), "Create a document.", "exec-4", Settings(max_retries=3))
    assert len(attempts) == 1
    assert results[0].status == TaskStatus.FAILED
