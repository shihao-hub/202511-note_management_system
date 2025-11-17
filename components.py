import os
from typing import Callable, Tuple, Sequence

from loguru import logger
from nicegui import ui, app


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
        if not is_native_local():
            ui.notify("仅在本地桌面模式下支持保存文件", type="warning")
            return

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
