import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GitFileStatus:
    path: str
    status: str


@dataclass(frozen=True)
class GitCommit:
    sha: str
    subject: str


@dataclass(frozen=True)
class GitSnapshot:
    project_path: str
    is_git_repo: bool
    repo_root: str
    branch: str
    dirty_count: int
    files: list[GitFileStatus]
    recent_commits: list[GitCommit]
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "project_path": self.project_path,
            "is_git_repo": self.is_git_repo,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "dirty_count": self.dirty_count,
            "files": [file.__dict__ for file in self.files],
            "recent_commits": [commit.__dict__ for commit in self.recent_commits],
            "error": self.error,
        }


def read_git_snapshot(project_path: str, *, timeout: int = 5) -> GitSnapshot:
    normalized = os.path.abspath(os.path.expanduser(project_path))
    if not os.path.isdir(normalized):
        raise FileNotFoundError("项目目录不存在")

    root_result = _run_git(normalized, ["rev-parse", "--show-toplevel"], timeout=timeout)
    if root_result.returncode != 0:
        return GitSnapshot(
            project_path=normalized,
            is_git_repo=False,
            repo_root="",
            branch="",
            dirty_count=0,
            files=[],
            recent_commits=[],
            error=_stderr_or_stdout(root_result) or "不是 Git 仓库",
        )

    repo_root = root_result.stdout.strip()
    branch_result = _run_git(repo_root, ["branch", "--show-current"], timeout=timeout)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    if not branch:
        head_result = _run_git(repo_root, ["rev-parse", "--short", "HEAD"], timeout=timeout)
        branch = head_result.stdout.strip() if head_result.returncode == 0 else "detached"

    status_result = _run_git(repo_root, ["status", "--short"], timeout=timeout)
    files = _parse_status(status_result.stdout if status_result.returncode == 0 else "")
    commits = _read_recent_commits(repo_root, timeout=timeout)

    return GitSnapshot(
        project_path=normalized,
        is_git_repo=True,
        repo_root=repo_root,
        branch=branch,
        dirty_count=len(files),
        files=files,
        recent_commits=commits,
    )


def _run_git(cwd: str, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _parse_status(output: str) -> list[GitFileStatus]:
    files = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip() or line[:2]
        path = line[3:].strip()
        if path:
            files.append(GitFileStatus(path=path, status=status))
    return files


def _read_recent_commits(repo_root: str, *, timeout: int) -> list[GitCommit]:
    result = _run_git(repo_root, ["log", "--pretty=format:%h%x09%s", "-5"], timeout=timeout)
    if result.returncode != 0:
        return []
    commits = []
    for line in result.stdout.splitlines():
        sha, _, subject = line.partition("\t")
        if sha:
            commits.append(GitCommit(sha=sha, subject=subject))
    return commits


def _stderr_or_stdout(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or "").strip()
