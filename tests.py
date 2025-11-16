from nicegui import ui
import sys
import os

# 判断是否为 native 模式
IS_NATIVE = True # NiceGUI 启动时会传这些参数

title = ui.input(label="标题", value="默认标题")
content = ui.textarea(label="内容", value="这里是正文内容...")

# ————————————————————————
# native 模式：使用 tkinter 弹出保存对话框
# ————————————————————————
if IS_NATIVE:
    try:
        import tkinter as tk
        from tkinter import filedialog
        has_tk = True
    except Exception:
        has_tk = False

    def save_file_native():
        if not has_tk:
            ui.notify("缺少 tkinter，无法弹出保存对话框", type='negative')
            return

        # 创建隐藏的 Tk 窗口
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)  # 置顶，避免被盖住
        file_path = filedialog.asksaveasfilename(
            title="保存文件",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        root.destroy()

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"{title.value}\n\n{content.value}")
                ui.notify(f"已保存到：{os.path.basename(file_path)}", type='positive')
            except Exception as e:
                ui.notify(f"保存失败：{e}", type='negative')

    export_handler = save_file_native

# ————————————————————————
# 浏览器模式：使用 JS Blob 下载
# ————————————————————————
else:
    import json
    async def save_file_web():
        file_name = "导出内容.txt"
        file_content = f"{title.value}\n\n{content.value}"
        safe_content = json.dumps(file_content)[1:-1]

        js_code = f'''
            const blob = new Blob(["{safe_content}"], {{ type: "text/plain;charset=utf-8" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "{file_name}";
            document.body.appendChild(a);
            a.click();
            URL.revokeObjectURL(url);
            a.remove();
        '''
        await ui.run_javascript(js_code)

    export_handler = save_file_web

# ————————————————————————
# 统一菜单项
# ————————————————————————
with ui.button(icon='menu'):
    with ui.menu() as menu:
        if IS_NATIVE:
            ui.menu_item("导出为文件", on_click=export_handler)
        else:
            ui.menu_item("导出为文件", on_click=lambda: ui.timer(0, save_file_web, once=True))

ui.run(native=IS_NATIVE)