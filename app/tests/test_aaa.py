from  nicegui import ui

# 一直显示
ui.label("Always visible")

# 预期：小于 sm 隐藏，大于 sm 显示。结果：永远隐藏
ui.label("Hidden on small screens").classes("hidden sm:inline-block")

# **只有这个是正常的**，预期：小于 sm 显示，大于 sm 隐藏
ui.label("Visible on small screens").classes("inline sm:hidden")

# 预期：小于 sm 隐藏，大于 sm 显示。结果：永远隐藏
ui.label("Test with inline-block").classes("hidden sm:inline-block")

# 预期：小于 sm 隐藏，大于 sm 显示。结果：永远隐藏
ui.label("Check me").classes("hidden sm:inline-block")

# 无效，block 改为 inline 生效
ui.button("Responsive Button").classes("block sm:hidden")

ui.run()