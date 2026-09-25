from __future__ import annotations

from copy import deepcopy


BASE = {
    "id": "baseline",
    "name": "Acme Group — acquisition payment",
    "amount": "£4.2M",
    "destination": "Singapore",
    "beneficiary": "New beneficiary",
    "customer_tenure": "8 years",
    "kyc": "Current",
    "normal_payment_size": "£200k–£800k",
    "apac_history": "Yes, but infrequent",
    "channel": "Corporate online banking",
    "device": "Recognised device",
    "time": "02:13 UK",
    "purpose": "Acquisition closing payment",
    "recent_behaviour": "3 new beneficiaries in 48 hours",
    "sanctions": "No sanctions match",
    "confirmation": "CFO says transaction is urgent; no independent callback yet",
}


VARIANTS = {
    "baseline": {"label": "Baseline", "description": "Ambiguous high-value payment"},
    "cfo_confirmed": {"label": "CFO confirmed", "description": "Independent callback confirms payment"},
    "unknown_device": {"label": "Unknown device", "description": "Login device becomes unrecognised"},
    "sanctions_alert": {"label": "Sanctions alert", "description": "Potential name-screening hit appears"},
    "amount_25m": {"label": "£25M payment", "description": "Payment value jumps materially"},
}


def scenario_for(variant: str) -> dict:
    s = deepcopy(BASE)
    s["id"] = variant
    if variant == "cfo_confirmed":
        s["confirmation"] = "Independent callback to a known CFO number confirms beneficiary, amount, and acquisition purpose"
    elif variant == "unknown_device":
        s["device"] = "Unrecognised device with first-seen browser fingerprint"
    elif variant == "sanctions_alert":
        s["sanctions"] = "Potential sanctions/name-screening match requires analyst resolution"
    elif variant == "amount_25m":
        s["amount"] = "£25.0M"
        s["purpose"] = "Same-day acquisition completion payment; amount is >30× normal upper range"
    return s


def scenario_to_state(s: dict) -> str:
    return f"""Synthetic banking payment event. This is decision-support only, not a real customer.
Client: Acme Group (synthetic)
Payment amount: {s['amount']}
Destination: {s['destination']}
Beneficiary: {s['beneficiary']}
Customer relationship: {s['customer_tenure']}
KYC status: {s['kyc']}
Typical payment size: {s['normal_payment_size']}
Prior APAC activity: {s['apac_history']}
Instruction channel: {s['channel']}
Device: {s['device']}
Transaction time: {s['time']}
Stated purpose: {s['purpose']}
Recent behaviour: {s['recent_behaviour']}
Sanctions screening: {s['sanctions']}
Customer confirmation: {s['confirmation']}

Assess only the supplied facts. Do not assume facts that are not present."""


def all_scenarios() -> list[dict]:
    out = []
    for key, meta in VARIANTS.items():
        s = scenario_for(key)
        out.append({"id": key, **meta, "facts": s, "state": scenario_to_state(s)})
    return out


def benchmark_states(n: int) -> list[tuple[str, str]]:
    keys = list(VARIANTS)
    rows: list[tuple[str, str]] = []
    for i in range(n):
        key = keys[i % len(keys)]
        s = scenario_for(key)
        if i >= len(keys):
            batch = i // len(keys)
            s["recent_behaviour"] = f"{2 + (batch % 5)} new beneficiaries in the last {24 + (batch % 4) * 12} hours"
            s["time"] = f"{(2 + batch) % 24:02d}:{(13 + batch * 7) % 60:02d} UK"
        rows.append((f"{key}-{i+1:04d}", scenario_to_state(s)))
    return rows
