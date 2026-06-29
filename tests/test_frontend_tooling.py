import json
from pathlib import Path


def test_frontend_package_exposes_vite_build_script():
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))

    assert package["scripts"]["build"] == (
        "tsc --noEmit -p tsconfig.json && tsc --noEmit -p tsconfig.node.json && vite build"
    )
    assert "react" in package["dependencies"]
    assert "react-dom" in package["dependencies"]
    assert "vite" in package["dependencies"]
    assert "typescript" in package["dependencies"]
