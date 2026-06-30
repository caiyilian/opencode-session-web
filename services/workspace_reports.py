from typing import Any


def build_task_report(
    *,
    task: dict[str, Any],
    linked_sessions: list[dict[str, Any]],
    command_runs: list[dict[str, Any]],
    git_snapshot: dict[str, Any] | None,
) -> str:
    lines = [
        f"# {task['title']}",
        "",
        f"- Status: {task['status']}",
        f"- Project: {task['project_path'] or 'N/A'}",
    ]
    if task.get("description"):
        lines.extend(["", "## Description", "", task["description"]])

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

    return "\n".join(lines).strip() + "\n"
