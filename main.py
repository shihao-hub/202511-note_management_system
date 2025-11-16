from addict import Dict as Addict
from nicegui import ui, app, native
from loguru import logger
from dotenv import load_dotenv

# region - template

# python-doenv 设置环境变量
load_dotenv(".env")

# pyinstaller（注意 sqlalchemy 搭配 alembic 的主动迁移命令，导致打包后出错，需要考虑如何解决，虽然复制一个无数据 db 即可解决）
try:
    import sys

    import addict
    import aiosqlite
    import loguru
    import alembic
    import sqlalchemy
    import sqlalchemy_utc
    import fastapi
    import jinja2

    is_packed = getattr(sys, "frozen", False)
except ImportError as exception:
    logger.error(exception)
    raise exception

# 移除默认的日志处理器
logger.remove()
# 控制台输出 - 彩色，简洁格式
logger.add(
    sys.stdout,
    format="<c>{time:YYYY-MM-DD HH:mm:ss.SSS}</c> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}",
    level="DEBUG",
    colorize=True,
    backtrace=True,
    diagnose=True
)
# 详细日志文件 - 包含所有级别
logger.add(
    "debug.log",
    format="<c>{time:YYYY-MM-DD HH:mm:ss.SSS}</c> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    backtrace=True,
    diagnose=True
)

# endregion

# 在 main.py 中项目的包建议放在最下面执行，这样最稳当（比如 .env 导入，nicegui 环境变量设置等）
from api import fastapi_app
from models import init_db, auto_upgrade_db
from utils import cleanup
from services import UserConfigService
from settings import dynamic_settings
from pages import register_pages

register_pages()

# [knowledge] 在创建 NiceGUI 应用时保留 FastAPI 的文档路由（不要让 nicegui 接管根路径）
app.mount("/api", fastapi_app)
app.add_static_files("/static", "static")
app.add_static_files("/fonts", "fonts")


@app.on_startup
async def startup_event():
    logger.debug("app - startup")
    await init_db()
    await auto_upgrade_db()
    async with UserConfigService() as service:
        await service.init_user_config()
    await cleanup.start()


@app.on_shutdown
async def shutdown_event():
    logger.debug("app - shutdown")
    await cleanup.stop()


if __name__ in {"__main__", "__mp_main__"}:

    props = Addict()
    props.title = dynamic_settings.title
    props.host = dynamic_settings.host

    # todo: 添加 static 路由和文件，解决 cdn 需要挂 vpn 的问题

    if not is_packed:
        import os
        import argparse

        # NiceGUI 使用 webview 或内置 CEF 启动原生窗口，可通过下列环境变量开启底层日志
        # os.environ["PYWEBVIEW_LOG"] = "debug"
        # os.environ["CEFPYTHON_LOG_SEVERITY"] = "info"

        # [pyinstaller 之程序立即退出的根本原因](https://lxblog.com/qianwen/share?shareId=a439527a-cf57-4902-9cca-0cc1172191d3)
        parser = argparse.ArgumentParser()
        parser.add_argument("--native", action="store_true", default=False)
        args = parser.parse_args()

        props.native = args.native
        props.window_size = None
        if props.native:
            props.window_size = (1200, 900)

        ui.run(
            title=props.title,
            host=props.host,
            port=8888,
            native=props.native,
            window_size=props.window_size,
            uvicorn_reload_includes="*.py, *.js, *.lua"
        )
    else:
        logger.debug("nicegui-pack application startup!")
        port = native.find_open_port(start_port=12000, end_port=65535)
        logger.debug("启动端口：{}", port)
        ui.run(
            title=props.title,
            host=props.host,
            port=port,
            native=True,
            window_size=(1200, 900),
            fullscreen=False,
            reload=False
        )
