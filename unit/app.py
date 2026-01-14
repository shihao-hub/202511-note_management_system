import os
import traceback

from dotenv import load_dotenv

load_dotenv(".env")

from nicegui import ui, app

# 在 main.py 中项目的包建议放在最下面执行，这样最稳当（比如 .env 导入，nicegui 环境变量设置等）
import settings
from api import fastapi_app
from models import init_db, auto_upgrade_db
from utils import cleanup
from services import UserConfigService
from settings import dynamic_settings
from pages import register_pages
from log import logger

register_pages()

# [knowledge] 在创建 NiceGUI 应用时保留 FastAPI 的文档路由（不要让 nicegui 接管根路径）
app.mount("/api", fastapi_app)
app.add_static_files("/static", "static")
app.add_static_files("/fonts", "fonts")


@app.on_startup
async def startup_event():
    logger.info("🌱 app - startup")
    await init_db()
    if not settings.DEBUG:
        await auto_upgrade_db()
    async with UserConfigService() as service:
        await service.init_user_config()
    await cleanup.start()



@app.on_shutdown
async def shutdown_event():
    # fixme: 通过进程启动然后终止，app.on_shutdown 似乎无法正常执行，也就是说清理工作无法执行？
    logger.info("🔚 app - shutdown")
    await cleanup.stop()


@app.on_exception
def handle_exception(e: Exception):
    # 如果当前函数是 async，那么 traceback.format_exc() 的值是 NoneType: None，不知道为什么
    logger.error("捕获到全局异常：{}({})\n{}\n============", e, type(e).__name__, traceback.format_exc())


def main():
    # todo: 整理一下，目前已确定版本发布必用 PySide/pyinstaller，那么判断 dev 和 prod 建议用 IS_DEV = not hasattr(sys, "PYSTAND") and not hasattr(sys, "frozen") 即可
    # todo: 整理一份自己的 dev 和 prod 的通用区分逻辑，目前属于是乱七八糟

    if os.environ.get("PYWEBVIEW") or os.environ.get("PYSIDE"):
        logger.debug("启动端口：{}", int(os.environ["NICEGUI_PORT"]))
        ui.run(
            title=os.environ["NICEGUI_TITLE"],
            host="localhost",
            port=int(os.environ["NICEGUI_PORT"]),
            native=False,
            show=False,
            reload=False
        )
    else:
        logger.debug("启动端口：{}", settings.PORT)
        ui.run(
            title=dynamic_settings.title,
            host="localhost",
            port=settings.PORT,
            native=True,
            window_size=settings.WINDOW_SIZE,
            reload=settings.RELOAD
        )


if __name__ in {"__main__", "__mp_main__"}:
    main()
