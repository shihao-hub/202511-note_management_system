from nicegui import ui,native

# https://lxblog.com/qianwen/share?shareId=527780c2-1236-46a7-a7fc-71a8c894313b
# - 避免下拉菜单被父容器裁剪（常见于 overflow: hidden 的卡片中）。
# - 全屏加载遮罩


# todo: 太妙了，下面的代码可以实现遮罩效果！nicegui 更新了好多东西呀！
ui.label("12")
ui.spinner(size='xl')
with ui.teleport('body'):

    with ui.element('div').classes('fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-30'):
        ui.spinner(size='xl')

ui.run(port=9999)
