content = open('app.py', 'r', encoding='utf-8').read()

# Match step_finish handler: 3 lines followed by elif
# Line N:   elif event_type == "step_finish":
# Line N+1:     tokens = part.get("tokens", {})
# Line N+2:     yield f"event: done...
# Line N+3: elif event_type and event_type not in ("step_start", "step_finish"):
import re

def fix_step_finish(content, var_name='event_type'):
    """Replace step_finish handlers to only send done for 'stop' reason."""
    pattern = (
        rf'(\s+)(elif {var_name} == "step_finish":)\n'
        rf'\1    tokens = part\.get\("tokens", {{}}\)\n'
        rf'\1    yield f"event: done\\ndata: .*?"\n'
        rf'(    elif {var_name} and {var_name} not in \("step_start", "step_finish"\):)'
    )
    replacement = (
        r'\1\2\n'
        r'\1    reason = part.get("reason", "")\n'
        r'\1    tokens = part.get("tokens", {})\n'
        r'\1    if reason == "stop":\n'
        r'\1        yield f"event: done\\ndata: ' + '{\\"session_id\\": \\"' + ' + var_name.replace("event_","") + '_id}\\"...}"\n'
    )
    
    # Simpler: multiline string replacement
    return content

# Use simple string replacement for each occurrence
# Find the exact blocks by their unique context
lines = content.split('\n')
result = []
i = 0
while i < len(lines):
    line = lines[i]
    # Check if this is a step_finish handler
    if ('elif event_type == "step_finish":' in line or 'elif ev_type == "step_finish":' in line):
        indent = line[:len(line) - len(line.lstrip())]
        sub_indent = indent + '    '
        # Look ahead: next line should have tokens = part.get
        if i+2 < len(lines) and 'tokens = part.get' in lines[i+1] and 'yield' in lines[i+2]:
            result.append(line)  # elif ... step_finish:
            result.append(sub_indent + 'reason = part.get("reason", "")')
            result.append(sub_indent + 'tokens = part.get("tokens", {})')
            result.append(sub_indent + 'if reason == "stop":')
            result.append(sub_indent + '    yield f"event: done\\ndata: {json.dumps({\\"session_id\\": session_id, \\"tokens\\": tokens, \\"cost\\": part.get(\\"cost\\", 0)})}\\n\\n"')
            i += 3  # Skip the 3 lines we replaced
            continue
    result.append(line)
    i += 1

content = '\n'.join(result)
open('app.py', 'w', encoding='utf-8').write(content)
print('Done')
