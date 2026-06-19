with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix step_finish handlers (only send done for reason=="stop")
changes = 0
for i, line in enumerate(lines):
    if 'step_finish' in line and i+1 < len(lines) and 'tokens' in lines[i+1] and i+2 < len(lines) and 'done' in lines[i+2]:
        # Check indentation
        indent = line[:len(line) - len(line.lstrip())]
        lines[i+1] = indent + 'reason = part.get("reason", "")\n'
        lines[i+2] = indent + 'tokens = part.get("tokens", {})\n'
        # The existing yield line becomes conditional
        old_yield = lines[i+3]
        new_yield = indent + 'if reason == "stop":\n' + indent + '    ' + old_yield.lstrip()
        lines[i+3] = new_yield
        changes += 1

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print(f'Fixed {changes} occurrences')
