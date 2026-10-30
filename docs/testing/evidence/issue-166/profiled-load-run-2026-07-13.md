# Issue #166 — instrumented production load run

**Date:** 2026-07-13  
**Target:** `https://evidence-eu-worker.mc146.workers.dev`  
**Deployed commit:** `8bf75bb39a4cf38f8d912c56995d0174c3dc5ac7`  
**Scenario:** Real Hindsight Cloud recall followed by streamed Apertus answer generation

PR #173 introduced event-aware client timings and server-side Datadog stage
metrics. The public SSE event contract was unchanged.

## 10-VU latency run

Locust ran for 60 seconds with 10 users and a 2 users/second ramp.

| Measurement | Samples | p50 | p95 | p99 |
|-------------|--------:|----:|----:|----:|
| First result | 105 | 1.019s | 10.658s | 13.764s |
| Answer TTFT (first result → first answer token) | 105 | 0.242s | 0.521s | 0.620s |
| Answer stream (first answer token → done) | 105 | 0.736s | 3.652s | 4.468s |
| Post-retrieval (first result → done) | 105 | 0.988s | 4.154s | 4.488s |
| Full stream | 105 | 2.695s | 11.950s | 14.208s |

Completed streams: **105**. Errors: **0 (0.00%)**.

NFR-01 remains failed: full-stream p95 is 11.950s against the 5s target.
First-result p95 alone is 10.658s, while answer TTFT p95 is 0.521s. The
dominant slow-tail stage is therefore Hindsight retrieval, not answer startup.

## 50-VU capacity run

Locust ran for 60 seconds with 50 users and a 5 users/second ramp.

| Measurement | Samples | p50 | p95 | p99 |
|-------------|--------:|----:|----:|----:|
| First result (successful recalls) | 331 | 2.665s | 10.084s | 17.987s |
| Answer TTFT | 331 | 0.244s | 1.087s | 1.592s |
| Answer stream | 331 | 0.991s | 4.717s | 5.774s |
| Post-retrieval | 331 | 1.429s | 5.293s | 6.039s |
| Full stream (successful and failed) | 432 | 4.425s | 12.354s | 18.068s |

Completed streams: **432**. Errors: **101 (23.38%)**.

Every failure was a Hindsight Cloud `429 Too Many Requests` response from the
real recall endpoint. NFR-02 remains failed against the less-than-1% target and
the Issue #166 zero-429 acceptance criterion.

The lower error rate than the earlier 31.33% run is not treated as a completed
remediation: no provider capacity change was confirmed, and both runs remain
far above the acceptance threshold.

## Capacity conclusion

Application retries cannot satisfy the requirement. The next blocking action
is written confirmation from Vectorize of a managed/dedicated concurrency tier
that can support the 50-VU acceptance run. If that cannot be provided, ADR-016
requires migration to Enterprise BYOC or an EU-hosted persistent deployment.

## Deployment note

GitHub Actions run
[`29267308377`](https://github.com/chindris-mihai-alexandru/evidence-eu/actions/runs/29267308377)
successfully deployed the backend and proxy Workers. The combined deploy job
then failed while downloading the absent frontend artifact for this
backend-only change. Both public health endpoints returned `status: ok` before
the load runs. This CI artifact-orchestration failure did not prevent the
profiling backend from reaching production.

## Deviations from plan

- No managed Hindsight capacity increase had been confirmed before the run, so
  these are diagnostic measurements rather than final acceptance evidence.
- The main workflow failed after the backend deploy because a backend-only
  change does not produce the frontend artifact that the deploy job downloads
  unconditionally.
