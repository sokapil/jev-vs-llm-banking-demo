# Cost behaviour

The demo does not hard-code live provider results. In **live mode**, it calculates cost from provider-reported token usage and the price values configured in `.env`.

For a safe first run, `.env.example` starts with:

```env
MOCK_MODE=true
```

Mock mode uses illustrative values close to the explainer visuals:

- JEV: ~1,302 input tokens, ~0.18 s, ~US$0.000055 equivalent
- Terra: ~2,402 input + up to 1,200 output/reasoning tokens, ~2.8 s, ~US$0.0192 equivalent

These mock numbers are **illustrative only** and make no provider charge.

Once `MOCK_MODE=false`, the UI replaces them with measured live latency, actual reported token usage and locally calculated cost.

Local safety guards:

```env
JEV_SESSION_BUDGET_USD=1.00
LLM_SESSION_BUDGET_USD=1.50
```

The scale test runs a cost preflight before sending provider requests.
