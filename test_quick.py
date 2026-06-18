"""Quick test: verify API works."""
import sys, os, time, json, urllib.request, threading
os.chdir(r'E:\projects\opencode-session-web')
sys.path.insert(0, '.')
from app import app

t = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=18778, debug=False, threaded=True), daemon=True)
t.start()
time.sleep(2)

# Test sessions API
r = urllib.request.urlopen('http://127.0.0.1:18778/api/sessions?limit=200')
d = json.loads(r.read())
print(f'Sessions count: {len(d["sessions"])}, total: {d["total"]}')
if d['sessions']:
    print(f'First: {d["sessions"][0]["title"]}')

# Test stats
r = urllib.request.urlopen('http://127.0.0.1:18778/api/stats')
s = json.loads(r.read())
print(f'Stats: {s["total_sessions"]} sessions, {s["total_projects"]} projects')

# Test page
r = urllib.request.urlopen('http://127.0.0.1:18778/')
html = r.read().decode()
print(f'Page: {r.status} {len(html)} bytes')
print(f'Has app.js: {"app.js" in html}')

import urllib.error
# Test file API
r = urllib.request.urlopen('http://127.0.0.1:18778/api/files?path=' + urllib.parse.quote('E:\\projects\\opencode-session-web'))
f = json.loads(r.read())
print(f'Files: {len(f["entries"])} entries')

print('\nAll OK')
