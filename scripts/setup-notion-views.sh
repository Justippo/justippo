#!/usr/bin/env bash
# Setup Notion board views for EvidenceEU Capstone Project Board.
# Requires: NOTION_TOKEN env var, Python 3, internet.
# Usage: ./scripts/setup-notion-views.sh
set -euo pipefail

NOTION_TOKEN="${NOTION_TOKEN:?NOTION_TOKEN env var required}"
DATABASE_ID="38cbf1cf330681b484d0c68d7fc9505c"

python3 <<'PY'
import json, os, sys, urllib.request, urllib.error

TOKEN = os.environ["NOTION_TOKEN"]
API = "https://api.notion.com/v1"
VERSION = "2026-03-11"
DB = "38cbf1cf330681b484d0c68d7fc9505c"

def notion(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": VERSION, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def notion_safe(method, path, body=None):
    try:
        return notion(method, path, body)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return json.loads(raw)

# Get data_source_id
db = notion("GET", f"/databases/{DB}")
data_sources = db.get("data_sources", [])
if not data_sources:
    print("ERROR: No data_sources found on database")
    sys.exit(1)
ds_id = data_sources[0]["id"]

# Get property IDs
req = urllib.request.Request(
    f"{API}/databases/{DB}", method="GET",
    headers={"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=30) as resp:
    db_old = json.loads(resp.read().decode("utf-8"))
props = db_old.get("properties", {})
TASK_STATUS_ID = props.get("Task Status", {}).get("id", "")
SPRINT_ID = props.get("Sprint", {}).get("id", "")
ASSIGNEES_ID = props.get("Assignees", {}).get("id", "")

print(f"data_source_id: {ds_id}")
print(f"Task Status property_id: {TASK_STATUS_ID}")
print(f"Sprint property_id: {SPRINT_ID}")
print(f"Assignees property_id: {ASSIGNEES_ID}")

# Existing views
existing_views = notion("GET", f"/views?database_id={DB}")
existing_names = set()
for v in existing_views.get("results", []):
    vid = v.get("id")
    detail = notion("GET", f"/views/{vid}")
    existing_names.add(detail.get("name", ""))

def create_view(name, view_type, config):
    if name in existing_names:
        print(f"SKIP: View '{name}' already exists")
        return
    result = notion_safe("POST", "/views", {
        "database_id": DB,
        "data_source_id": ds_id,
        "name": name,
        "type": view_type,
        "configuration": {"type": view_type, **config},
    })
    if "id" in result:
        print(f"OK: Created '{name}' — {result.get('url', result['id'])}")
    else:
        print(f"FAIL: {result.get('message', result)}")

create_view("Board by Status", "board", {
    "group_by": {"type": "status", "property_id": TASK_STATUS_ID, "group_by": "group", "sort": {"type": "manual"}},
    "card_size": "medium",
    "card_layout": "compact",
})

create_view("Board by Sprint", "board", {
    "group_by": {"type": "select", "property_id": SPRINT_ID, "sort": {"type": "manual"}},
    "card_size": "medium",
    "card_layout": "compact",
})

create_view("My Tasks", "table", {
    "table": {"properties": [{"property_id": TASK_STATUS_ID, "visible": True}, {"property_id": SPRINT_ID, "visible": True}]},
})
PY
