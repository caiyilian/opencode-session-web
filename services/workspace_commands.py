import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any


COMMAND_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


@dataclass(frozen=True)
class WorkspaceCommand:
    key: str
    label: str
    argv: list[str]
    cwd: str = "."
    description: str = ""
    requires_confirmation: bool = False
    safety_note: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "argv": self.argv,
            "cwd": self.cwd,
            "description": self.description,
            "requires_confirmation": self.requires_confirmation,
            "safety_note": self.safety_note,
        }


@dataclass(frozen=True)
class CommandExecution:
    status: str
    exit_code: int | None
    output: str
    duration_ms: int
    started_at: int
    finished_at: int
    cwd: str


def parse_workspace_commands(raw: Any) -> list[WorkspaceCommand]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, list):
        raise ValueError("Workspace commands config must be a list")

    commands = []
    seen_keys = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Workspace command entries must be objects")
        key = str(item.get("key", "")).strip()
        if not COMMAND_KEY_RE.match(key):
            raise ValueError(f"Invalid workspace command key: {key}")
        if key in seen_keys:
            raise ValueError(f"Duplicate workspace command key: {key}")
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(str(part).strip() for part in argv):
            raise ValueError(f"Workspace command {key} must define a non-empty argv list")
        cwd = str(item.get("cwd", ".") or ".").strip()
        if os.path.isabs(cwd):
            raise ValueError(f"Workspace command {key} cwd must be relative")
        if ".." in cwd.replace("\\", "/").split("/"):
            raise ValueError(f"Workspace command {key} cwd cannot contain '..'")
        commands.append(
            WorkspaceCommand(
                key=key,
                label=str(item.get("label") or key).strip(),
                argv=[str(part) for part in argv],
                cwd=cwd,
                description=str(item.get("description") or "").strip(),
                requires_confirmation=bool(item.get("requires_confirmation", False)),
                safety_note=str(item.get("safety_note") or "").strip(),
            )
        )
        seen_keys.add(key)
    return commands


def find_workspace_command(commands: list[WorkspaceCommand], key: str) -> WorkspaceCommand | None:
    return next((command for command in commands if command.key == key), None)


def require_workspace_command_confirmation(command: WorkspaceCommand, confirmed: Any) -> None:
    if command.requires_confirmation and confirmed is not True:
        raise ValueError("命令需要确认后才能运行")


def run_workspace_command(
    command: WorkspaceCommand,
    *,
    project_path: str,
    process_manager,
    timeout: int,
    output_limit: int = 20000,
) -> CommandExecution:
    project_root = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.isdir(project_root):
        raise FileNotFoundError("项目目录不存在")

    cwd = resolve_workspace_command_cwd(project_root, command.cwd)
    started_at = int(time.time() * 1000)
    start = time.monotonic()
    proc = process_manager.start(
        command.argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    try:
        try:
            output, _ = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
            status = "success" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            process_manager.terminate(proc, timeout=2)
            output = exc.output or ""
            exit_code = None
            status = "timeout"
    finally:
        process_manager.unregister(proc)

    finished_at = int(time.time() * 1000)
    return CommandExecution(
        status=status,
        exit_code=exit_code,
        output=truncate_command_output(output, output_limit),
        duration_ms=int((time.monotonic() - start) * 1000),
        started_at=started_at,
        finished_at=finished_at,
        cwd=cwd,
    )


def resolve_workspace_command_cwd(project_root: str, relative_cwd: str) -> str:
    candidate = os.path.abspath(os.path.join(project_root, relative_cwd or "."))
    try:
        common = os.path.commonpath([project_root, candidate])
    except ValueError as exc:
        raise ValueError("命令工作目录必须位于项目目录内") from exc
    if common != project_root:
        raise ValueError("命令工作目录必须位于项目目录内")
    if not os.path.isdir(candidate):
        raise FileNotFoundError("命令工作目录不存在")
    return candidate


def truncate_command_output(output: str | bytes | None, limit: int) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    text = str(output)
    if len(text) <= limit:
        return text
    return text[-limit:]
