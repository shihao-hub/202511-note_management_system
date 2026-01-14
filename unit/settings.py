import sys
import tomllib
from pathlib import Path
from typing import List

import portpicker
from pydantic_settings import BaseSettings
from jinja2 import Environment, FileSystemLoader

ENV = Environment(loader=FileSystemLoader("./templates"))  # 设置 jinja2 模板目录

DEBUG = not (hasattr(sys, "PYWEBVIEW") or hasattr(sys, "frozen"))
RELOAD = DEBUG  # 开发阶段开启热重载，生产环境关闭热重载

PORT = 8889 if DEBUG else portpicker.pick_unused_port()
WINDOW_SIZE = (1200, 900)

# [pydantic-settings 如何使用](https://lxblog.com/share?shareId=ec78187b-f927-4c5e-9296-7cae4b461a6d)
class DynamicSettings(BaseSettings):
    save_note_cooldown: int
    attachment_upload_text: str  # [note] python 可以这样使用 format："{0}".format(0)
    intruction_content: str
    title: str
    host: str
    version: str
    export_dir: str = "exports"
    prefix_import_values: List[str]

    @classmethod
    def from_toml(cls, path: str | Path = "settings.toml") -> "DynamicSettings":
        """手动加载 TOML + cls(**data)，强烈推荐，简单、可控、易测试"""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data)


dynamic_settings = DynamicSettings.from_toml()
