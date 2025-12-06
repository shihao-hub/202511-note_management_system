import nicegui as q
from nicegui import ui
import datetime
from typing import List, Dict

# 模拟笔记数据
notes: List[Dict] = [
    {
        "id": 1,
        "title": "项目会议记录",
        "summary": "讨论了项目进展和下一步计划，需要准备下周的演示材料...",
        "date": "2023-06-15",
        "attachments": 3,
        "content": "2023年6月15日 项目进度会议\n\n与会人员：\n- 张经理\n- 李工程师\n- 王设计师\n- 刘测试\n\n会议内容：\n1. 项目进度回顾\n  - 前端界面开发完成80%"
    },
    {
        "id": 2,
        "title": "学习计划",
        "summary": "学习React和Node.js的计划安排，包括书籍、教程和实践项目...",
        "date": "2023-06-10",
        "attachments": 1,
        "content": "学习 React 和 Node.js 的详细计划..."
    },
    {
        "id": 3,
        "title": "旅行清单",
        "summary": "夏季旅行需要准备的物品清单，包括衣物、证件和其他必需品...",
        "date": "2023-05-28",
        "attachments": 2,
        "content": "行李清单：护照、充电器、防晒霜..."
    }
]

# 当前选中的笔记
selected_note = None


# 页面布局
@ui.page("/", title="笔记管理系统")
def main():
    with ui.row().classes("w-full h-screen bg-gray-50"):
        # 左侧栏
        with ui.column().classes("w-80 bg-white border-r border-gray-200 p-4"):
            ui.label("📋 笔记管理系统").classes("text-xl font-bold mb-4")
            search_bar = ui.input(placeholder="搜索笔记...").classes("w-full mb-6")

            # 列表容器
            with ui.card().classes("w-full"):
                for note in notes:
                    with ui.card().classes("border-b hover:bg-gray-100 cursor-pointer transition-colors") as card:
                        with ui.row().classes("items-start"):
                            ui.label(note["title"]).classes("font-semibold text-lg flex-1")
                            ui.label(str(note["attachments"])).classes("text-sm text-gray-500 ml-auto")
                        ui.label(note["summary"]).classes("text-sm text-gray-600 mt-1")
                        with ui.row().classes("text-xs text-gray-500 mt-1"):
                            ui.icon("calendar_today").classes("mr-1")
                            ui.label(note["date"])
                            ui.icon("attach_file").classes("ml-2 mr-1")
                            ui.label(f"{note['attachments']}个附件")
                        # card.clicked.connect(lambda _, n=note: load_note(n))

        # 右侧主内容区
        with ui.column().classes("flex-1 p-6 overflow-y-auto"):
            ui.label("编辑笔记").classes("text-xl font-bold mb-4")

            # 操作按钮
            with ui.row().classes("mb-6 justify-end"):
                ui.button("💾 保存", color="positive").classes("mr-2")
                ui.button("🗑️ 删除", color="negative").classes("mr-2")
                ui.button("📎 查看附件", color="primary")

            # 标题输入
            with ui.row().classes("items-center mb-4"):
                ui.label("标题").classes("font-medium w-20")
                title_input = ui.input(value="项目会议记录").classes("flex-1")
                ui.button("📋 复制", icon="content_copy").on_click(lambda: ui.copy(title_input.value))

            # 内容区域
            with ui.row().classes("items-center mb-4"):
                ui.label("内容").classes("font-medium w-20")
                content_input = ui.textarea(
                    value="2023年6月15日 项目进度会议\n\n与会人员：\n- 张经理\n- 李工程师\n- 王设计师\n- 刘测试\n\n会议内容：\n1. 项目进度回顾\n  - 前端界面开发完成80%",
                    placeholder="请输入笔记内容...",
                ).classes("flex-1 min-h-40")
                ui.button("📋 复制", icon="content_copy").on_click(lambda: ui.copy(content_input.value))

            # 提示信息
            ui.label("💡 提示：您可以粘贴图片到内容区域，系统将自动上传作为附件").classes(
                "text-sm text-gray-600 bg-blue-50 p-3 rounded-md my-4")

            # 附件区域
            with ui.row().classes("items-center justify-between mb-4"):
                ui.label("附件 (3)").classes("font-medium")
                ui.button("📎 管理附件", color="gray").classes("px-3 py-1")

            # 图片附件预览
            with ui.row().classes("gap-4"):
                for i in range(3):
                    ui.image(f"https://picsum.photos/seed/{i}/300/200").classes("w-60 h-32 object-cover rounded")

            # 添加图片上传功能（可选）
            with ui.row().classes("mt-4"):
                ui.upload(label="上传附件").on_upload(lambda e: print(e.content))


def load_note(note):
    global selected_note
    selected_note = note
    # 更新右侧内容
    ui.run_async(update_editor(note))


async def update_editor(note):
    # 这里可以更新输入框的内容
    # 注意：由于 NiceGUI 的限制，可能需要重新构建组件或使用 `ui.refresh()`，这里简化处理
    pass


# 启动应用
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(reload=True)
