import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

import app as webapp
from services.git_status import read_git_snapshot


pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git CLI is required")


def test_read_git_snapshot_reports_branch_dirty_files_and_commits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial commit")
    (repo / "README.md").write_text("hello\nchanged\n", encoding="utf-8")

    snapshot = read_git_snapshot(str(repo))

    assert snapshot.is_git_repo is True
    assert snapshot.repo_root
    assert snapshot.branch in {"master", "main"}
    assert snapshot.dirty_count == 1
    assert snapshot.files[0].path == "README.md"
    assert snapshot.recent_commits[0].subject == "initial commit"


def test_workspace_git_api_handles_non_git_directory(tmp_path):
    project = Path(tempfile.mkdtemp(prefix="opencode-non-git-"))
    app = webapp.create_app({"TESTING": True})

    try:
        with app.test_client() as client:
            response = client.get("/api/workspace/git", query_string={"project_path": str(project)})
    finally:
        shutil.rmtree(project, ignore_errors=True)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["git"]["is_git_repo"] is False
    assert payload["git"]["dirty_count"] == 0
    assert payload["git"]["error"]


def test_workspace_git_api_rejects_missing_project_path():
    app = webapp.create_app({"TESTING": True})

    with app.test_client() as client:
        response = client.get("/api/workspace/git")

    assert response.status_code == 400
    assert "project_path" in response.get_json()["error"]


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
