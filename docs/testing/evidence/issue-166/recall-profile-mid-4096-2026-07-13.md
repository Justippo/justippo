# Issue #166 — Hindsight `mid` / 4096 production experiment

**Date:** 2026-07-13  
**Target:** `https://evidence-eu-worker.mc146.workers.dev`  
**Deployed commit:** `04b5d1701e832738bb3d0456a22c919a60e5ff16`  
**Deployment run:** [29274716895](https://github.com/chindris-mihai-alexandru/evidence-eu/actions/runs/29274716895)  
**Recall profile:** `budget=mid`, `max_tokens=4096`

PR [#179](https://github.com/chindris-mihai-alexandru/evidence-eu/pull/179)
replaced the hardcoded `high` / 8192 profile with validated settings and used
Hindsight's documented defaults for this reversible experiment. The public SSE
contract, retry policy, hosting, and GDPR handling were unchanged.

## Functional quality gate

The first post-deploy request used `residence permit renewal`, `top_k=5`, and
English. It returned HTTP 200, five real Hindsight results, twelve streamed
answer tokens, and the terminal `done` event. The top three results directly
covered Directive 2004/38/EC and EU residence rights. TTFB was 9.606s and the
full stream completed in 10.886s. Grounded retrieval therefore remained
functional before load was applied.

## Exact commands and windows

```bash
# 10 VUs — 2026-07-13 20:35:05–20:36:05 CEST
uv run --with locust locust -f tests/benchmark/locustfile.py \
  --headless -u 10 -r 2 --run-time 60s \
  --host https://evidence-eu-worker.mc146.workers.dev --only-summary

# 50 VUs — 2026-07-13 20:36:20–20:37:20 CEST
uv run --with locust locust -f tests/benchmark/locustfile.py \
  --headless -u 50 -r 5 --run-time 60s \
  --host https://evidence-eu-worker.mc146.workers.dev --only-summary
```

## 10-VU latency run

| Measurement | Samples | p50 | p95 | p99 |
|-------------|--------:|----:|----:|----:|
| First result | 111 | 0.829s | 10.299s | 15.793s |
| Answer TTFT | 111 | 0.245s | 0.478s | 0.584s |
| Answer stream | 111 | 1.151s | 3.489s | 4.724s |
| Post-retrieval | 111 | 1.523s | 3.689s | 4.944s |
| Full stream | 111 | 3.194s | 12.565s | 17.403s |

Completed streams: **111** at **1.86 requests/s**. Errors: **0 (0.00%)**.

Against the `high` / 8192 profiled run, first-result p95 improved by 0.359s
(3.4%), while full-stream p95 regressed by 0.615s (5.1%). This is not a
material NFR-01 improvement; full-stream p95 remains above the 5s target.

## 50-VU capacity run

| Measurement | Samples | p50 | p95 | p99 |
|-------------|--------:|----:|----:|----:|
| First result (successful recalls) | 372 | 2.368s | 7.598s | 14.066s |
| Answer TTFT | 372 | 0.250s | 0.556s | 0.969s |
| Answer stream | 372 | 1.014s | 4.258s | 5.751s |
| Post-retrieval | 372 | 1.332s | 4.666s | 6.078s |
| Full stream (successful and failed) | 465 | 3.904s | 9.828s | 15.163s |

Completed streams: **465** at **7.82 requests/s**. Errors: **93 (20.00%)**.

All failures were Hindsight Cloud HTTP 429 responses from the real bank-scoped
recall endpoint: 55 legal, 28 administrative, 5 multilingual, and 5 edge-case
requests. Against the prior `high` / 8192 profiled run, error rate improved by
3.38 percentage points (23.38% → 20.00%), first-result p95 improved by 2.486s
(24.7%), and full-stream p95 improved by 2.526s (20.4%).

## Decision

Retain `mid` / 4096: grounded source quality remained intact and the capacity
run improved, while the settings make the profile reversible. Do not claim NFR
closure. The normal-load latency remains over 5s and sustained Hindsight 429s
remain far above the less-than-1% error target.

The next blocking action remains managed/dedicated Hindsight concurrency. If
Vectorize cannot provide it, ADR-016 requires Enterprise BYOC or an EU-hosted
persistent deployment before rerunning the acceptance scenarios.

## Deviations from plan

- The experiment improved the capacity run but not the normal-load full-stream
  p95, so it is retained as a safer default profile rather than presented as an
  NFR remediation.
- The deployment workflow again failed after the backend and proxy deployment
  because the backend-only run produced no frontend artifact. This did not
  affect the deployed experiment.
