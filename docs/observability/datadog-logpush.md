# Datadog Logpush Setup Guide — Cloudflare → Datadog

**Date:** 2026-06-18
**Status:** Setup guide (dashboard-only, no code changes)
**NFRs addressed:** NFR-01 (p95 latency), NFR-02 (error rate), NFR-09 (CDN load time)

---

## Overview

Cloudflare Logpush streams log data from Cloudflare's edge directly to Datadog.
This is a pure dashboard configuration — no code changes required. It provides
Server-side visibility into Worker invocations, D1 queries, and Pages Functions
that complement the client-side RUM data from `@datadog/browser-rum`.

---

## Prerequisites

- Datadog account with API key and US/EU site configured
- Cloudflare account with Workers, D1, and Pages provisioned
- Cloudflare Workers Paid tier (Logpush requires Workers Paid)

---

## Step 1: Get Datadog API Key

1. Go to **Datadog → Organization Settings → API Keys**
2. Create a new API key named `evidence-eu-logpush`
3. Copy the key — you'll need it in Step 3

---

## Step 2: Navigate to Cloudflare Logpush

1. Log in to the **Cloudflare Dashboard**
2. Select your domain or account
3. Go to **Analytics & Logs → Logpush**
4. Click **Create a Logpush job**

---

## Step 3: Configure the Datadog Destination

1. **Select a destination:** Choose **Datadog**
2. Enter the following:
   - **Datadog API Key:** Paste the key from Step 1
   - **Datadog Site:** `datadoghq.com` (US) or `datadoghq.eu` (EU)
   - **Service:** `evidence-eu`
   - **Source:** `cloudflare` (auto-detected)
3. Click **Proceed**

---

## Step 4: Select Datasets

Enable the following Cloudflare datasets for EvidenceEU:

| Dataset | What It Provides | NFR Evidence |
|---------|-----------------|--------------|
| **Workers Trace Events** | Worker invocation logs, exceptions, console.log, CPU time, wall time | NFR-01 (p95 latency per Worker), NFR-02 (Worker error rate) |
| **D1 Query Analytics** | SQL query execution time, rows scanned, query type | NFR-01 (database query latency breakdown) |
| **Pages Functions** | Pages Function invocations, edge logs, deployment metadata | NFR-09 (CDN response time, cache hit rate) |

### Recommended Filter (optional)

To reduce log volume and cost, add a filter:
```
CF.Worker.Status != "ok"
```
This only pushes error/exception logs. Remove the filter for full observability
during the capstone demo period.

---

## Step 5: Configure Log Fields

For each dataset, select these fields:

### Workers Trace Events
- `EventTimestampMs`
- `Outcome` (ok, error, exception)
- `ScriptName`
- `CPUTime`
- `WallTime`
- `RequestURI`
- `RequestMethod`
- `RequestStatus`
- `ResponseHttpStatus`
- `Exceptions`
- `Logs` (console.log output)
- `CFRay`

### D1 Query Analytics
- `QueryDuration`
- `RowsRead`
- `RowsWritten`
- `QueryType`
- `DatabaseName`

### Pages Functions
- `RequestURL`
- `RequestMethod`
- `ResponseStatus`
- `RayID`
- `DeploymentID`

---

## Step 6: Confirm and Enable

1. Review the job configuration
2. Click **Create Job**
3. Verify logs appear in Datadog → **Logs → Search** within 1-2 minutes

---

## Datadog Dashboard Setup (Optional)

After Logpush is active, create these dashboards in Datadog:

### 1. API Performance Dashboard (NFR-01)
- **Metric:** `evidence_eu.request.duration` (from custom metrics forwarder)
- **Widget:** Timeseries — p50, p95, p99 latency by route
- **Log source:** Workers Trace Events — filter by `ScriptName:evidence-eu-api`

### 2. Error Rate Dashboard (NFR-02)
- **Metric:** `evidence_eu.request.count` filtered by `status:5xx`
- **Widget:** Query value — error rate = 5xx / total requests
- **Alert:** > 1% error rate → email notification

### 3. Frontend RUM Dashboard (NFR-09)
- **Source:** `@datadog/browser-rum` data
- **Widgets:** Core Web Vitals (LCP, FID, CLS), page load time, JS errors
- **Filter:** `service:evidence-eu-frontend`

---

## Cost Considerations

- Cloudflare Logpush: $0.05 per million requests
- Datadog: Custom metrics ($15 per 100 custom metrics/month)
- Current custom metrics: 2 (request.duration, request.count) = well within free tier
- Log ingestion: ~0.5 GB/month for capstone traffic = well within free tier

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No logs in Datadog | Wrong API key or site | Verify key in Datadog → Organization Settings → API Keys |
| Logs delayed > 5 min | Logpush batching | Normal — Cloudflare batches logs every 60s |
| Missing D1 query data | D1 Query Analytics not enabled | Enable in Cloudflare → D1 → Settings → Query Analytics |
| High Datadog cost | Too many log fields | Reduce fields in Step 5 or add filter in Step 4 |
