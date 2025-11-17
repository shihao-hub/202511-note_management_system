-- 要求 config 中的键为 string 类型，值类型要与 json 的类型对应
config = {}

config.title = "笔记管理系统"
config.host = "localhost"
config.version = "v1.1.2.1"
config.save_note_cooldown = 1
config.attachment_upload_text = "共 {0} 个附件，粘贴上传或拖拽上传" -- {0} 为 python format 的占位符
config.intruction_content = [[
快捷键：
    ctrl+s: 编辑笔记和保存笔记页面用于快捷保存
    ctrl+v: 笔记正文输入框用于粘贴文本和上传文件
    ctrl+o: 搜索编辑按钮并点击
    end: 笔记正文自动滚到最下面
    ecs: 搜索退回按钮并点击
笔记详情：
    markdown 渲染模式下，点击链接，将自动打开默认浏览器
    自动增长选项指的是笔记正文侧面是否存在滚轮
编辑笔记：
    导出为文件：导出位置是 exe 所在目录下的 exports 目录
其他：
    附件列表现在支持编辑附件名称（文件后缀自动保留）
]]
config.export_dir = "exports" -- 文件导出目录（相对目录，根目录为 .exe 所在目录）
config.prefix_import_values = { -- 前缀导入插入项配置
    "【抖音】",
    "【知乎】",
    "【待办】",
    "【Pixso AI】",
}