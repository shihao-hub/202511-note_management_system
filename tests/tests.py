from nicegui import ui

html_content = '''
<div id="editor" style="height: 300px;"></div>
<script src="https://cdn.quilljs.com/1.3.6/quill.js"></script>
<link href="https://cdn.quilljs.com/1.3.6/quill.snow.css" rel="stylesheet">
<script>
  var quill = new Quill('#editor', {
    theme: 'snow'
  });
  // 可通过 window.noteContent = () => quill.root.innerHTML; 供 Python 调用
</script>
'''

ui.add_body_html(html_content)
ui.button('Get Content', on_click=lambda: ui.run_javascript('console.log(document.querySelector(".ql-editor").innerHTML);'))
ui.run()