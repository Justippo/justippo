"""Shared Notion API helpers for sync workflows.

Usage in GitHub Actions heredocs:
    import sys; sys.path.insert(0, "scripts")
    from notion_helpers import notion_request, notion_query_all, find_page_by_issue_number

Environment variables required:
    NOTION_TOKEN — Notion integration token
    NOTION_DATABASE_ID — Target database ID
"""
import json
import os
import time
import urllib.error
import urllib.request

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "38cbf1cf330681b484d0c68d7fc9505c")


def notion_request(method, path, body=None, timeout=30):
    """Make authenticated Notion API request.

    Surfaces Notion's error body on HTTP errors so callers can diagnose
    400/404/500 responses instead of seeing only the status code."""
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        f"{NOTION_API}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        print(f"Notion {method} {path} failed HTTP {exc.code}: {raw[:500]}")
        raise


def notion_query_all(database_id=None, filter_obj=None):
    """Query all pages from Notion database with auto-pagination."""
    db_id = database_id or NOTION_DATABASE_ID
    all_results = []
    start_cursor = None
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        if filter_obj:
            body["filter"] = filter_obj
        _, page = notion_request("POST", f"/databases/{db_id}/query", body)
        all_results.extend(page.get("results", []))
        if not page.get("has_more"):
            break
        start_cursor = page.get("next_cursor")
        time.sleep(0.35)
    return all_results


def find_page_by_issue_number(issue_number, database_id=None):
    """Find Notion page by GitHub issue number (#N format). Returns page_id or None."""
    pages = notion_query_all(database_id, {"property": "GitHub", "rich_text": {"contains": f"#{issue_number}"}})
    for page in pages:
        github_prop = page.get("properties", {}).get("GitHub", {}).get("rich_text", [])
        full_text = "".join(t.get("plain_text", "") for t in github_prop)
        refs = [r.strip() for r in full_text.replace(" ", "").split(",") if r.strip()]
        if f"#{issue_number}" in refs:
            return page.get("id")
    return None


def extract_issue_numbers_from_page(page):
    """Extract list of issue numbers from a Notion page's GitHub property."""
    github_prop = page.get("properties", {}).get("GitHub", {}).get("rich_text", [])
    full_text = "".join(t.get("plain_text", "") for t in github_prop)
    refs = [r.strip() for r in full_text.replace(" ", "").split(",") if r.strip()]
    numbers = []
    for ref in refs:
        m = __import__("re").match(r"#(\d+)", ref)
        if m:
            numbers.append(int(m.group(1)))
    return numbers


def extract_labels(page):
    """Extract labels from a Notion page's Tags multi_select property."""
    tags_prop = page.get("properties", {}).get("Tags", {}).get("multi_select", [])
    return [t.get("name", "") for t in tags_prop if t.get("name")]


def extract_assignees(page):
    """Extract assignees from a Notion page's Assignees multi_select property."""
    assignees_prop = page.get("properties", {}).get("Assignees", {}).get("multi_select", [])
    return [a.get("name", "") for a in assignees_prop if a.get("name")]


def build_notion_properties(title, issue_number, state, labels=None, assignees=None):
    """Build Notion page properties dict.

    Args:
        title: Issue title
        issue_number: GitHub issue number
        state: "open" or "closed"
        labels: List of label names
        assignees: List of assignee usernames
    """
    is_closed = state == "closed"
    labels = labels or []
    assignees = assignees or []

    props = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Task Status": {"status": {"status": "Done" if is_closed else "To Do"}},
        "Completed": {"checkbox": is_closed},
        "GitHub": {"rich_text": [{"text": {"content": f"#{issue_number}"}}]},
        "Tags": {"multi_select": [{"name": label} for label in labels[:10] if label]},
        "Priority": {"select": {"name": _priority_from_labels(labels)}},
    }
    if assignees:
        props["Assignees"] = {"multi_select": [{"name": a} for a in assignees[:10]]}
    # Evidence-based contribution column. Populated by
    # scripts/populate_notion_contributors.py (or manually); left empty here
    # because PR authors/reviewers aren't known at issue-sync time.
    props["Actual Contributors"] = {"rich_text": []}
    return props


def priority_from_labels(labels):
    """Derive priority from GitHub labels. Shared across all sync workflows."""
    label_set = {label.lower() for label in labels}
    if "priority: critical" in label_set or "p0" in label_set:
        return "Critical"
    if "priority: high" in label_set or "p1" in label_set:
        return "High"
    if "priority: medium" in label_set or "p2" in label_set:
        return "Medium"
    if "priority: low" in label_set or "p3" in label_set:
        return "Low"
    return "Medium"


def sprint_from_labels(labels):
    """Map sprint-N labels to Notion Sprint select values. Shared across all sync workflows."""
    label_set = {label.lower() for label in labels}
    if "sprint-1" in label_set:
        return "Sprint 1"
    if "sprint-2" in label_set:
        return "Sprint 2"
    if "sprint-3" in label_set:
        return "Sprint 3"
    return None
