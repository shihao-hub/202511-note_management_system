import os
import shutil
import argparse
from pathlib import Path

from loguru import logger

# 将根目录下的指定目录和文件提取到当前目录的 package 目录下，如果 package 目录存在则先删除

parse = argparse.ArgumentParser()
parse.add_argument("--pystand", action="store_true")
args = parse.parse_args()

CWD = Path(__file__).resolve().parent  # Path.cwd() | 注意，Path.cwd() 有问题，还是要获取入口文件所在目录
ROOT_DIR = CWD.parent
RESULT_DIR = CWD / ("package" if not args.pystand else "script")
TRAGET_FILES = [
    {"type": "dir", "name": "bin"},
    {"type": "dir", "name": "fonts"},
    {"type": "dir", "name": "locales"},
    {"type": "dir", "name": "migrations"},
    {"type": "dir", "name": "static"},
    {"type": "dir", "name": "templates"},

    {"type": "file", "name": ".env"},
    {"type": "file", "name": "alembic.ini"},
    {"type": "file", "name": "settings.lua"},
]

# todo: 源代码最好是 src 目录（PyStand 打包是直接源代码打包）
if args.pystand:
    TRAGET_FILES.extend([
        {"type": "dir", "name": "pages"},
        {"type": "dir", "name": "scripts"},
        {"type": "dir", "name": "utils"},

        {"type": "file", "name": "api.py"},
        {"type": "file", "name": "components.py"},
        {"type": "file", "name": "documents.py"},
        {"type": "file", "name": "filters.py"},
        {"type": "file", "name": "main.py"},
        {"type": "file", "name": "mediator.py"},
        {"type": "file", "name": "middlewares.py"},
        {"type": "file", "name": "models.py"},
        {"type": "file", "name": "schemas.py"},
        {"type": "file", "name": "services.py"},
        {"type": "file", "name": "settings.py"},
        {"type": "file", "name": "views.py"},
    ])

if RESULT_DIR.exists():
    shutil.rmtree(RESULT_DIR)
    logger.debug("Removed old result directory: {}", RESULT_DIR)

RESULT_DIR.mkdir()

# [2025-11-17] 代码写的有点丑陋啊，而且文件操作感觉好危险啊，非常危险！！！

for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
    logger.debug(f"dirnames: {dirnames}")
    logger.debug(f"filenames: {filenames}")
    for filename in filenames:
        for fileinfo in TRAGET_FILES:
            if fileinfo["type"] == "file" and filename == fileinfo["name"]:
                logger.debug("filename: {}", filename)
                shutil.copy(os.path.join(dirpath, filename), RESULT_DIR)
    for dirname in dirnames:
        for fileinfo in TRAGET_FILES:
            if fileinfo["type"] == "dir" and dirname == fileinfo["name"]:
                logger.debug("dirname: {}", dirname)
                shutil.copytree(os.path.join(dirpath, dirname), RESULT_DIR / dirname)
    break
