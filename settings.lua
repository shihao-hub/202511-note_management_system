-- 要求 config 中的键为 string 类型，值类型要与 json 的类型对应
config = {}

config.title = "笔记管理系统"
config.host = "localhost"
config.version = "v1.1.2"
config.save_note_cooldown = 1
config.attachment_upload_text = "共 {0} 个附件，粘贴上传或拖拽上传" -- {0} 为 python format 的占位符
config.intruction_content = [[
快捷键：
    ctrl+s: 编辑笔记和保存笔记页面用于快捷保存
    ctrl+v: 笔记正文输入框用于粘贴文本和上传文件
笔记详情：
    markdown 渲染模式下，点击链接，将自动打开默认浏览器
]]
config.export_dir = "exports" -- 文件导出目录（相对目录，根目录为 .exe 所在目录）