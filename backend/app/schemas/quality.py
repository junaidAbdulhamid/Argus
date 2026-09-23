from typing import Literal
from math import isfinite
from pydantic import BaseModel, Field, model_validator


class QualityRules(BaseModel):
    required_annotations: int = Field(default=1, ge=1, le=20)
    required_reviews: int = Field(default=1, ge=1, le=10)
    minimum_agreement: float = Field(default=0, ge=0, le=1)
    minimum_score: float = Field(default=1, ge=1, le=5)
    maximum_variance: float | None = Field(default=None, ge=0, le=100)
    minimum_gold_accuracy: float | None = Field(default=None, ge=0, le=1)
    minimum_gold_attempts: int = Field(default=1, ge=1, le=20)
    gold_every: int = Field(default=5, ge=1, le=100)
    auto_escalate_disagreement: bool = True
    reveal_after_completion: bool = False


class FieldInput(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    label: str = Field(min_length=1, max_length=200)
    field_type: Literal[
        "boolean", "single_select", "multi_select", "integer_rating", "continuous_score", "text", "json"
    ]
    description: str = Field(default="", max_length=5000)
    required: bool = False
    constraints: dict = Field(default_factory=dict)
    options: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def constraints_valid(self):
        allowed = {"minimum", "maximum", "min_length", "max_length", "min_items", "max_items"}
        if set(self.constraints) - allowed:
            raise ValueError("Unknown validation constraint")
        for key, value in self.constraints.items():
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError("Constraints must be numeric")
            if not isfinite(value):
                raise ValueError("Constraints must be finite")
            if key not in {"minimum", "maximum"} and (not isinstance(value, int) or value < 0):
                raise ValueError("Length and item constraints must be nonnegative integers")
        for lo, hi in [("minimum", "maximum"), ("min_length", "max_length"), ("min_items", "max_items")]:
            if lo in self.constraints and hi in self.constraints and self.constraints[lo] > self.constraints[hi]:
                raise ValueError("Minimum cannot exceed maximum")
        if len(set(self.options)) != len(self.options) or any(not x.strip() for x in self.options):
            raise ValueError("Options must be unique and nonempty")
        if self.field_type in {"single_select", "multi_select"} and not self.options:
            raise ValueError("Select fields require options")
        return self


class SchemaInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fields: list[FieldInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_keys(self):
        if len({f.key for f in self.fields}) != len(self.fields):
            raise ValueError("Field keys must be unique")
        return self


class EscalationInput(BaseModel):
    reason: str = Field(min_length=1, max_length=10000)


class EscalationResolution(BaseModel):
    status: Literal["RESOLVED", "DISMISSED"]
    resolution: str = Field(min_length=1, max_length=10000)


class GoldInput(BaseModel):
    expected: dict
    tolerance: float = Field(default=0, ge=0, le=100)


class ReviewCreate(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "REQUEST_CHANGES", "ESCALATED"]
    comments: str = Field(min_length=1, max_length=10000)
    metadata: dict = Field(default_factory=dict)
