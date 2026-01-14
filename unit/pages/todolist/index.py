from nicegui import ui, app
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

VUE_COMPATIBLE_ENV = Environment(
    loader=FileSystemLoader("templates"),
    variable_start_string="[[",
    variable_end_string="]]"
)


@app.get("/todolist/index", response_class=HTMLResponse)
async def todolist_index(request: Request):
    return VUE_COMPATIBLE_ENV.get_template("todolist_index.html").render({"jinja2": "jinja2-test"})


@ui.page("/todolist", title="待办事项")
async def page_todolist():
    ui.button("返回", on_click=lambda: ui.navigate.to("/"))
