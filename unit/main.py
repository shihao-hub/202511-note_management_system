import os
import sys
import subprocess
import atexit
import threading
import time
import urllib.request
from pathlib import Path

import webview
from portpicker import pick_unused_port
from filelock import FileLock, Timeout
from plyer import notification

from log import logger

IS_DEV = not hasattr(sys, "PYSTAND")

os.environ["NICEGUI_TITLE"] = "笔记管理系统"
os.environ["NICEGUI_PORT"] = str(pick_unused_port())
os.environ["NICEGUI_WINDOW_SIZE_WIDTH"] = "1200"
os.environ["NICEGUI_WINDOW_SIZE_HEIGHT"] = "900"

LOADING_PAGE_HTML = """
<html>
<head>
    <style>
        body {
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #f5f5f5;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #333;
        }
        .loading {
            text-align: center;
            font-size: 24px;
        }
        .spinner {
            border: 4px solid rgba(0, 0, 0, 0.1);
            border-left-color: #0078d7;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        #timer {
            font-size: 16px;
            color: #666;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <p>正在启动后端服务，请稍候...</p>
        <div id="timer">已等待 <span id="seconds">0.0</span> 秒</div>
    </div>

    <script>
        let startTime = performance.now();
        const span = document.getElementById("seconds");

        function updateTimer() {
            let elapsed = (performance.now() - startTime) / 1000;
            span.textContent = elapsed.toFixed(1);
            requestAnimationFrame(updateTimer);
        }

        updateTimer();
    </script>
</body>
</html>
"""

ERROR_PAGE_HTML = """
<html>
<head>
    <style>
        body {
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            background-color: #fff5f5;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            color: #c00;
        }
        .error {
            text-align: center;
            font-size: 20px;
            max-width: 600px;
            padding: 20px;
        }
    </style>
</head>
<body>
    <div class="error">
        <h2>❌ 无法连接到后端服务</h2>
        <p>后端进程未能及时启动。请联系维护人员。</p>
    </div>
</body>
</html>
"""


def is_already_running():
    """通过文件锁保证单实例运行"""
    try:
        lock_file = os.path.join(os.path.expanduser("~"), f".notemanager_{"dev" if IS_DEV else "prod"}.lock")
        lock = FileLock(lock_file)
        lock.acquire(timeout=0)  # 非阻塞尝试获取锁，立即失败则说明已有实例
        atexit.register(lock.release)  # 退出时释放锁，即使不注册且程序崩溃，操作系统通常也会清理文件锁
        return False
    except Timeout:
        return True
    except Exception as e:
        logger.error("[pywebview] Failed to acquire lock file: {}({})", e, type(e).__name__)
        raise


def get_python_exe():
    runtime = Path("../runtime/").resolve()
    res = sys.executable if not runtime.exists() else str(runtime / "python.exe")
    logger.info(f"[pywebview] python.exe: {res}")
    return res


def terminate_process_gracefully(proc, timeout=5):
    if proc and proc.poll() is None:
        logger.info("[pywebview] Terminating backend process...")
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.info("[pywebview] Backend did not terminate gracefully; killing it.")
            proc.kill()


def start_backend():
    cmd = [get_python_exe(), "app.py"]
    env = os.environ.copy()
    env["PYWEBVIEW"] = "1"
    return subprocess.Popen(cmd, cwd=".", env=env, creationflags=subprocess.CREATE_NO_WINDOW if not IS_DEV else 0)


def start_app(window):
    index_url = f"http://127.0.0.1:{os.environ["NICEGUI_PORT"]}/"
    health_url = f"http://127.0.0.1:{os.environ["NICEGUI_PORT"]}/health"

    window.load_html(LOADING_PAGE_HTML)  # 显示加载页

    def health_check_loop():
        """后台健康检查"""
        retry_count = 0
        max_retries = 20
        while retry_count < max_retries:
            try:
                request = urllib.request.Request(health_url)
                with urllib.request.urlopen(request, timeout=1) as response:
                    if response.getcode() == 200:
                        logger.info("[pywebview] Backend is ready!")
                        window.load_url(index_url)
                        return
            except Exception as e:
                logger.debug(f"[pywebview] Health check failed: {e}")

            retry_count += 1
            time.sleep(0.1)

        logger.error("[pywebview] Backend did not start in time.")
        window.load_html(ERROR_PAGE_HTML)

    threading.Thread(target=health_check_loop, daemon=True).start()  # 正确理解守护线程：当主程序退出时，是否要等它


def main():
    if is_already_running():
        notification.notify(
            title=os.environ["NICEGUI_TITLE"],
            message=f"应用已在运行！",
            timeout=5
        )
        sys.exit(1)

    # 启动后台子进程
    backend_proc = start_backend()
    atexit.register(lambda: terminate_process_gracefully(backend_proc, timeout=3))

    # 初始加载页和启动主循环
    window = webview.create_window(
        os.environ["NICEGUI_TITLE"],
        html=LOADING_PAGE_HTML,
        width=int(os.environ["NICEGUI_WINDOW_SIZE_WIDTH"]),
        height=int(os.environ["NICEGUI_WINDOW_SIZE_HEIGHT"]),
        resizable=True
    )

    webview.start(start_app, window, debug=False)  # debug=True 可开启 DevTools（仅部分平台支持）


if __name__ == "__main__":
    main()
