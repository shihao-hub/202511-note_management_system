import subprocess
import time


def git_push_with_retry(max_retries=1000):
    for attempt in range(1, max_retries + 1):
        print(f"尝试第 {attempt} 次执行 git push origin master:main...")
        try:
            # 执行 git push 命令
            result = subprocess.run(
                ["git", "push", "origin", "master:main"],
                capture_output=True,
                text=True,
                check=True  # 如果命令返回非零退出码，会抛出 CalledProcessError
            )
            print("推送成功！")
            print("标准输出:", result.stdout)
            return  # 成功则退出函数
        except subprocess.CalledProcessError as e:
            print(f"推送失败（第 {attempt} 次）:")
            print("错误输出:", e.stderr)
            if attempt < max_retries:
                print("等待1秒后重试...")
                time.sleep(1)  # 短暂等待后再重试，避免过于频繁
            else:
                print("已达到最大重试次数，退出。")
        except FileNotFoundError:
            print("错误：未找到 git 命令，请确保 Git 已安装并加入系统 PATH。")
            break
    print("脚本结束。")


if __name__ == "__main__":
    git_push_with_retry()
