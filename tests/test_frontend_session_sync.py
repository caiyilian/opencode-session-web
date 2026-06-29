import shutil
import subprocess
from pathlib import Path

import pytest


def test_session_sync_helpers_refresh_and_connect(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for frontend helper smoke")

    source = Path("static/js/app.js").read_text(encoding="utf-8")
    start = source.index("async function refreshSessionList")
    end = source.index("// ── Markdown rendering ──")
    helper_source = source[start:end]

    script = tmp_path / "check_session_sync.js"
    script.write_text(
        """
const assert = require('assert');

let sessions = [];
let allDirectories = [];
let allSessions = [];
let currentSessionId = 'keep';
let compareIds = ['keep', 'drop'];
let syncEventSource = null;
let syncRefreshTimer = null;
const SESSION_CACHE = { keep: { stale: true }, old: { stale: true } };
let renderCount = 0;
let showedList = false;

const responses = {
  '/api/directories': { directories: [{ path: 'C:/repo', name: 'repo' }] },
  '/api/sessions?limit=200': { sessions: [{ id: 'keep', title: 'Keep' }] },
};

async function api(path) {
  return responses[path];
}

function renderSidebar() {
  renderCount += 1;
}

function showList() {
  showedList = true;
  currentSessionId = null;
}

class FakeEventSource {
  static instances = [];
  static CLOSED = 2;

  constructor(url) {
    this.url = url;
    this.readyState = 1;
    this.listeners = {};
    FakeEventSource.instances.push(this);
  }

  addEventListener(name, callback) {
    this.listeners[name] = callback;
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
}

global.EventSource = FakeEventSource;

"""
        + helper_source
        + """

(async () => {
  await refreshSessionList();
  assert.deepStrictEqual(allDirectories, [{ path: 'C:/repo', name: 'repo' }]);
  assert.deepStrictEqual(allSessions, [{ id: 'keep', title: 'Keep' }]);
  assert.deepStrictEqual(sessions, allSessions);
  assert.deepStrictEqual(compareIds, ['keep']);
  assert.strictEqual(renderCount, 1);

  connectSessionEvents();
  assert.strictEqual(FakeEventSource.instances.length, 1);
  assert.strictEqual(FakeEventSource.instances[0].url, '/api/events');
  assert.strictEqual(typeof FakeEventSource.instances[0].listeners.session_change, 'function');

  responses['/api/sessions?limit=200'] = { sessions: [] };
  handleSessionChangeEvent({ data: JSON.stringify({ session: { id: 'keep' }, previous: { id: 'old' } }) });
  assert.strictEqual('keep' in SESSION_CACHE, false);
  assert.strictEqual('old' in SESSION_CACHE, false);

  await new Promise(resolve => setTimeout(resolve, 350));
  assert.strictEqual(showedList, true);
  assert.strictEqual(currentSessionId, null);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
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
