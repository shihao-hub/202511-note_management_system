from nicegui import ui

ui.label("1112")
# with ui.row().classes("w-full justify-center py-2 mt-auto"):
with ui.scroll_area().classes("w-full p-0 "):
    # --- 对照实验
    ui.label('A' * 100).classes('w-full bg-green-500 ')


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(reload=True,port=10001)