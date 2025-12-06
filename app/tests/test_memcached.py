import atexit
import os
import signal
import subprocess

from pymemcache import Client
from loguru import logger


class _MemcachedManager:
    """嵌入式 memcached，ai 生成，暂时测试使用

    [嵌入式地使用 memcached](https://lxblog.com/qianwen/share?shareId=7d5a9614-2475-4b1c-8cd8-ab492201db6a)

    最佳实践建议：
    - 仅在开发/测试环境使用：生产环境应使用**系统服务**管理 memcached
    - 检查端口是否被占用：避免冲突
    - 日志重定向：可将 stdout/stderr 重定向到文件便于调试
    - 权限问题：确保 ./bin/memcached 有执行权限

    """

    def __init__(self):
        self.memcached_bin = os.path.join(os.getcwd(), "..", "bin", "memcached", "memcached.exe")
        logger.debug("self.memcached_bin: {}", self.memcached_bin)
        self.memcached_host = "127.0.0.1"
        self.memcached_port = 11211  # 显然需要设置为动态
        self.memecached_pid: int | None = None
        self.registerd_stop_memcached = False
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = Client((self.memcached_host, self.memcached_port))
        return self._client

    def set(self, key: str, value: str):
        # 待定（client 使用示例而已）
        self.client.set(key, value)

    def get(self, key: str):
        # 待定（client 使用示例而已）
        return self.client.get(key)

    def start_memcached(self):
        if not os.path.exists(self.memcached_bin):
            raise FileNotFoundError(f"memcached binary not found at {self.memcached_bin}")

        # 注册退出清理函数（atexit good, os.kill good）
        if not self.registerd_stop_memcached:
            logger.debug("注册退出清理函数")
            atexit.register(self.stop_memcached)
            self.registerd_stop_memcached = True

        # 启动 memcached 子进程
        proc = subprocess.Popen(
            [self.memcached_bin, "-p", str(self.memcached_port), "-d", "-l", self.memcached_host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.memecached_pid = proc.pid

        logger.debug(f"Started memcached (PID: {proc.pid}) on port {self.memcached_port}")

    def stop_memcached(self):
        if self.memecached_pid:
            try:
                os.kill(self.memecached_pid, signal.SIGTERM)
                logger.debug("Stopped embedded memcached.")
            except ProcessLookupError:
                pass  # Already dead


memcached_manager = _MemcachedManager()

memcached_manager.start_memcached()

client = memcached_manager.client

client.set('hello', 'world')

value = client.get('hello')

print("Retrieved from memcached:", value.decode() if value else None)

input()
