"""Runtime and experiment configuration contracts."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RuntimeConfig(BaseModel):
    """Operational bounds for one graph invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_attempts: int = Field(default=2, ge=1, le=5)
    timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    max_graph_steps: int = Field(default=12, ge=1, le=100)


class EvaluationThresholds(BaseModel):
    """Thresholds that may be used by a future evaluation gate.

    Phase 2 does not run a quality gate. A future evaluation entrypoint must
    call ``require_locked`` before using these values.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    correctness: Decimal | None = Field(default=None, ge=0, le=1)
    fairness: Decimal | None = Field(default=None, ge=0, le=1)
    locked: bool = False

    @field_validator("version")
    @classmethod
    def version_must_be_trimmed(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("threshold version must not have surrounding whitespace")
        return value

    def require_locked(self) -> None:
        """Fail closed when a future evaluation tries to use unlocked values."""

        if not self.locked:
            raise ValueError("evaluation thresholds must be locked before use")
        if self.correctness is None or self.fairness is None:
            raise ValueError("locked evaluation thresholds must define correctness and fairness")


class PipelineConfig(BaseModel):
    """Configuration for the deterministic foundation.

    Policy limits are intentionally optional. No lending threshold is invented
    from the inspected dataset; callers must provide and version any such rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    policy_dti_max: float | None = Field(default=None, gt=0, le=100)
    policy_ltv_max: float | None = Field(default=None, gt=0)
    evaluation_thresholds: EvaluationThresholds | None = None

