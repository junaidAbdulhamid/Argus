from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ExampleFilters(BaseModel):
    project_id: str | None = None
    task_type: str | None = None
    model: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    minimum_score: float = Field(default=1, ge=1, le=5)
    reviewer_decision: Literal["APPROVED"] | None = None
    annotation_label: str | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def dates(self):
        if any(d and d.tzinfo is None for d in [self.date_from, self.date_to]):
            raise ValueError("Date filters must include timezone")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Date range is reversed")
        return self


class DatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)


class VersionInput(BaseModel):
    example_ids: list[str] = Field(min_length=1, max_length=10000)
    filters: ExampleFilters = Field(default_factory=ExampleFilters)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_examples(self):
        if len(self.example_ids) != len(set(self.example_ids)):
            raise ValueError("Examples must be unique")
        return self


class ExportInput(BaseModel):
    format: Literal["sft", "dpo", "reward", "trajectory"]
    container: Literal["jsonl", "json"] = "jsonl"


class PreferenceInput(BaseModel):
    chosen_run_id: str
    rejected_run_id: str
    rationale: str = Field(min_length=1, max_length=10000)
