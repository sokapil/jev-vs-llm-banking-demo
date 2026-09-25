from __future__ import annotations

import asyncio
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from models import BenchmarkRequest, DecisionRequest
from providers import append_audit, azure_llm_config, call_jev, call_llm, execution_plan, ledger
from scenarios import VARIANTS, all_scenarios, benchmark_states, scenario_for, scenario_to_state

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="JEV vs LLM Banking Decision Demo", version="3.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def llm_prices(model_family: str) -> tuple[float, float]:
    table = {
        "gpt-5.6-terra": (
            float(os.getenv("AZURE_GPT_5_6_TERRA_INPUT_PER_M", "2.00")),
            float(os.getenv("AZURE_GPT_5_6_TERRA_OUTPUT_PER_M", "12.00")),
        ),
        "gpt-5.6-sol": (
            float(os.getenv("AZURE_GPT_5_6_SOL_INPUT_PER_M", "4.00")),
            float(os.getenv("AZURE_GPT_5_6_SOL_OUTPUT_PER_M", "20.00")),
        ),
    }
    return table.get(model_family, table["gpt-5.6-terra"])


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 3.5))


def projected_cost(provider: str, state: str, cases: int = 1) -> float:
    if provider == "jev":
        tokens = estimate_tokens(state) + 1100
        return cases * tokens / 1_000_000 * float(os.getenv("JEV_INPUT_PRICE_PER_M", "0.042"))
    _, model_family, _ = azure_llm_config()
    in_price, out_price = llm_prices(model_family)
    input_tokens = estimate_tokens(state) + int(os.getenv("AZURE_OPENAI_INPUT_OVERHEAD_TOKENS", "2200"))
    output_tokens = int(os.getenv("AZURE_OPENAI_MAX_OUTPUT_TOKENS", "1200"))
    return cases * ((input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price))


async def ensure_budget(provider: str, estimate: float) -> None:
    spend = await ledger.snapshot()
    if provider == "jev":
        cap = float(os.getenv("JEV_SESSION_BUDGET_USD", "1.00"))
    else:
        cap = float(os.getenv("LLM_SESSION_BUDGET_USD", "1.50"))
    remaining = max(0.0, cap - spend[provider])
    if estimate > remaining + 1e-12:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Local {provider.upper()} cost guard blocked this run. "
                f"Projected ${estimate:.4f}, session budget remaining ${remaining:.4f}. "
                "Raise the corresponding *_SESSION_BUDGET_USD value in .env if you intentionally want to spend more."
            ),
        )


def state_from_request(req: DecisionRequest) -> tuple[str, dict[str, Any]]:
    if req.custom_state and req.custom_state.strip():
        return req.custom_state.strip(), {"id": "custom", "name": "Custom synthetic state"}
    if req.variant not in VARIANTS:
        raise HTTPException(status_code=400, detail=f"Unknown variant: {req.variant}")
    s = scenario_for(req.variant)
    return scenario_to_state(s), s


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/scenarios")
async def scenarios() -> dict[str, Any]:
    return {"scenarios": all_scenarios()}


@app.get("/api/config")
async def config() -> dict[str, Any]:
    spend = await ledger.snapshot()
    jev_credit = float(os.getenv("JEV_CREDIT_BALANCE_USD", "5.00"))
    jev_cap = float(os.getenv("JEV_SESSION_BUDGET_USD", "1.00"))
    llm_cap = float(os.getenv("LLM_SESSION_BUDGET_USD", "1.50"))
    mock = env_bool("MOCK_MODE", False)
    ts_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    azure_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    deployment, model_family, base_url = azure_llm_config()
    return {
        "mock_mode": mock,
        "jev": {
            "model": os.getenv("TYPESAFE_MODEL", "jev-latest"),
            "configured": bool(ts_key and ts_key != "replace_me") or mock,
            "input_price_per_m": float(os.getenv("JEV_INPUT_PRICE_PER_M", "0.042")),
            "display_credit_balance": jev_credit,
            "session_budget": jev_cap,
            "session_spend": spend["jev"],
            "estimated_display_credit_remaining": max(0.0, jev_credit - spend["jev"]),
        },
        "llm": {
            "provider": "Microsoft Foundry",
            "model": model_family,
            "deployment": deployment,
            "display_name": f"GPT-5.6 {model_family.split('-')[-1].title()} · Azure Foundry",
            "configured": bool(azure_key and azure_key != "replace_me" and base_url and deployment and deployment != "replace_me") or mock,
            "prices_per_m": {"input": llm_prices(model_family)[0], "output": llm_prices(model_family)[1]},
            "session_budget": llm_cap,
            "session_spend": spend["llm"],
            "reasoning_effort": os.getenv("AZURE_OPENAI_REASONING_EFFORT", "medium"),
            "max_output_tokens": int(os.getenv("AZURE_OPENAI_MAX_OUTPUT_TOKENS", "1200")),
        },
        "note": "Credit balance is configured locally from your screenshot; the app does not query TypeSafe billing.",
    }


@app.get("/api/cost-preview")
async def cost_preview(cases: int = 20) -> dict[str, Any]:
    cases = max(1, min(cases, 1000))
    sample = scenario_to_state(scenario_for("baseline"))
    return {
        "cases": cases,
        "jev_projected_usd": projected_cost("jev", sample, cases),
        "llm_projected_usd": projected_cost("llm", sample, cases),
        "jev_note": "Conservative local estimate; actual cost uses provider-reported input tokens.",
        "llm_note": "Conservative local estimate; actual cost uses provider-reported input/output tokens.",
    }


@app.post("/api/decision/{provider}")
async def decision(provider: str, req: DecisionRequest) -> dict[str, Any]:
    if provider not in {"jev", "llm"}:
        raise HTTPException(status_code=404, detail="provider must be jev or llm")
    state, scenario = state_from_request(req)
    await ensure_budget(provider, projected_cost(provider, state))
    mock = env_bool("MOCK_MODE", False)
    try:
        result = await (call_jev(state, mock=mock) if provider == "jev" else call_llm(state, mock=mock))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = result.as_dict()
    payload["execution_plan"] = execution_plan(result.normalized)
    payload["scenario"] = {"id": scenario.get("id"), "name": scenario.get("name", "Acme Group")}
    payload["timestamp"] = datetime.now(timezone.utc).isoformat()
    append_audit({
        "timestamp": payload["timestamp"],
        "kind": "single",
        "scenario": payload["scenario"],
        "provider": result.provider,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "cost_usd": result.cost_usd,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "normalized": result.normalized,
    })
    return payload


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))
    return s[idx]


async def run_provider_benchmark(provider: str, rows: list[tuple[str, str]], concurrency: int, mock: bool) -> dict[str, Any]:
    sem = asyncio.Semaphore(concurrency)
    results = []
    errors: list[str] = []

    async def one(case_id: str, state: str):
        async with sem:
            try:
                r = await (call_jev(state, mock=mock) if provider == "jev" else call_llm(state, mock=mock))
                return case_id, r, None
            except Exception as exc:
                return case_id, None, str(exc)

    started = time.perf_counter()
    completed = await asyncio.gather(*(one(case_id, state) for case_id, state in rows))
    wall_ms = (time.perf_counter() - started) * 1000

    for case_id, r, err in completed:
        if err:
            errors.append(f"{case_id}: {err}")
        elif r is not None:
            results.append(r)

    latencies = [r.latency_ms for r in results]
    total_cost = sum(r.cost_usd for r in results)
    total_in = sum(r.input_tokens for r in results)
    total_out = sum(r.output_tokens for r in results)
    return {
        "provider": provider,
        "model": results[0].model if results else (
            os.getenv("TYPESAFE_MODEL", "jev-latest")
            if provider == "jev"
            else f"Azure Foundry · {azure_llm_config()[1]} · {azure_llm_config()[0] or 'deployment-not-set'}"
        ),
        "requested_cases": len(rows),
        "successful_cases": len(results),
        "errors": errors[:10],
        "schema_failures": len(errors),
        "wall_time_ms": round(wall_ms, 2),
        "avg_latency_ms": round(statistics.mean(latencies), 2) if latencies else 0,
        "p50_latency_ms": round(percentile(latencies, 0.50), 2),
        "p95_latency_ms": round(percentile(latencies, 0.95), 2),
        "throughput_per_sec": round((len(results) / (wall_ms / 1000)), 2) if wall_ms > 0 else 0,
        "total_cost_usd": round(total_cost, 8),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "decisions_returned": len(results) * 8,
    }


@app.post("/api/benchmark")
async def benchmark(req: BenchmarkRequest) -> dict[str, Any]:
    rows = benchmark_states(req.cases)
    sample = rows[0][1]
    providers = ["jev", "llm"] if req.provider == "both" else [req.provider]
    for p in providers:
        await ensure_budget(p, projected_cost(p, sample, len(rows)))

    mock = env_bool("MOCK_MODE", False)
    concurrency = max(1, min(int(os.getenv("BENCHMARK_CONCURRENCY", "8")), 20))
    started = time.perf_counter()
    if len(providers) == 2:
        jev_result, llm_result = await asyncio.gather(
            run_provider_benchmark("jev", rows, concurrency, mock),
            run_provider_benchmark("llm", rows, concurrency, mock),
        )
        results = {"jev": jev_result, "llm": llm_result}
    else:
        p = providers[0]
        results = {p: await run_provider_benchmark(p, rows, concurrency, mock)}

    payload = {
        "cases": len(rows),
        "provider_mode": req.provider,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "warning": "Synthetic benchmark. Latency includes network/API time from this machine. LLM probability fields are self-reported, not a calibration claim.",
    }
    append_audit({"timestamp": payload["timestamp"], "kind": "benchmark", "cases": len(rows), "provider_mode": req.provider, "results": results})
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("PORT", "8010")), reload=False)
