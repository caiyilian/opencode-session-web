content = open('static/js/app.js', 'r', encoding='utf-8').read()

old = "  let html = '<div class=\"modal-overlay\" id=\"providerModal\" onclick=\"if(event.target===this)closeProviderManager()\" style=\"display:flex\"><div class=\"modal\"><h2>&#128220; \u7ba1\u7406\u63d0\u4f9b\u8005</h2><p style=\"font-size:12px;color:var(--text-dim);margin-bottom:12px\">\u52fe\u9009\u7684\u63d0\u4f9b\u8005\u5c06\u88ab\u9690\u85cf</p>';"

new = "  let html = '<div class=\"modal-overlay\" id=\"providerModal\" onclick=\"if(event.target===this)closeProviderManager()\" style=\"display:flex\"><div class=\"modal\"><h2>\u7ba1\u7406\u63d0\u4f9b\u8005</h2><p style=\"font-size:12px;color:var(--text-dim);margin-bottom:12px\">\u52fe\u9009\u7684\u63d0\u4f9b\u8005\u5c06\u88ab\u9690\u85cf</p><div class=\"provider-list\">';"

if old in content:
    content = content.replace(old, new)
    print('OK: updated header')
else:
    print('header pattern not found')

old2 = "    html += '<label style=\"display:flex;align-items:center;gap:6px;padding:3px 0;font-size:13px;cursor:pointer\"><input type=\"checkbox\" ' + checked + ' onchange=\"toggleBlockProvider(\\'" + p + "\\')\" style=\"accent-color:var(--accent)\"> ' + p + '</label>';"
new2 = "    html += '<label class=\"provider-item\"><input type=\"checkbox\" ' + checked + ' onchange=\"toggleBlockProvider(\\'" + p + "\\')\"> <span>' + p + '</span></label>';"

if old2 in content:
    content = content.replace(old2, new2)
    print('OK: updated label')
else:
    print('label pattern not found')

old3 = "  html += '<div class=\"modal-actions\" style=\"margin-top:12px\"><button class=\"btn-primary\" onclick=\"closeProviderManager()\">\u786e\u5b9a</button></div></div></div>';"
new3 = "  html += '</div><div class=\"modal-actions\"><button class=\"btn-cancel\" onclick=\"closeProviderManager()\">\u5173\u95ed</button></div></div></div>';"

if old3 in content:
    content = content.replace(old3, new3)
    print('OK: updated actions')
else:
    print('actions pattern not found')

open('static/js/app.js', 'w', encoding='utf-8').write(content)
