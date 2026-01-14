"""
涉及 tkinter，由于 embed python 不包含 tkinter，所以建议单独处理 tkinter 相关的代码
"""
import contextlib

from log import logger


@contextlib.contextmanager
def create_tk_root():
    import tkinter as tk
    # tkinter 可以在 nicegui 现有事件循环中执行，只不过会阻塞，但是对于文件弹窗这些场景，是适用的
    # tkinter 在线程中启动存在一些问题，能用但是很奇怪
    # tkinter 我的理解应该是通过 ctypes 封装了操作系统的 UI API 接口，比较简陋

    # [note] 必须在有 Tk 实例的线程中运行
    root = tk.Tk()  # 创建一个 Tk 根窗口
    logger.debug("[create_tk_root] root_ad: {}", id(root))
    root.withdraw()  # 隐藏主窗口
    root.wm_attributes("-topmost", True)  # 对话框置顶
    yield root
    root.destroy()  # 销毁 Tk 实例，释放资源


def import_filedialog():
    from tkinter import filedialog
    return filedialog


def import_messagebox():
    from tkinter import messagebox
    return messagebox
