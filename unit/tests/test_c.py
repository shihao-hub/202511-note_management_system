from nicegui import ui

# 初始配置
config = {
    "note_detail_render_type": "markdown",
    "page_size": 12,
    "note_detail_autogrow": True,
    "home_select_option": "default",
    "search_content": ""
}

def open_config_dialog():
    with ui.dialog() as dialog, ui.card().classes('w-96 p-4'):
        ui.label('配置设置').classes('text-lg font-bold mb-4')

        # 1. 渲染类型（下拉选择）
        render_type = ui.select(
            options=['markdown', 'html', 'plain'],
            label='笔记详情渲染类型',
            value=config["note_detail_render_type"]
        ).classes('w-full')

        # 2. 每页数量（数字输入）
        page_size = ui.number(
            label='每页条数',
            value=config["page_size"],
            min=1,
            max=100,
            step=1
        ).classes('w-full')

        # 3. 自动增高（开关）
        autogrow = ui.switch(
            '笔记详情自动增高',
            value=config["note_detail_autogrow"]
        )

        # 4. 首页选项（下拉）
        home_option = ui.select(
            options=['default', 'recent', 'favorite'],
            label='首页显示选项',
            value=config["home_select_option"]
        ).classes('w-full')

        # 5. 搜索内容（文本输入）
        search_content = ui.input(
            label='默认搜索内容',
            value=config["search_content"]
        ).classes('w-full')

        # 按钮组
        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('取消', on_click=dialog.close).props('outline')
            ui.button('保存', on_click=lambda: save_config(
                render_type.value,
                int(page_size.value) if page_size.value else 12,
                autogrow.value,
                home_option.value,
                search_content.value,
                dialog
            )).classes('bg-primary text-white')

        dialog.open()

def save_config(render_type, page_size, autogrow, home_option, search_content, dialog):
    # 更新全局 config
    config.update({
        "note_detail_render_type": render_type,
        "page_size": page_size,
        "note_detail_autogrow": autogrow,
        "home_select_option": home_option,
        "search_content": search_content
    })
    print("✅ 配置已保存:", config)
    dialog.close()
    # 可选：刷新页面或通知用户
    ui.notify('配置已保存！', type='positive')

# 主界面
ui.button('打开配置', on_click=open_config_dialog).classes('mt-4')

# 显示当前配置（用于调试）
ui.separator()
ui.label('当前配置：').classes('mt-4')
ui.code(str(config)).classes('bg-gray-100 p-2 rounded')

ui.run()