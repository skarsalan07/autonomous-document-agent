import pytest
from pydantic import ValidationError

from app.planner import validate_plan
from app.schemas import ExecutionPlan, PlanTask, TaskStatus


def sample_plan() -> ExecutionPlan:
    return ExecutionPlan(
        objective="Create a clear implementation document.",
        document_type="Implementation Plan",
        audience="Project stakeholders",
        tasks=[
            PlanTask(task_id="analyze", description="Analyze request details", tool_name="analyze_request", expected_output="Analysis"),
            PlanTask(task_id="draft", description="Draft substantive content", tool_name="draft_content", expected_output="Draft", dependencies=["analyze"]),
            PlanTask(task_id="generate", description="Generate a Word document", tool_name="generate_document", expected_output="DOCX", dependencies=["draft"]),
            PlanTask(task_id="validate", description="Validate the Word document", tool_name="validate_document", expected_output="Quality report", dependencies=["generate"]),
        ],
        outline=[
            {"title": "Objectives", "description": "Goals and outcomes"},
            {"title": "Delivery", "description": "Phases and responsibilities"},
        ],
        success_criteria=["A complete, validated DOCX is available."],
    )


def test_valid_plan_passes_tool_and_dependency_validation():
    assert validate_plan(sample_plan()).document_type == "Implementation Plan"


def test_planner_cannot_forge_execution_status_or_results():
    plan = sample_plan()
    plan.tasks[0].status = TaskStatus.COMPLETED
    plan.tasks[0].result = {"claimed": "completed"}
    validated = validate_plan(plan)
    assert validated.tasks[0].status == TaskStatus.PENDING
    assert validated.tasks[0].result is None


def test_unknown_tool_is_rejected():
    plan = sample_plan()
    plan.tasks[1].tool_name = "run_shell"
    with pytest.raises(ValueError, match="Unregistered tool"):
        validate_plan(plan)


def test_circular_dependency_is_rejected():
    plan = sample_plan()
    plan.tasks[0].dependencies = ["validate"]
    with pytest.raises(ValueError, match="circular"):
        validate_plan(plan)


def test_plan_requires_direct_mandatory_workflow_dependencies():
    plan = sample_plan()
    plan.tasks[-1].dependencies = ["draft"]
    with pytest.raises(ValueError, match="must depend directly"):
        validate_plan(plan)


def test_request_model_rejects_blank_and_trims_valid_input():
    from app.schemas import AgentRequest

    with pytest.raises(ValidationError):
        AgentRequest(request=" \n ")
    assert AgentRequest(request="  Make a plan  ").request == "Make a plan"
