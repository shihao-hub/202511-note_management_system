import sys
import subprocess
import atexit
import urllib.request
import urllib.error
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer


def terminate_process_gracefully(proc, timeout=5):
    if proc and proc.poll() is None:
        print("Terminating backend process...")
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            print("Backend did not terminate gracefully; killing it.")
            proc.kill()


class MainWindow(QWidget):
    def __init__(self, backend_process):
        super().__init__()
        self.backend_process = backend_process
        self._retry_count = 0

        self.setWindowTitle("笔记管理系统")
        layout = QVBoxLayout(self)

        self.view = QWebEngineView()
        layout.addWidget(self.view)

        self.resize(1200, 900)

        # 立即显示“正在加载”页面
        self.show_loading_page()

        # 开始检查后端是否就绪
        QTimer.singleShot(100, self.check_backend_ready)

    def show_loading_page(self):
        html = """
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
            </style>
        </head>
        <body>
            <div class="loading">
                <div class="spinner"></div>
                <p>正在启动后端服务，请稍候...</p>
            </div>
        </body>
        </html>
        """
        self.view.setHtml(html)

    def check_backend_ready(self):
        health_url = "http://127.0.0.1:9999/health"
        index_url = "http://127.0.0.1:9999/"
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.getcode() == 200:
                    print("Backend is ready!")
                    self.view.load(QUrl(index_url))
                    return
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            pass  # 后端尚未就绪

        self._retry_count += 1
        if self._retry_count < 20:
            QTimer.singleShot(500, self.check_backend_ready)
        else:
            self.show_error_page()

    def show_error_page(self):
        html = """
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
                <p>后端进程未能及时启动。请检查日志或手动重启应用。</p>
            </div>
        </body>
        </html>
        """
        self.view.setHtml(html)
        print("Backend did not start in time.")

    def closeEvent(self, event):
        terminate_process_gracefully(self.backend_process, timeout=5)
        event.accept()