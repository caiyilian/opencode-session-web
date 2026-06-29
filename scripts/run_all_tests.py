import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def run(label: str, command: list[str], cwd: Path) -> None:
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def npm_command() -> str:
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm is required to run frontend tests")
    return npm


def main() -> None:
    npm = npm_command()
    run("Python tests", [sys.executable, "-m", "pytest"], ROOT)
    run("Frontend unit tests", [npm, "test"], FRONTEND)
    run("Frontend E2E tests", [npm, "run", "test:e2e"], FRONTEND)


if __name__ == "__main__":
    main()
