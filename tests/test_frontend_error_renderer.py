import shutil
import subprocess
from pathlib import Path

import pytest


def test_stream_error_renderer_outputs_friendly_details(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for frontend helper smoke")

    source = Path("static/js/app.js").read_text(encoding="utf-8")
    start = source.index("function escHtml")
    end = source.index("function fmtTokens")
    helper_source = source[start:end]

    script = tmp_path / "check_stream_error_renderer.js"
    script.write_text(
        f"""
const assert = require('assert');
global.window = {{}};
global.document = {{
  createElement: () => {{
    let text = '';
    return {{
      set textContent(value) {{
        text = String(value ?? '');
      }},
      get innerHTML() {{
        return text
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
      }},
    }};
  }},
}};

{helper_source}

const friendly = renderStreamError('模型额度或速率已受限，请切换模型或稍后重试。\\n\\n技术细节：quota <exceeded>');
assert(friendly.includes('class="error-msg"'));
assert(friendly.includes('class="error-title"'));
assert(friendly.includes('模型额度或速率已受限'));
assert(friendly.includes('<details class="error-details">'));
assert(friendly.includes('<summary>技术细节</summary>'));
assert(friendly.includes('quota &lt;exceeded&gt;'));

const nestedJson = renderStreamError(JSON.stringify({{ error: {{ message: 'model not found' }} }}));
assert(nestedJson.includes('model not found'));
assert(!nestedJson.includes('[object Object]'));
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [node, str(script)],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
