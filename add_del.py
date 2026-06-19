content = open('static/js/app.js', 'r', encoding='utf-8').read()

old = '''      html += `<div class="session-item ${active}" onclick="${compareMode ? 'toggleCompareSelect(\'' + s.id + '\', this.querySelector(\'.compare-cb\'))' : 'openSession(\'' + s.id + '\')'}">
        ${cb}<div class="title">${escHtml(s.title)}</div>
        <div class="meta">'''

new = '''      html += `<div class="session-item ${active}" onclick="${compareMode ? 'toggleCompareSelect(\'' + s.id + '\', this.querySelector(\'.compare-cb\'))' : 'openSession(\'' + s.id + '\')'}">
        ${cb}<div class="title">${escHtml(s.title)}</div>
        <span class="del-session" onclick="event.stopPropagation();deleteSession('${s.id}')" title="\\u5220\\u9664\\u4f1a\\u8bdd">&#10005;</span>
        <div class="meta">'''

assert old in content, 'pattern not found'
content = content.replace(old, new)
open('static/js/app.js', 'w', encoding='utf-8').write(content)
print('OK')
