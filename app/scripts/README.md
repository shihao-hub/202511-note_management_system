# scripts 目录

非 Python Package，类比 templates 目录，目的是将函数脚本化以支持动态载入。

虽然通过 sys.executable 执行应该是可以做到继承 .venv 虚拟环境的第三方库，
但是我建议只使用 python 标准库实现，因为可以练手和保证通用性。
但是既然继承第三方库，那我为什么要脚本化呢？写在源代码里不就行了。

---

注意，subprocess 启动 python.exe 去执行某个脚本显然是不靠谱的行为！耗时能做到将近 500ms！

能不能参考 lua？lua 是真的自由... 直接导入 lua 字符串就能直接执行...，然后拿到返回值...

调查发现，可行，但是需要有沙箱模式... 个人项目，直接用吧！

可参考 demo：
```python
import functools
import time
import traceback
from typing import Dict

@functools.lru_cache()
def run_script(script_path: str, loader: str = "./") -> Dict | None:
    """动态读取并执行外部 Python 脚本，并根据其 __all__ 列表返回受限的命名空间。如果没有定义 __all__，则返回完整命名空间。

    :param script_path: 外部脚本的文件路径
    :param loader: 加载器（参考 jinja2，未来扩展为一个类）
    :return: 包含脚本执行后所有全局变量的字典，执行失败返回 None
    """
    start = time.perf_counter()
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
```
