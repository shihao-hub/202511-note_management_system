import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# region - [2025-11-23] compatible with old version database | 兼容旧版本数据库

def compatible_with_old_version():
    # Scan the Note table and extract content from the title field to populate Tag table | 扫描 Note 表，提取 title 字段中被 【】 包含的内容，用于创建 Tag 表内容
    conn = None
    try:
        conn = sqlite3.connect(str(BASE_DIR / "unit" / "notes.db"))

    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if conn is not None:
            conn.close()


# endregion


if __name__ == '__main__':
    pass
