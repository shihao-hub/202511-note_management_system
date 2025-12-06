import functools
import os
import pprint
import subprocess
import sys
import json
import time
import traceback
from typing import Dict
from pathlib import Path


@functools.lru_cache()
def run_script(script_path: str, loader: str = "./") -> Dict | None:
    """动态读取并执行外部 Python 脚本，并根据其 __all__ 列表返回受限的命名空间。如果没有定义 __all__，则返回完整命名空间。

    :param script_path: 外部脚本的文件路径
    :param loader: 加载器（参考 jinja2，未来扩展为一个类）
    :return: 包含脚本执行后所有全局变量的字典，执行失败返回 None
    """
    start = time.perf_counter()
    # [note] 尽早出错（不得不说，JAVA 确实适合企业级项目）
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"脚本文件 '{script_path}' 不存在")
    if not path.is_file():
        raise FileNotFoundError(f"脚本文件 '{script_path}' 不是一个文件")
    try:
        namespace = {}
        with open(script_path, "r", encoding="utf-8") as f:
            exec(f.read(), namespace)
        if "__all__" in namespace:
            all_names = namespace["__all__"]
            if not isinstance(all_names, (list, tuple)):
                raise ValueError("__all__ 必须是 list 或 tuple")
            filtered_ns = {}
            for name in all_names:
                if name not in namespace:
                    raise AttributeError(f"__all__ 中包含未定义的名称: {name}")
                filtered_ns[name] = namespace[name]
            return filtered_ns
        return namespace
    except Exception as e:
        print(f"[ERROR] {type(e).__name__} - {e}\n{traceback.format_exc()}============")
        return None
    finally:
        print(f"[INFO] time interval: {(time.perf_counter() - start) * 1000:.4f} ms")


def main():
    def use_subprocess():
        start = time.perf_counter()
        process = subprocess.run(
            [sys.executable, "is_valid_filename.py", "test.txt"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        print(f"[INFO] time interval: {(time.perf_counter() - start) * 1000:.4f} ms")
        if process.stderr:
            sys.stderr.write(f"{process.stderr}\n")

        # stdout 是干净的结果！
        data = json.loads(process.stdout)  # {'data': True, 'reason': None}

        print(data)

    # use_subprocess()
    # print()

    # 实践发现，耗时也就 2~4 ms
    namespace = run_script("is_valid_filename.py")
    valid = namespace["is_valid_filename"]("text.txt")
    print(f"valid: {valid}")


if __name__ == "__main__":
    main()
