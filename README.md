# JEV vs LLM — Banking Decision Demo (Simple UX v3)

A synthetic enterprise banking demo comparing **TypeSafe JEV** with **GPT-5.6 Terra in Microsoft Foundry / Azure OpenAI**.

The front end is deliberately simple:

1. **Incoming payment** — one synthetic £4.2M London → Singapore payment.
2. **LLM** — a short human-readable assessment plus live latency/cost/tokens.
3. **JEV** — software-ready probabilistic decision signals plus live latency/cost/tokens.
4. **Run comparison** — both providers receive the same state concurrently.
5. **How it works** — simple explainer screens.
6. **Scale test** — optional benchmark hidden behind its own tab.

The backend still keeps the richer decision schema, cost guards, synthetic state changes, audit logging, and scale benchmark.

## Reproduce the LinkedIn demo

This repository accompanies a synthetic banking comparison of **TypeSafe Jev** and **GPT-5.6 Terra via Azure Foundry**.

The recorded flow is:

1. Run the £4.2M baseline payment through both providers.
2. Compare the LLM assessment with Jev's typed probabilistic decision signals.
3. Change one fact (for example, CFO independently confirmed) and rerun.
4. Open **Scale test** and run 20 or more synthetic cases.
5. Compare latency, throughput, tokens and provider cost.

See [`RESULTS.md`](RESULTS.md) for the measurements captured in the LinkedIn recording.

> **Note:** All transaction/customer data in this project is synthetic. This is an architecture demonstration, not a production fraud model or financial decisioning system.

## 1. Requirements

- Windows 11 / macOS / Linux
- Python 3.10+ (Python 3.13 is fine)
- A TypeSafe API key with JEV access
- A Microsoft Foundry / Azure OpenAI deployment of GPT-5.6 Terra (Sol is optional)

This version intentionally uses `uvicorn` **without** `[standard]`, so Windows ARM64 does not need to compile `httptools` or install Visual C++ Build Tools.

## 2. Extract and open

Clone or download the repo and open the folder in PyCharm, or open a terminal in the project root.

Example:

```powershell
git clone https://github.com/sokapil/jev-vs-llm-banking-demo.git
cd jev-vs-llm-banking-demo
```

## 3. Create `.env`

```powershell
Copy-Item .env.example .env
```

Edit `.env`.

### TypeSafe / JEV

Keep these two values exactly as shown:

```env
TYPESAFE_MODEL=jev-latest
TYPESAFE_BASE_URL=https://api.typesafe.ai/v1/systemone
```

Add your real key:

```env
TYPESAFE_API_KEY=YOUR_REAL_TYPESAFE_KEY
```

### Microsoft Foundry / Azure OpenAI

Add:

```env
AZURE_OPENAI_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
AZURE_OPENAI_API_KEY=YOUR_REAL_AZURE_KEY
AZURE_OPENAI_DEPLOYMENT_TERRA=YOUR_EXACT_TERRA_DEPLOYMENT_NAME
AZURE_OPENAI_DEPLOYMENT_SOL=YOUR_EXACT_SOL_DEPLOYMENT_NAME
AZURE_OPENAI_COMPARATOR=terra
```

The deployment value must be the **deployment name you created in Foundry**, not merely the catalog model name.

For a safe first run, keep:

```env
AZURE_OPENAI_REASONING_EFFORT=medium
AZURE_OPENAI_MAX_OUTPUT_TOKENS=1200
PORT=8010
MOCK_MODE=true
```

## 4. Run

### Easiest on Windows

```powershell
.\run.ps1
```

If PowerShell blocks scripts:

```cmd
run.bat
```

The first run creates the virtual environment, installs packages and starts FastAPI.

Open:

```text
http://127.0.0.1:8010
```

With `MOCK_MODE=true`, no provider API calls are made and there is no model cost.

## 5. Turn on the real APIs

Stop the app with `Ctrl+C`.

Change:

```env
MOCK_MODE=false
```

Run again:

```powershell
.\run.ps1
```

Then click **Run comparison** once.

That makes:

- 1 live JEV call
- 1 live GPT-5.6 Terra call through Microsoft Foundry

The UI shows the **actual measured latency, provider-reported token usage and calculated cost for that run**.

## 6. Demo flow

### Live comparison

Start on **Baseline**, explain the mixed transaction signals, then press **Run comparison**.

Change one fact and rerun:

- CFO confirmed
- Unknown device
- Sanctions alert
- £25M payment

The key distinction is:

> **LLM returns a human-readable assessment. JEV returns probabilistic decision signals software can act on.**

### How it works

The **How it works** tab automatically reuses the latest live results and explains the difference without extra API calls.

### Scale test

Start with **20 cases**. The local spend guard checks projected cost before the benchmark begins. The UI supports larger runs up to 1,000 cases.

## 7. Cost guards

The `.env` defaults include:

```env
JEV_SESSION_BUDGET_USD=1.00
LLM_SESSION_BUDGET_USD=1.50
```

These are local safety guards. Increase them only deliberately.

`JEV_CREDIT_BALANCE_USD=5.00` is display-only and reflects the balance you entered; this application does not query TypeSafe billing.

## 8. Audit log

Live and benchmark runs are written to:

```text
audit/decisions.jsonl
```

The demo uses synthetic data only.

## Troubleshooting

### `httptools` / Microsoft Visual C++ error

This version uses:

```text
uvicorn>=0.35,<1
```

instead of `uvicorn[standard]`.

### Port 8010 is already in use

Change:

```env
PORT=8011
```

and open `http://127.0.0.1:8011`.

### Azure model error

Check that `AZURE_OPENAI_DEPLOYMENT_TERRA` contains your **exact deployment name** and that `AZURE_OPENAI_BASE_URL` points to the correct Azure OpenAI v1 endpoint.

### TypeSafe URL

Use the raw URL only:

```env
TYPESAFE_BASE_URL=https://api.typesafe.ai/v1/systemone
```

Do not paste Markdown link syntax into `.env`.
