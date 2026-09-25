"""Restore a JSON export of /api/tasks after the first Redis PVC migration."""

import json
import sys
from urllib.request import Request, urlopen


def api(path, method, payload):
    request = Request(
        "http://localhost:8080" + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 scripts/restore_tasks.py tasks-backup.json")
    with open(sys.argv[1], encoding="utf-8") as source:
        tasks = json.load(source)
    if not isinstance(tasks, list):
        raise SystemExit("Expected a JSON array from GET /api/tasks")
    for task in reversed(tasks):
        created = api("/api/tasks", "POST", {"title": task["title"]})
        if task["status"] != "todo":
            api(f"/api/tasks/{created['id']}", "PATCH", {"status": task["status"]})
    print(f"Restored {len(tasks)} tasks with new IDs")


if __name__ == "__main__":
    main()
