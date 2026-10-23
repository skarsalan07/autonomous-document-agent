"""Pydantic contracts shared across API, planner, executor, and tools."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentRequest(BaseModel):
    request: str = Field(min_length=1, max_length=10_000)

    @field_validator("request")
    @classmethod
    def request_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("request must not be empty or whitespace-only")
        return value


class OutlineSection(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)


class PlanTask(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_-]{0,39}$")
    description: str = Field(min_length=3, max_length=500)
    tool_name: str = Field(min_length=1, max_length=80)
    expected_output: str = Field(min_length=3, max_length=300)
    dependencies: list[str] = Field(default_factory=list, max_length=20)
    status: TaskStatus = TaskStatus.PENDING
    result: Any | None = None
    error_message: str | None = None


class ExecutionPlan(BaseModel):
    objective: str = Field(min_length=5, max_length=1000)
    document_type: str = Field(min_length=2, max_length=120)
    audience: str = Field(min_length=2, max_length=300)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    risks: list[str] = Field(default_factory=list, max_length=30)
    tasks: list[PlanTask] = Field(min_length=4, max_length=20)
    outline: list[OutlineSection] = Field(min_length=2, max_length=20)
    success_criteria: list[str] = Field(min_length=1, max_length=20)


class ContentSection(BaseModel):
    heading: str = Field(min_length=1, max_length=160)
    paragraphs: list[str] = Field(default_factory=list, max_length=20)
    bullets: list[str] = Field(default_factory=list, max_length=30)
    numbered_items: list[str] = Field(default_factory=list, max_length=30)
    table: list[list[str]] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def section_must_have_content(self) -> "ContentSection":
        if not (self.paragraphs or self.bullets or self.numbered_items or self.table):
            raise ValueError("each document section must contain substantive content")
        return self


class DocumentDraft(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    executive_summary: str = Field(min_length=50, max_length=5000)
    sections: list[ContentSection] = Field(min_length=2, max_length=30)
    conclusion: str = Field(min_length=30, max_length=3000)


class TaskResult(BaseModel):
    task_id: str
    description: str
    tool_name: str
    expected_output: str
    dependencies: list[str]
    status: TaskStatus
    result: Any | None = None
    error_message: str | None = None
    attempts: int = 0


class ExecutionSummary(BaseModel):
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    skipped_tasks: int


class QualityCheck(BaseModel):
    name: str
    passed: bool
    details: str


class QualityResult(BaseModel):
    passed: bool
    checks: list[QualityCheck]
    character_count: int
    file_size_bytes: int


class DocumentMetadata(BaseModel):
    filename: str
    size_bytes: int
    download_url: str


class AgentResponse(BaseModel):
    execution_id: str
    status: str
    request: str
    document_type: str
    plan: list[TaskResult]
    execution_summary: ExecutionSummary
    quality_check: QualityResult
    document: DocumentMetadata | None = None
    message: str


class ErrorResponse(BaseModel):
    execution_id: str
    error: str
    detail: str
