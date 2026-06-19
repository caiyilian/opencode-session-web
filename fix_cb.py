content = open('static/js/app.js', 'r', encoding='utf-8').read()

old = '''html += '<label style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:13px;cursor:pointer"><input type="checkbox" ' + checked + ' onchange="toggleBlockProvider(\\'' + p + '\\')" style="accent-color:var(--accent)"> ' + p + '</label>';'''
new = '''html += '<label class="provider-item"><input type="checkbox" class="provider-cb" ' + checked + ' onchange="toggleBlockProvider(\\'' + p + '\\')"> ' + p + '</label>';'''

assert old in content, 'pattern not found'
content = content.replace(old, new)
open('static/js/app.js', 'w', encoding='utf-8').write(content)
print('OK')
