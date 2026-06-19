content = open('app.py', 'r', encoding='utf-8').read()

# Fix 1: run_opencode_stream - only send done for final step_finish
old1 = """                elif event_type == "step_finish":
                    tokens = part.get("tokens", {})
                    yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                elif event_type and event_type not in ("step_start", "step_finish"):"""

new1 = """                elif event_type == "step_finish":
                    reason = part.get("reason", "")
                    tokens = part.get("tokens", {})
                    if reason == "stop":
                        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                elif event_type and event_type not in ("step_start", "step_finish"):"""

# Fix 2: new session endpoint
old2 = """                    elif ev_type == "step_finish":
                        tokens = part.get("tokens", {})
                        yield f"event: done\ndata: {json.dumps({'session_id': new_session_id or '', 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                    elif ev_type and ev_type not in ("step_start", "step_finish"):"""

new2 = """                    elif ev_type == "step_finish":
                        reason = part.get("reason", "")
                        tokens = part.get("tokens", {})
                        if reason == "stop":
                            yield f"event: done\ndata: {json.dumps({'session_id': new_session_id or '', 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                    elif ev_type and ev_type not in ("step_start", "step_finish"):"""

# Fix 3: fork endpoint
old3 = """                    elif ev_type == "step_finish":
                        tokens = part.get("tokens", {})
                        yield f"event: done\ndata: {json.dumps({'session_id': new_session_id or '', 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                except json.JSONDecodeError:"""

new3 = """                    elif ev_type == "step_finish":
                        reason = part.get("reason", "")
                        tokens = part.get("tokens", {})
                        if reason == "stop":
                            yield f"event: done\ndata: {json.dumps({'session_id': new_session_id or '', 'tokens': tokens, 'cost': part.get('cost', 0)})}\n\n"
                except json.JSONDecodeError:"""

changes = [(old1, new1, 'run_opencode_stream'), (old2, new2, 'new session'), (old3, new3, 'fork')]
for old, new, name in changes:
    if old in content:
        content = content.replace(old, new)
        print(f'OK: {name}')
    else:
        print(f'FAIL: {name} - pattern not found')

open('app.py', 'w', encoding='utf-8').write(content)
if all(old in content for old, _, _ in changes):
    print('All done')
