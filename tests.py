from nicegui import ui

# 正确包含换行符的字符串
text = """快捷键：
ctrl+s: 保存
ctrl+v: 粘贴"""

# 方式1：直接赋值
ta1 = ui.textarea('测试1', value=text).props('rows=5').classes('w-full')

# 方式2：动态设置
ta2 = ui.textarea('测试2').props('rows=5').classes('w-full')
ta2.set_value("第一行\n第二行\n第三行")

# 按钮验证内容
def show_repr():
    print("TA1 内容 repr:", repr(ta1.value))
    print("TA2 内容 repr:", repr(ta2.value))

ui.button('打印内容', on_click=show_repr)

ui.run()