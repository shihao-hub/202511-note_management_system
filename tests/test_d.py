from nicegui import ui
from typing import Any, Dict, List, Union

# 示例配置（包含 number, string, list, dict）
config: Dict[str, Any] = {
    "app_name": "MyApp",  # string
    "version": 1.5,  # number
    "debug_mode": True,  # boolean（也支持）
    "tags": ["note", "todo", "idea"],  # list of string
    "limits": [10, 20, 30],  # list of number
    "database": {  # dict
        "host": "localhost",
        "port": 5432,
        "ssl": False
    },
    "ui_options": {  # nested dict
        "theme": "dark",
        "font_size": 14,
        "plugins": ["markdown", "code"]
    }
}


def render_value(parent_key: str, value: Any, container: ui.element):
    """递归渲染值（支持 dict/list/基本类型）"""
    if isinstance(value, dict):
        with ui.card().classes('w-full p-2 bg-gray-50'):
            for k, v in value.items():
                full_key = f"{parent_key}.{k}" if parent_key else k
                with ui.row().classes('w-full items-center gap-2 mb-1'):
                    ui.label(k).classes('font-mono text-sm w-24')
                    render_value(full_key, v, container)
    elif isinstance(value, list):
        with ui.card().classes('w-full p-2 bg-blue-50'):
            list_container = ui.column().classes('w-full')
            for i, item in enumerate(value):
                with ui.row().classes('items-center gap-2 mb-1'):
                    ui.label(f"[{i}]").classes('font-mono text-sm w-8')
                    render_value(f"{parent_key}[{i}]", item, list_container)

            # 添加新项按钮
            def add_item():
                new_val = "" if all(isinstance(x, str) for x in value) else 0
                value.append(new_val)
                list_container.clear()
                render_list_items(parent_key, value, list_container)

            ui.button('➕ 添加', on_click=add_item).props('dense').classes('text-xs')
    elif isinstance(value, bool):
        switch = ui.switch('', value=value)

        def on_change(e):
            _set_nested_value(config, parent_key, e.value)

        switch.on('update:model-value', on_change)
    elif isinstance(value, (int, float)):
        num = ui.number(value=value, format='%.2f' if isinstance(value, float) else '%d')

        def on_change(e):
            val = float(e.value) if isinstance(value, float) else int(e.value or 0)
            _set_nested_value(config, parent_key, val)

        num.on('update:model-value', lambda e: on_change(e))
    else:  # string
        inp = ui.input(value=str(value) if value is not None else '')

        def on_change(e):
            _set_nested_value(config, parent_key, e.value)

        inp.on('update:model-value', lambda e: on_change(e))


def render_list_items(parent_key: str, lst: List, container: ui.element):
    """专门用于重新渲染列表（配合“添加”按钮）"""
    container.clear()
    for i, item in enumerate(lst):
        with container:
            with ui.row().classes('items-center gap-2 mb-1'):
                ui.label(f"[{i}]").classes('font-mono text-sm w-8')
                render_value(f"{parent_key}[{i}]", item, container)


def _get_nested_value(obj: dict, key_path: str):
    """通过 a.b[0].c 这样的路径获取嵌套值"""
    keys = _parse_key_path(key_path)
    for k in keys:
        if isinstance(obj, dict):
            obj = obj[k]
        elif isinstance(obj, list):
            obj = obj[int(k)]
        else:
            break
    return obj


def _set_nested_value(obj: dict, key_path: str, value):
    """通过 a.b[0].c 这样的路径设置嵌套值"""
    keys = _parse_key_path(key_path)
    for k in keys[:-1]:
        if isinstance(obj, dict):
            obj = obj[k]
        elif isinstance(obj, list):
            obj = obj[int(k)]
    last_key = keys[-1]
    if isinstance(obj, dict):
        obj[last_key] = value
    elif isinstance(obj, list):
        obj[int(last_key)] = value


def _parse_key_path(path: str) -> List[str]:
    """解析 'a.b[0].c' -> ['a', 'b', '0', 'c']"""
    import re
    # 将 a.b[0].c 转为 a.b.0.c
    path = re.sub(r'\[(\d+)\]', r'.\1', path)
    return [part for part in path.split('.') if part]


# ===== 主界面 =====
def build_config_editor():
    ui.label('⚙️ 通用 JSON 配置编辑器').classes('text-2xl font-bold mb-4')

    with ui.card().classes('w-full max-w-2xl p-4'):
        render_value('', config, ui.element())

    ui.button('💾 保存配置', on_click=lambda: ui.notify(f'当前配置:\n{config}', type='positive')) \
        .classes('mt-4')


# 启动
build_config_editor()
ui.run()