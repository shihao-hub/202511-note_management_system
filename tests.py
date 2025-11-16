import webbrowser
from nicegui import ui, app

# 定义一个可被 JS 调用的函数
@app.get('/open-external-link')
def open_external_link(url: str):
    webbrowser.open(url)
    return {'status': 'ok'}

# 注入 JS 代码
js_code = '''
document.addEventListener('click', function(e) {
    let el = e.target;
    while (el && el.tagName !== 'A') {
        el = el.parentElement;
    }
    if (el && el.href) {
        e.preventDefault();
        fetch('/open-external-link?url=' + encodeURIComponent(el.href))
            .catch(err => console.error('Failed to open link:', err));
    }
});
'''

# 在页面加载时注入
ui.add_head_html(f'<script>{js_code}</script>')

# 示例 markdown
ui.markdown('''
这是一个测试：[点击这里去 Google](https://www.google.com)
还有 [GitHub](https://github.com)
''')

ui.run()