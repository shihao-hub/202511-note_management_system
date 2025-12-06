from nicegui import ui

# 假设这是你的图片路径
image_path = '../docs/images/page_add_note.png'

with ui.card().classes("w-1/2"):
    with ui.grid().classes("w-full").style('grid-template-columns: 4fr 1fr'):
        # 左侧部分
        with ui.column().classes('p-4 border-2 border-red-500'):  # 使用space-y-2为垂直间距
            # 第一行：标题
            ui.label('这里是标题').classes('text-black font-bold')
            # 第二行：副标题
            ui.label('这里是灰色小的副标题').classes('text-gray-500 text-sm')
            # 第三行：下拉按钮
            with ui.dropdown_button('Open me!', auto_close=True).classes('mt-2'):
                ui.item('Item 1', on_click=lambda: ui.notify('You clicked item 1'))
                ui.item('Item 2', on_click=lambda: ui.notify('You clicked item 2'))

        # 右侧部分
        with ui.column().classes('p-4 items-center justify-center border-2 border-red-500'):  # 让内容居中
            ui.image(image_path).classes('rounded object-contain')  # 自动调整高度保持宽高比

ui.run()
