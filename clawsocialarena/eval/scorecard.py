"""RunScorecard pydantic schema.

Emitted by EvalRunner per scenario run. Main-table metrics (TSR, privacy,
security) land in later phases; Phase 2 stubs them as defaults.
"""

from pydantic import BaseModel, ConfigDict, Field


class SAFDimsPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    dims: dict[str, float]
    passes: dict[str, bool]
    overall: float


class TaskScorecard(BaseModel):
    tsr: float = 1.0
    partial_credit: dict[str, float] = Field(default_factory=dict)


class PrivacyScorecard(BaseModel):
    leak_rates: dict[str, float] = Field(default_factory=dict)


class SecurityScorecard(BaseModel):
    asr: float = 0.0
    prop_depth: float = 0.0
    tiua: float = 1.0


class RunScorecard(BaseModel):
    scenario_id: str
    saf: SAFDimsPayload
    task: TaskScorecard = Field(default_factory=TaskScorecard)
    privacy: PrivacyScorecard = Field(default_factory=PrivacyScorecard)
    security: SecurityScorecard = Field(default_factory=SecurityScorecard)
    diagnostics: dict = Field(default_factory=dict)
    evaluator_version: str = "eval_v1.0.0"
