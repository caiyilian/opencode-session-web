"""Test opencode subprocess directly."""
import subprocess, json, time

# Try with DEVNULL stdin
proc = subprocess.Popen(
    ['opencode', 'run', '-s', 'ses_125211dfdffebgQQg23K6iYSco', 'say hello', '--format', 'json'],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
    stdin=subprocess.DEVNULL,
)

lines = []
try:
    for line in proc.stdout:
        line = line.strip()
        if line:
            lines.append(line)
            print('LINE:', line[:100], flush=True)
    proc.wait(timeout=10)
    print(f'EXIT: {proc.returncode}', flush=True)
except subprocess.TimeoutExpired:
    proc.kill()
    print(f'TIMEOUT after {len(lines)} lines', flush=True)

# Print stderr
err = proc.stderr.read()
if err:
    print('STDERR:', err[:500], flush=True)
