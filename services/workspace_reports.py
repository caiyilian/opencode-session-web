from typing import Any


def build_task_report(
    *,
    task: dict[str, Any],
    linked_sessions: list[dict[str, Any]],
    command_runs: list[dict[str, Any]],
    git_snapshot: dict[str, Any] | None,
    task_events: list[dict[str, Any]] | None = None,
) -> str:
    latest_run = command_runs[0] if command_runs else None
    git_dirty_count = 0
    git_branch = ""
    if git_snapshot and git_snapshot.get("is_git_repo"):
        git_dirty_count = int(git_snapshot.get("dirty_count") or 0)
        git_branch = str(git_snapshot.get("branch") or "detached")

    lines = [
        f"# {task['title']}",
        "",
        f"- Status: {task['status']}",
        f"- Project: {task['project_path'] or 'N/A'}",
    ]
    if task.get("description"):
        lines.extend(["", "## Description", "", task["description"]])

    lines.extend(
        [
            "",
            "## Delivery Summary",
            "",
            f"- Task status: {task['status']}",
            f"- Linked sessions: {len(linked_sessions)}",
            f"- Validation runs: {len(command_runs)}",
        ]
    )
    if latest_run:
        exit_code = "no exit code" if latest_run.get("exit_code") is None else f"exit {latest_run['exit_code']}"
        lines.append(
            f"- Latest validation: {latest_run['command_label']} {latest_run['status']} ({exit_code})"
        )
    if git_snapshot and git_snapshot.get("is_git_repo"):
        lines.append(f"- Git snapshot: {git_branch}, {git_dirty_count} dirty files")
    elif git_snapshot:
        lines.append(f"- Git snapshot: {git_snapshot.get('error') or 'Project is not a Git repository'}")
    else:
        lines.append("- Git snapshot: unavailable")

    lines.extend(["", "## PR Description Draft", "", "### Summary"])
    lines.append(f"- {task['title']}")
    if task.get("description"):
        lines.append(f"- {task['description']}")
    lines.extend(["", "### Validation"])
    if command_runs:
        for run in command_runs[:5]:
            exit_code = "no exit code" if run.get("exit_code") is None else f"exit {run['exit_code']}"
            lines.append(f"- {run['command_label']}: {run['status']} ({exit_code})")
    else:
        lines.append("- Not run")

    lines.extend(["", "## Acceptance Notes"])
    lines.append("- [x] Workspace task and linked sessions reviewed")
    lines.append("- [x] Git snapshot captured" if git_snapshot else "- [ ] Git snapshot captured")
    lines.append(
        "- [x] Validation evidence recorded"
        if command_runs
        else "- [ ] Validation evidence recorded"
    )

    lines.extend(["", "## Linked Sessions"])
    if linked_sessions:
        for session in linked_sessions:
            lines.append(
                f"- `{session['id']}` {session['title'] or 'Untitled session'}"
                f" ({session['model'] or 'N/A'}, updated {session['time_updated']})"
            )
    else:
        lines.append("- No linked sessions")

    lines.extend(["", "## Git Snapshot"])
    if git_snapshot and git_snapshot.get("is_git_repo"):
        lines.extend(
            [
                f"- Branch: {git_snapshot.get('branch') or 'detached'}",
                f"- Dirty files: {git_snapshot.get('dirty_count', 0)}",
                f"- Repo root: {git_snapshot.get('repo_root') or 'N/A'}",
            ]
        )
        files = git_snapshot.get("files") or []
        if files:
            lines.append("- Changed files:")
            for item in files[:10]:
                lines.append(f"  - `{item.get('status', '')}` {item.get('path', '')}")
    elif git_snapshot:
        lines.append(f"- {git_snapshot.get('error') or 'Project is not a Git repository'}")
    else:
        lines.append("- Git snapshot unavailable")

    lines.extend(["", "## Validation Runs"])
    if command_runs:
        for run in command_runs:
            exit_code = "no exit code" if run.get("exit_code") is None else f"exit {run['exit_code']}"
            lines.extend(
                [
                    f"- {run['command_label']}: {run['status']} ({exit_code}, {run['duration_ms']} ms)",
                ]
            )
            output = (run.get("output") or "").strip()
            if output:
                lines.extend(["", "```text", output[-2000:], "```", ""])
    else:
        lines.append("- No validation runs linked to this task")

    lines.extend(["", "## Task Timeline"])
    if task_events:
        for event in task_events[:10]:
            payload = event.get("payload") or {}
            git = payload.get("git") if isinstance(payload, dict) else None
            detail = ""
            if isinstance(git, dict) and git.get("is_git_repo"):
                detail = f" ({git.get('branch') or 'detached'}, {git.get('dirty_count', 0)} dirty files)"
            lines.append(f"- {event['title']} [{event['event_type']}]{detail}")
    else:
        lines.append("- No task events recorded")

    return "\n".join(lines).strip() + "\n"
