import os
from enum import Enum
from typing import Callable, Tuple, Sequence, List, Dict, TypedDict, Literal

from loguru import logger
from nicegui import ui, app


# [note] 数据流动方向 components.py -> views.py（谨防循环依赖问题）


class NoteInputElement:
    # todo: 构建一个输入笔记的元素，要求足够复杂，至少一点：实现 mermaid 渲染，不知道这种咋实现...
    #       尤其笔记输入区嵌很多元素，这是咋做到的？
    #       如果解决这个问题，可能就好一点了。
    def __init__(self):
        pass



class LoadingOverlay:
    """遮盖组件"""

    def __init__(self, default_message: str = "处理中..."):
        # 创建遮罩层：纯毛玻璃效果、无背景色、默认隐藏
        self.overlay = ui.element("div").classes(
            "fixed inset-0 flex items-center justify-center z-50"
        ).style("backdrop-filter: blur(2px); display: none;")
        with self.overlay:
            with ui.card().classes("p-6 shadow-lg rounded-lg bg-white flex flex-col items-center"):
                ui.spinner(size="lg")
                self.label = ui.label(default_message).classes("mt-4 text-gray-700")

    def show(self, message: str = None):
        """显示加载遮罩，可选更新提示文字"""
        if message is not None:
            self.label.set_text(message)
        self.overlay.style("display: flex;")

    def hide(self):
        """隐藏加载遮罩"""
        self.overlay.style("display: none;")


# todo: 进一步完善
def is_native_local() -> bool:
    # 判断是否运行在本地 native 模式（即桌面应用）
    # 通常 native 模式会通过特定方式启动（如 pyinstaller 打包 + 内嵌浏览器）
    # 这里简单判断：如果标准输入输出存在且不是在 Jupyter/Colab 环境，且 host 是 localhost
    # 更严谨的方式可通过环境变量或启动参数传递
    return (
            "localhost" in str(app.config.host) or
            "127.0.0.1" in str(app.config.host)
    ) and not any(key in os.environ for key in ["COLAB", "JUPYTER"])


class NativeFileDialog(ui.dialog):
    """
    本地 native 模式下的文件保存对话框（使用 tkinter）
    非 native 模式下不显示或提示不支持
    """

    def __init__(
            self,
            *,
            value: bool = False,
            title: str = "保存文件",
            default_filename: str = "document.txt",
            filetypes: Sequence[Tuple[str, str]] = (("文本文件", "*.txt"), ("所有文件", "*.*")),
            on_save: Callable[[str, str], None] | None = None,  # (filename, content) -> None
            content_getter: Callable[[], str] | None = None,
            title_getter: Callable[[], str] | None = None,
    ):
        super().__init__(value=value)
        self.title_str = title
        self.default_filename = default_filename
        self.filetypes = filetypes
        self.on_save = on_save
        self.content_getter = content_getter or (lambda: "")
        self.title_getter = title_getter or (lambda: "")

    def open(self) -> None:
        # if not is_native_local():
        #     ui.notify("仅在本地桌面模式下支持保存文件", type="warning")
        #     return

        # 使用 tkinter 打开系统保存对话框
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            filepath = filedialog.asksaveasfilename(
                title=self.title_str,
                initialfile=self.default_filename,
                defaultextension=".txt",
                filetypes=self.filetypes,
            )
            root.destroy()

            if filepath:
                full_content = f"{self.title_getter()}\n\n{self.content_getter()}"
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(full_content)

                filename = os.path.basename(filepath)
                ui.notify(f"已保存到：{filename}", type="positive")

                if self.on_save:
                    self.on_save(filepath, full_content)

        except Exception as e:
            logger.error(e)
            ui.notify(f"保存失败：{e}", type="negative")


# todo: 封装一些 dialog，如：
#       使用介绍（可翻页！）、
#       二次确认弹窗、
#       配置页弹窗、
#       ai 调用页弹窗、
#       文件上传弹窗、
#       查看附件弹窗（查看列表类弹窗）、
#       ai 问答页弹窗（找完全免费的 ai）、
#       图片预览弹窗、
#       markdown 渲染弹窗 ...


def show_config_dialog():
    """展示配置项/首选项弹窗"""
    with ui.dialog(value=True), ui.card().classes("w-96 p-4"):
        pass

# [2025-11-18] 先把之前写的临时弹窗抽取到这边，暂不考虑优化（封装成类之后慢慢考虑优化）
class ConfigInfoTypeDict(TypedDict):
    key: str
    value: str | int | float | List | bool
    type: Literal["str", "int", "float", "List", "bool", "Enum"]
    human_name: str
    options: List | None  # 供 Enum 使用


class ConfigDialog(ui.dialog):
    """ConfigDialog - 配置弹窗 - 很难有普遍性，但是可以尝试一下（很麻烦，不如手动写，两边映射一下）"""

    def __init__(
            self,
            *,
            value: bool = False,
            configs: List[ConfigInfoTypeDict],
            extra_keys: List | None = None
    ):
        """

        :param value: ui.dialog's
        :param configs:
        :param extra_keys: 排除在外的键
        """
        super().__init__(value=value)

        with self, ui.card().classes("w-96 p-4"):
            for config in configs:
                if config["type"] == "str":
                    pass
                elif config["type"] == "int":
                    ui.number(label=config["human_name"], value=config["value"], min=1, max=100, step=1) \
                        .classes("w-full")
                elif config["type"] == "float":
                    pass
                elif config["type"] == "List":
                    pass
                elif config["type"] == "bool":
                    pass
                elif config["type"] == "Enum":
                    ui.select(options=config["options"], value=config["value"], label=config["human_name"]) \
                        .classes("w-full")
                else:
                    raise TypeError("config type must be str or int, float, List, bool, Enum")


class AboutDialog(ui.dialog):
    """AboutDialog - 普遍性一般"""

    def __init__(
            self,
            *,
            value: bool = False,
            app_name: str,
            version: str,
            description: str,
            author: str,
            license_text: str = "MIT License",
            website: str | None = None,
    ) -> None:
        """AboutDialog

        创建软件的关于 dialog

        :param value: ui.dialog 的 value
        :param app_name: 软件名
        :param version: 软件版本号
        :param description: 软件描述
        :param author: 软件作者
        :param license_text: 证书信息
        :param website: 软件网站
        """
        super().__init__(value=value)

        title = "关于"
        icon = "info"

        with self, ui.card().classes("p-6 min-w-[350px] max-w-[500px]"):
            # --- 标题栏
            with ui.row().classes("w-full items-center mb-2"):  # mb-4(margin bottom)
                ui.icon(icon, size="24px").classes("mr-2 text-primary")
                ui.label(title).classes("text-h6 font-bold")

            # --- 内容区
            with ui.row().classes("w-full items-center"):
                ui.label(app_name).classes("text-h5 font-bold")
                ui.space()
                ui.label(f"版本: {version}").classes("text-caption text-grey-7 dark:text-grey-4 translate-y-[0.15em]")

            ui.separator().classes("my-3")

            ui.label(description).classes("mt-2 leading-tight")

            # --- 元信息（作者、网站等）
            with ui.column().classes("mt-4 gap-1 text-sm"):
                if author:
                    ui.label(f"作者: {author}")
                if website:
                    with ui.link(website, website).classes("text-primary hover:underline") as link:
                        link.props('target="_blank"')
                if license_text:
                    ui.label(f"许可证: {license_text}")

            # --- 关闭按钮
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("关闭", on_click=self.close).props('outline padding="sm"')


class TextDialog(ui.dialog):
    """TextDialog - 显示只读文本内容的对话框 - 普遍性极其一般"""

    def __init__(self, *, content: str, title: str = "文本框", value: bool = False) -> None:
        """

        :param content: 文本框内容
        :param title:  文本框标题
        :param value: 来自 ui.dialog
        """
        super().__init__(value=value)

        with self, ui.card().classes("p-6 min-w-[350px] max-w-[500px]"):
            with ui.row().classes("w-full items-center mb-2"):  # mb-4(margin bottom)
                ui.icon("mdi-card-text-outline", size="24px").classes("mr-2 text-primary")
                ui.label(title).classes("text-h6 font-bold")

            # [note] textarea 似乎无法轻易控制宽高
            # ui.textarea(value=content).classes("w-full mb-6").props("readonly outlined ")

            # ui.markdown(content).classes("w-full")

            # [step] ai: [pre-wrap pre-line](https://lxblog.com/qianwen/share?shareId=520cd53e-04aa-427e-a97b-f67449f8a7f5)
            ui.label(content).classes("w-full mb-6 border-2 border-dashed rounded-sm p-4").style(
                "white-space: pre-wrap")

            # todo: 来多个 label，都有边框，很有意思
