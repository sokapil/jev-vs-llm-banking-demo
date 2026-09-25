from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from models import LLMDecisionBundle


JEV_QUESTIONS = {
    "payment_action": {
        "type": "choice",
        "instructions": "What operational action should the bank take on this payment right now?",
        "criteria": {
            "allow": "Allow processing without additional intervention",
            "review": "Continue only after an analyst reviews the event",
            "hold": "Temporarily hold the payment while additional checks are completed",
            "block": "Do not process because the supplied state indicates a strong reason to stop it",
        },
    },
    "fraud_risk": {
        "type": "choice",
        "instructions": "What is the fraud-risk level indicated by the supplied transaction state?",
        "criteria": {
            "low": "Little evidence of anomalous or suspicious behaviour",
            "medium": "Some anomalies exist but can plausibly fit legitimate activity",
            "high": "Multiple material anomalies justify active fraud review",
            "critical": "The supplied evidence strongly indicates immediate fraud intervention",
        },
    },
    "aml_escalation": {
        "type": "noul",
        "instructions": "The supplied transaction state warrants escalation to AML review",
    },
    "sanctions_review": {
        "type": "noul",
        "instructions": "The supplied transaction state warrants sanctions-screening review before processing",
    },
    "authentication": {
        "type": "choice",
        "instructions": "What customer authentication action is appropriate before processing?",
        "criteria": {
            "standard": "Normal controls are sufficient",
            "step_up": "Require an additional strong authentication step",
            "call_back": "Require independent callback or equivalent out-of-band confirmation",
        },
    },
    "route_to": {
        "type": "choice",
        "instructions": "Which operational team should own the next review step?",
        "criteria": {
            "payments": "Payments operations",
            "fraud": "Fraud operations",
            "aml": "AML / financial-crime operations",
            "relationship_manager": "Relationship manager for client confirmation or context",
        },
    },
    "transaction_anomaly": {
        "type": "score",
        "instructions": "How anomalous is this transaction compared with the supplied customer context?",
        "criteria": [
            "0 - Normal: strongly consistent with stated customer behaviour",
            "1 - Mild: small departure from normal behaviour",
            "2 - Moderate: meaningful anomalies that deserve attention",
            "3 - High: several material anomalies",
            "4 - Extreme: highly unusual or clearly inconsistent with normal behaviour",
        ],
    },
    "human_review_required": {
        "type": "noul",
        "instructions": "A human analyst should review this transaction before it is released",
    },
}


LLM_SYSTEM = """You are a banking operations decision-support model working on a fully synthetic payment scenario.
Return only the requested structured object.
Use only facts in the supplied state. Do not invent customer history or external intelligence.
The assessment field must be one or two concise sentences for a human operator (about 55 words maximum).
For categorical questions, choose one allowed value and provide a probability distribution over all allowed values.
For yes/no questions, probability_true is your own estimated probability that the proposition is true.
For transaction_anomaly, score from 0 to 4 and provide five probabilities for levels 0,1,2,3,4.
The confidence fields are the LLM's own self-reported confidence and are not a calibration claim.
This is an architecture demo, not a production fraud, AML, sanctions, or credit decision."""


@dataclass
class ProviderResult:
    provider: str
    model: str
    latency_ms: float
    cost_usd: float
    input_tokens: int
    output_tokens: int
    raw: dict[str, Any]
    normalized: dict[str, Any]
    schema_valid: bool = True
    error: str | None = None
    assessment: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 2),
            "cost_usd": round(self.cost_usd, 8),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "raw": self.raw,
            "normalized": self.normalized,
            "schema_valid": self.schema_valid,
            "error": self.error,
            "assessment": self.assessment,
        }


class SpendLedger:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.jev_spend = 0.0
        self.llm_spend = 0.0

    async def add(self, provider: str, amount: float) -> None:
        async with self._lock:
            if provider == "jev":
                self.jev_spend += amount
            else:
                self.llm_spend += amount

    async def snapshot(self) -> dict[str, float]:
        async with self._lock:
            return {"jev": self.jev_spend, "llm": self.llm_spend}


ledger = SpendLedger()


def azure_llm_config() -> tuple[str, str, str]:
    comparator = os.getenv("AZURE_OPENAI_COMPARATOR", "terra").strip().lower()
    if comparator not in {"terra", "sol"}:
        raise RuntimeError("AZURE_OPENAI_COMPARATOR must be 'terra' or 'sol'.")

    if comparator == "sol":
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_SOL", "").strip()
        model_family = "gpt-5.6-sol"
    else:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_TERRA", "").strip()
        model_family = "gpt-5.6-terra"

    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip() or deployment
    base_url = os.getenv("AZURE_OPENAI_BASE_URL", "").strip()
    if base_url:
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/openai/v1"):
            base_url = f"{base_url}/openai/v1"
        base_url += "/"
    return deployment, model_family, base_url


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _choice(answer: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    probs = answer.get("probabilities") or {}
    return {
        "kind": "choice",
        "value": mapping.get(str(answer.get("choice", "")).lower(), str(answer.get("choice", "")).upper()),
        "confidence": answer.get("confidence"),
        "probabilities": {mapping.get(str(k).lower(), str(k).upper()): _f(v) for k, v in probs.items()},
    }


def _noul(answer: dict[str, Any]) -> dict[str, Any]:
    p = _f(answer.get("noul"))
    return {
        "kind": "binary",
        "value": "YES" if p >= 0.5 else "NO",
        "probability_true": p,
        "probabilities": {"YES": p, "NO": max(0.0, 1.0 - p)},
        "confidence": None,
    }


def _score(answer: dict[str, Any]) -> dict[str, Any]:
    probs = answer.get("probabilities") or {}
    return {
        "kind": "score",
        "value": _f(answer.get("score")),
        "confidence": answer.get("confidence"),
        "probabilities": {str(k): _f(v) for k, v in probs.items()},
        "legend": answer.get("legend") or {},
    }


def normalize_jev(payload: dict[str, Any]) -> dict[str, Any]:
    a = payload.get("answers") or {}
    return {
        "payment_action": _choice(a.get("payment_action", {}), {"allow": "ALLOW", "review": "REVIEW", "hold": "HOLD", "block": "BLOCK"}),
        "fraud_risk": _choice(a.get("fraud_risk", {}), {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"}),
        "aml_escalation": _noul(a.get("aml_escalation", {})),
        "sanctions_review": _noul(a.get("sanctions_review", {})),
        "authentication": _choice(a.get("authentication", {}), {"standard": "STANDARD", "step_up": "STEP_UP", "call_back": "CALL_BACK"}),
        "route_to": _choice(a.get("route_to", {}), {"payments": "PAYMENTS", "fraud": "FRAUD", "aml": "AML", "relationship_manager": "RM"}),
        "transaction_anomaly": _score(a.get("transaction_anomaly", {})),
        "human_review_required": _noul(a.get("human_review_required", {})),
    }


def normalize_llm(obj: LLMDecisionBundle) -> dict[str, Any]:
    d = obj.model_dump(mode="json")
    def choice(name: str) -> dict[str, Any]:
        x = d[name]
        return {
            "kind": "choice",
            "value": str(x["choice"]).upper(),
            "confidence": x["confidence"],
            "probabilities": {k.upper(): v for k, v in x["probabilities"].items()},
        }
    def binary(name: str) -> dict[str, Any]:
        p = d[name]["probability_true"]
        return {"kind": "binary", "value": "YES" if p >= .5 else "NO", "probability_true": p,
                "probabilities": {"YES": p, "NO": 1-p}, "confidence": None}
    x = d["transaction_anomaly"]
    return {
        "payment_action": choice("payment_action"),
        "fraud_risk": choice("fraud_risk"),
        "aml_escalation": binary("aml_escalation"),
        "sanctions_review": binary("sanctions_review"),
        "authentication": choice("authentication"),
        "route_to": choice("route_to"),
        "transaction_anomaly": {"kind": "score", "value": x["score"], "confidence": x["confidence"],
                                "probabilities": {str(i): p for i, p in enumerate(x["probabilities"])},
                                "legend": {"0":"Normal","1":"Mild","2":"Moderate","3":"High","4":"Extreme"}},
        "human_review_required": binary("human_review_required"),
    }


def mock_normalized(state: str) -> dict[str, Any]:
    s = state.lower()
    confirmed = "independent callback" in s and "confirms" in s
    unknown = "unrecognised device" in s
    sanctions = "potential sanctions" in s
    big = "£25.0m" in s

    review = max(.15, min(.98, .84 + (.08 if unknown else 0) + (.10 if sanctions else 0) - (.45 if confirmed else 0)))
    fraud = max(.10, min(.98, .71 + (.12 if unknown else 0) + (.10 if big else 0) - (.35 if confirmed else 0)))
    human = max(.10, min(.99, .93 + (.04 if sanctions else 0) - (.48 if confirmed else 0)))
    auth_cb = max(.05, min(.98, .62 + (.20 if unknown else 0) - (.45 if confirmed else 0)))
    route_fraud = max(.10, min(.95, .68 + (.10 if unknown else 0) - (.30 if confirmed else 0)))

    return {
        "payment_action": {"kind":"choice","value":"REVIEW" if review < .90 else "HOLD","confidence":review,
                           "probabilities":{"ALLOW":max(.01,1-review-.08),"REVIEW":review*.8,"HOLD":review*.18,"BLOCK":.02}},
        "fraud_risk": {"kind":"choice","value":"HIGH" if fraud >= .5 else "MEDIUM","confidence":fraud,
                       "probabilities":{"LOW":.05,"MEDIUM":max(.05,1-fraud-.15),"HIGH":fraud*.84,"CRITICAL":fraud*.16}},
        "aml_escalation": {"kind":"binary","value":"YES" if sanctions else "NO","probability_true":.88 if sanctions else .22,
                           "probabilities":{"YES":.88 if sanctions else .22,"NO":.12 if sanctions else .78},"confidence":None},
        "sanctions_review": {"kind":"binary","value":"YES" if sanctions else "NO","probability_true":.96 if sanctions else .06,
                             "probabilities":{"YES":.96 if sanctions else .06,"NO":.04 if sanctions else .94},"confidence":None},
        "authentication": {"kind":"choice","value":"CALL_BACK" if auth_cb >= .5 else "STANDARD","confidence":auth_cb,
                           "probabilities":{"STANDARD":max(.05,1-auth_cb-.15),"STEP_UP":.15,"CALL_BACK":auth_cb}},
        "route_to": {"kind":"choice","value":"FRAUD" if route_fraud >= .5 else "PAYMENTS","confidence":route_fraud,
                     "probabilities":{"PAYMENTS":max(.05,1-route_fraud-.20),"FRAUD":route_fraud,"AML":.12,"RM":.08}},
        "transaction_anomaly": {"kind":"score","value":3.4 if unknown or big else (2.2 if confirmed else 3.0),"confidence":.78,
                                "probabilities":{"0":.02,"1":.07,"2":.19,"3":.50,"4":.22},
                                "legend":{"0":"Normal","1":"Mild","2":"Moderate","3":"High","4":"Extreme"}},
        "human_review_required": {"kind":"binary","value":"YES" if human >= .5 else "NO","probability_true":human,
                                  "probabilities":{"YES":human,"NO":1-human},"confidence":None},
    }


def mock_assessment(state: str, normalized: dict[str, Any]) -> str:
    if "independent callback" in state.lower() and "confirms" in state.lower():
        return "Independent CFO confirmation materially reduces concern, but the payment remains unusually large and should continue through enhanced controls."
    if "unrecognised device" in state.lower():
        return "The payment remains high risk because the value is unusual, the beneficiary is new and the instruction now comes from an unrecognised device. Manual review and stronger authentication are appropriate."
    return "The payment appears high risk because it is much larger than usual, involves a new beneficiary and was requested urgently. Manual review and independent confirmation are appropriate before release."


async def call_jev(state: str, mock: bool = False) -> ProviderResult:
    model = os.getenv("TYPESAFE_MODEL", "jev-latest")
    if mock:
        await asyncio.sleep(.18)
        normalized = mock_normalized(state)
        inp = 1302
        cost = inp / 1_000_000 * float(os.getenv("JEV_INPUT_PRICE_PER_M", "0.042"))
        return ProviderResult("jev", "jev-mock", 180.0, cost, inp, 0, {"mock": True}, normalized)

    key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not key or key == "replace_me":
        raise RuntimeError("TYPESAFE_API_KEY is missing. Add it to .env or enable MOCK_MODE=true.")

    endpoint = os.getenv("TYPESAFE_BASE_URL", "https://api.typesafe.ai/v1/systemone")
    payload = {"state": state, "model": model, "questions": JEV_QUESTIONS}
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(endpoint, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
        r.raise_for_status()
        data = r.json()
    latency = (time.perf_counter() - start) * 1000
    usage = data.get("usage") or {}
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cost = inp / 1_000_000 * float(os.getenv("JEV_INPUT_PRICE_PER_M", "0.042"))
    await ledger.add("jev", cost)
    return ProviderResult("jev", str(data.get("model") or model), latency, cost, inp, out, data, normalize_jev(data))


async def call_llm(state: str, mock: bool = False) -> ProviderResult:
    deployment, model_family, base_url = azure_llm_config()
    display_model = f"Azure Foundry · {model_family} · {deployment or 'deployment-not-set'}"

    if mock:
        await asyncio.sleep(2.8)
        normalized = mock_normalized(state)
        assessment = mock_assessment(state, normalized)
        inp, out = 2402, 1200
        pricing = {
            "gpt-5.6-terra": (float(os.getenv("AZURE_GPT_5_6_TERRA_INPUT_PER_M","2")), float(os.getenv("AZURE_GPT_5_6_TERRA_OUTPUT_PER_M","12"))),
            "gpt-5.6-sol": (float(os.getenv("AZURE_GPT_5_6_SOL_INPUT_PER_M","4")), float(os.getenv("AZURE_GPT_5_6_SOL_OUTPUT_PER_M","20"))),
        }
        ip, op = pricing[model_family]
        cost = inp/1_000_000*ip + out/1_000_000*op
        return ProviderResult("llm", f"{model_family}-mock", 2800.0, cost, inp, out, {"mock": True}, normalized, assessment=assessment)

    key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    if not key or key == "replace_me":
        raise RuntimeError("AZURE_OPENAI_API_KEY is missing. Add it to .env.")
    if not base_url:
        raise RuntimeError("AZURE_OPENAI_BASE_URL is missing.")
    if not deployment or deployment == "replace_me":
        raise RuntimeError("Azure deployment name is missing.")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=key, base_url=base_url)
    start = time.perf_counter()
    response = await client.responses.parse(
        model=deployment,
        input=[{"role":"system","content":LLM_SYSTEM},{"role":"user","content":state}],
        reasoning={"effort": os.getenv("AZURE_OPENAI_REASONING_EFFORT","medium")},
        max_output_tokens=int(os.getenv("AZURE_OPENAI_MAX_OUTPUT_TOKENS","1200")),
        text_format=LLMDecisionBundle,
    )
    latency = (time.perf_counter() - start) * 1000
    parsed = response.output_parsed
    if parsed is None:
        raise RuntimeError("The Azure Foundry LLM returned no parsed structured output.")

    usage = response.usage
    inp = int(getattr(usage, "input_tokens", 0) or 0)
    out = int(getattr(usage, "output_tokens", 0) or 0)
    pricing = {
        "gpt-5.6-terra": (float(os.getenv("AZURE_GPT_5_6_TERRA_INPUT_PER_M","2")), float(os.getenv("AZURE_GPT_5_6_TERRA_OUTPUT_PER_M","12"))),
        "gpt-5.6-sol": (float(os.getenv("AZURE_GPT_5_6_SOL_INPUT_PER_M","4")), float(os.getenv("AZURE_GPT_5_6_SOL_OUTPUT_PER_M","20"))),
    }
    ip, op = pricing[model_family]
    cost = inp/1_000_000*ip + out/1_000_000*op
    await ledger.add("llm", cost)
    raw = parsed.model_dump(mode="json")
    return ProviderResult("llm", display_model, latency, cost, inp, out, raw, normalize_llm(parsed), assessment=parsed.assessment)


def execution_plan(normalized: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    action = normalized.get("payment_action", {}).get("value")
    hr = _f(normalized.get("human_review_required", {}).get("probability_true"))
    sanctions = _f(normalized.get("sanctions_review", {}).get("probability_true"))
    auth = normalized.get("authentication", {}).get("value")
    route = normalized.get("route_to", {}).get("value")

    if action in {"HOLD", "BLOCK"} or hr >= .80:
        out.append({"action":"HOLD RELEASE","reason":"Payment action / human-review threshold triggered"})
    elif action == "REVIEW":
        out.append({"action":"GUARDED REVIEW","reason":"Release only after operational review"})
    else:
        out.append({"action":"CONTINUE","reason":"No hold threshold triggered"})

    if auth == "CALL_BACK":
        out.append({"action":"CALL BACK","reason":"Independent out-of-band confirmation"})
    elif auth == "STEP_UP":
        out.append({"action":"STEP-UP AUTH","reason":"Additional authentication requested"})

    if sanctions >= .75:
        out.append({"action":"SANCTIONS REVIEW","reason":"Sanctions-review probability ≥ 0.75"})
    if route:
        out.append({"action":f"ROUTE → {route}","reason":"Highest-probability operational owner"})
    return out


def append_audit(record: dict[str, Any]) -> None:
    path = Path(__file__).resolve().parent / "audit" / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
