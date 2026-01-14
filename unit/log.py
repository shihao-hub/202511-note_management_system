import sys
import io

from loguru import logger

# region - template

# 移除默认的日志处理器
logger.remove()
# 创建一个 UTF-8 编码的文本包装器
utf8_stdout = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding="utf-8",
    errors="replace"  # 当遇到无法编码或解码的字符时，不抛出异常，而是用一个替代字符代替它，这样程序不会崩溃
)
# 控制台输出 - 彩色，简洁格式
logger.add(
    utf8_stdout,
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
