from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, model_validator
from app.models.entities import Role, StepType


class Register(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)


class Login(BaseModel):
    email: EmailStr
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    role: Role


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    status: Literal["ACTIVE", "ARCHIVED"] | None = None


class TaskCreate(BaseModel):
    external_id: str | None = Field(default=None, min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=100)
    priority: int = Field(default=0, ge=0, le=100)
    input_payload: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class BatchCreate(BaseModel):
    tasks: list[TaskCreate] = Field(min_length=1, max_length=100)


class StepCreate(BaseModel):
    sequence_number: int = Field(ge=0)
    step_type: StepType
    content: str = ""
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: dict | None = None
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime | None = None


class RunCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=200)
    model_version: str = Field(default="", max_length=200)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    steps: list[StepCreate] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def ordered(self):
        numbers = [s.sequence_number for s in self.steps]
        if numbers != sorted(set(numbers)):
            raise ValueError("Step sequence numbers must be unique and strictly increasing")
        dates = [self.started_at, self.completed_at, *[s.timestamp for s in self.steps]]
        if any(d is not None and d.tzinfo is None for d in dates):
            raise ValueError("Timestamps must include a timezone")
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("Run completion must follow start")
        return self


class AnnotationInput(BaseModel):
    values: dict = Field(default_factory=dict)
    label: Literal["SUCCESS", "PARTIAL", "FAILURE", "UNSAFE"]
    score: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=20000)
    structured_payload: dict = Field(default_factory=dict)


class ReviewInput(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "REQUEST_CHANGES", "ESCALATED"]
    reason: str = Field(min_length=1, max_length=5000)
