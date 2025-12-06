__all__ = ["is_valid_filename"]

import re
import argparse
import sys
import traceback
import json


# Unix/Linux 世界以及现代命令行工具开发中 广泛遵循的标准约定：sys.stdout -> 程序结果，sys.stderr -> 调试信息、日志、警告、错误详情
# [是否符合最佳实践](https://www.qianwen.com/share?shareId=222ac435-fec6-432c-9ad0-1f5bc28dd312)

def log(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def is_valid_filename(filename: str, platform: str = "windows") -> bool:
    try:
        if not filename:
            raise ValueError(f"filename: '{filename}'")

        # 1. 长度检查（Linux 最大 255 字节，Windows 路径总长有限，但单文件名建议 <=255）
        if len(filename.encode("utf-8")) > 255:
            raise ValueError("长度检查不通过")

        # 2. 禁止字符（Windows + Linux 关键限制）
        # Windows 禁止: < > : " \ / | ? *
        # Linux 禁止: / 和 \0（但 \0 在 Python str 中很难出现）
        if re.search(r'[<>:"/\\|?*\x00-\x1f]', filename):
            raise ValueError("特殊字符检查不通过")

        # 3. 不能以空格或点结尾（Windows 会自动截断，导致问题）
        if filename.endswith(" ") or filename.endswith("."):
            raise ValueError("不能以空格或点结尾")

        # 4. 不能是 Windows 保留设备名（不区分大小写）
        reserved_names = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))
        }
        if filename.upper() in reserved_names:
            raise ValueError("不能是 Windows 保留设备名")

        # 5. 不能是纯点（如 "." 或 ".."）
        if filename in (".", ".."):
            raise ValueError("不能是纯点")

        # 6. 不能包含路径分隔符（虽然前面已禁 / 和 \，但再保险一点）
        if "/" in filename or "\\" in filename:
            raise ValueError("不能包含路径分隔符")
        return True
    except ValueError as e:
        raise e
    except Exception as e:
        log(f"{type(e).__name__} - {e}\n{traceback.format_exc()}============")
        return False


def main():
    # 通过 subprocess.run 执行的逻辑
    parser = argparse.ArgumentParser(description="检查文件名在指定操作系统下是否合法")

    parser.add_argument("filename", type=str, help="文件名")
    parser.add_argument(
        "-p", "--platform",
        type=str,
        default="windows",
        choices=["windows", "linux", "mac", "darwin"],
        help="目标平台（默认: 'windows'）"
    )
    parser.add_argument("--json", action="store_true", default=False, help="以 JSON 格式输出结果（便于程序解析）")

    args = parser.parse_args()

    log("[INFO] 开始检查文件名...")
    valid = is_valid_filename(args.filename, platform=args.platform)
    result = {"data": valid, "reason": None}
    print(f"{json.dumps(result)}\n")


if __name__ == "__main__":
    main()
