from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PaymentAction(str, Enum):
    allow = "ALLOW"
    review = "REVIEW"
    hold = "HOLD"
    block = "BLOCK"


class FraudRisk(str, Enum):
    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"
    critical = "CRITICAL"


class AuthenticationAction(str, Enum):
    standard = "STANDARD"
    step_up = "STEP_UP"
    call_back = "CALL_BACK"


class RouteTo(str, Enum):
    payments = "PAYMENTS"
    fraud = "FRAUD"
    aml = "AML"
    relationship_manager = "RM"


class PaymentProbabilities(BaseModel):
    allow: float = Field(ge=0, le=1)
    review: float = Field(ge=0, le=1)
    hold: float = Field(ge=0, le=1)
    block: float = Field(ge=0, le=1)


class FraudProbabilities(BaseModel):
    low: float = Field(ge=0, le=1)
    medium: float = Field(ge=0, le=1)
    high: float = Field(ge=0, le=1)
    critical: float = Field(ge=0, le=1)


class AuthProbabilities(BaseModel):
    standard: float = Field(ge=0, le=1)
    step_up: float = Field(ge=0, le=1)
    call_back: float = Field(ge=0, le=1)


class RouteProbabilities(BaseModel):
    payments: float = Field(ge=0, le=1)
    fraud: float = Field(ge=0, le=1)
    aml: float = Field(ge=0, le=1)
    relationship_manager: float = Field(ge=0, le=1)


class ChoicePayment(BaseModel):
    choice: PaymentAction
    probabilities: PaymentProbabilities
    confidence: float = Field(ge=0, le=1)


class ChoiceFraud(BaseModel):
    choice: FraudRisk
    probabilities: FraudProbabilities
    confidence: float = Field(ge=0, le=1)


class ChoiceAuthentication(BaseModel):
    choice: AuthenticationAction
    probabilities: AuthProbabilities
    confidence: float = Field(ge=0, le=1)


class ChoiceRoute(BaseModel):
    choice: RouteTo
    probabilities: RouteProbabilities
    confidence: float = Field(ge=0, le=1)


class BinaryDecision(BaseModel):
    probability_true: float = Field(ge=0, le=1)


class ScoreDecision(BaseModel):
    score: float = Field(ge=0, le=4)
    probabilities: list[float] = Field(min_length=5, max_length=5)
    confidence: float = Field(ge=0, le=1)


class LLMDecisionBundle(BaseModel):
    assessment: str = Field(description="One or two concise sentences for a human operator, maximum about 55 words.")
    payment_action: ChoicePayment
    fraud_risk: ChoiceFraud
    aml_escalation: BinaryDecision
    sanctions_review: BinaryDecision
    authentication: ChoiceAuthentication
    route_to: ChoiceRoute
    transaction_anomaly: ScoreDecision
    human_review_required: BinaryDecision


class DecisionRequest(BaseModel):
    variant: str = "baseline"
    custom_state: str | None = None


class BenchmarkRequest(BaseModel):
    cases: int = Field(default=20, ge=1, le=1000)
    provider: Literal["jev", "llm", "both"] = "both"
