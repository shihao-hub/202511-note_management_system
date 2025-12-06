from . import (
    main,
    get_note,
    add_or_edit_note,
    index
)

# [note][2025-11-13] 初版完成后，通义非深度思考模式：
#                    `使用 tailwindcss、quasar 美化下面的 nicegui 代码，要求只修改修改样式`
#                    `我希望在 不改动逻辑结构 的前提下，仅通过 Tailwind CSS 和 Quasar 风格来美化这段 NiceGUI 代码`
# [note] 重点笔记，可以非深度思考模式问 ai 一些 tailwind css 元素问题，不要太复杂，很好用！
# [note] 前端在开发阶段要求可用即可，如骨架、按钮响应等，关键还是进行后端部分的开发！

# [knowledge] [Rust 的 Result 类型详解](https://lxblog.com/qianwen/share?shareId=c6059ca1-51c6-4424-876d-6e2019bfb925)

# [note] 页面拆分，我的建议是，规范情况下，一个 py 文件最好只有一个 ui.page！（哪怕两个也是有风险的）不管页面多小！
