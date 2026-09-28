"""Promote a successful CodeBuild image set to the Taskboard GitOps repository.

Uses GitHub's Contents API so CodeBuild does not need to clone the deployment
repository or put a GitHub token in a git remote URL.
"""

import base64
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_REPO = "zawarvyankatesh/application_code_argocd_project"
GITOPS_REPO = "zawarvyankatesh/HELM_chart_CD_ArgoCDproject"
VALUES_PATH = "charts/taskboard/values.yaml"
API = "https://api.github.com"
IMAGES = ("web", "api", "redis")


def github_json(path: str, token: str | None = None, payload: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "taskboard-codebuild-gitops",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        API + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method="PUT" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not log response bodies or authentication headers from GitHub.
        raise RuntimeError(f"GitHub API {request.method} {path}: HTTP {exc.code}") from None
    except URLError as exc:
        raise RuntimeError(f"GitHub API {request.method} {path}: connection failed") from exc


def updated_values(content: str, repositories: dict[str, str], image_tag: str) -> str:
    """Change only the image fields of the three known values.yaml sections."""
    if not re.fullmatch(r"[0-9a-f]{12}", image_tag):
        raise ValueError("Expected a 12-character lowercase Git commit tag")
    if not re.search(r"(?m)^  - name: ecr-pull\s*$", content):
        raise ValueError("GitOps values must reference the ecr-pull imagePullSecret")

    values = {
        name: {
            "repository": repositories[name],
            "tag": "7-alpine" if name == "redis" else image_tag,
            "pullPolicy": "IfNotPresent",
        }
        for name in IMAGES
    }
    for name in IMAGES:
        if not repositories[name].endswith(f"/taskboard-{name}"):
            raise ValueError(f"Unexpected ECR repository for {name}")

    seen: set[tuple[str, str]] = set()
    section = ""
    in_image = False
    result = []
    for line in content.splitlines(keepends=True):
        top = re.match(r"^([a-zA-Z][\w-]*):", line)
        if top:
            section = top.group(1)
            in_image = False
        if section in values and line.startswith("  image:"):
            in_image = True
        elif in_image and not line.startswith(("    ", "  image:")):
            in_image = False

        field = re.match(r"^(    )(repository|tag|pullPolicy):[^\r\n]*(\r?\n?)$", line)
        if section in values and in_image and field:
            key = (section, field.group(2))
            if key in seen:
                raise ValueError(f"Duplicate image field: {key}")
            seen.add(key)
            line = f"{field.group(1)}{field.group(2)}: {values[section][field.group(2)]}{field.group(3)}"
        result.append(line)

    required = {(section, field) for section in IMAGES for field in ("repository", "tag", "pullPolicy")}
    if seen != required:
        raise ValueError(f"Missing image fields in GitOps values: {sorted(required - seen)}")
    return "".join(result)


def main() -> None:
    source_sha = os.environ["CODEBUILD_RESOLVED_SOURCE_VERSION"].lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Expected a full Git commit SHA from CodeBuild")

    # A slow/queued older build must not roll back a more recent main commit.
    latest = github_json(f"/repos/{APP_REPO}/git/ref/heads/main")["object"]["sha"]
    if latest != source_sha:
        print(f"Skipping GitOps update: build {source_sha[:12]} is no longer app main")
        return

    token = os.environ["GITOPS_GITHUB_TOKEN"]
    if not token:
        raise ValueError("GITOPS_GITHUB_TOKEN is empty")
    path = f"/repos/{GITOPS_REPO}/contents/{VALUES_PATH}"
    current = github_json(path + "?ref=main", token=token)
    content = base64.b64decode(current["content"]).decode("utf-8")
    repositories = {
        "web": os.environ["WEB_REPOSITORY_URI"],
        "api": os.environ["API_REPOSITORY_URI"],
        "redis": os.environ["REDIS_REPOSITORY_URI"],
    }
    new_content = updated_values(content, repositories, source_sha[:12])
    if new_content == content:
        print(f"GitOps already points to image tag {source_sha[:12]}")
        return

    # GitHub checks the blob SHA. Concurrent edits to values.yaml cause a
    # conflict instead of silently replacing a human's newer change.
    published = github_json(path, token=token, payload={
        "message": f"deploy: taskboard images {source_sha[:12]}",
        "content": base64.b64encode(new_content.encode()).decode("ascii"),
        "sha": current["sha"],
        "branch": "main",
    })
    print(f"Published GitOps commit {published['commit']['sha']} for {source_sha[:12]}")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"GitOps promotion failed: {exc}", file=sys.stderr)
        sys.exit(1)
