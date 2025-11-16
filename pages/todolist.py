from nicegui import ui


@ui.page("/todolist", title="待办事项")
async def page_todolist():
    ui.button("返回", on_click=lambda: ui.navigate.to("/"))
