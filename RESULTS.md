# Demo results

These are **single-run measurements from the LinkedIn demo**, not universal benchmark claims.
Results will vary with model deployment, region, network conditions, concurrency, prompt/state size, and provider load.

## Baseline single-payment run

Synthetic payment: **£4.2M, London → Singapore**

| Provider | Latency | Provider cost |
|---|---:|---:|
| GPT-5.6 Terra via Azure Foundry | 3.97 s | $0.006058 |
| TypeSafe Jev | 1.19 s | $0.00004108 |

Observed in this run:
- Jev latency was about **3.3× lower**.
- Jev provider cost was about **147× lower**.

## 20-case scale test

| Provider | Throughput | Provider cost |
|---|---:|---:|
| TypeSafe Jev | 1.19 cases/s | $0.000828 |
| GPT-5.6 Terra via Azure Foundry | 0.74 cases/s | $0.12582 |

Observed in this run:
- Jev provider cost was about **152× lower**.

## What this demo is testing

The point is not that one model universally replaces the other.

- **GPT-5.6 Terra** produces a human-readable assessment.
- **Jev** produces typed probabilistic decision signals that software can consume directly.

The demo then changes one fact in the state and reruns the same workflow to show how the outputs respond.

## Important caveat

This is a synthetic demonstration, not a controlled vendor benchmark and not a production fraud-detection system. Re-run the test in your own environment before drawing performance or cost conclusions.
