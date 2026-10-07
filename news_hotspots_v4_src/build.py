# -*- coding: utf-8 -*-
"""
一键打包脚本

    python build.py            # 打包成单文件 exe
    python build.py --onedir   # 打包成目录（启动更快，便于排查）
    python build.py --clean    # 先清理再打包

产物：dist/新闻热点速览.exe
随后可用 Inno Setup 编译 setup_v4.iss 生成安装程序。
"""

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "新闻热点速览.spec")
NAME = "新闻热点速览"


def run(cmd, cwd=HERE):
    print("> %s" % " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        print("\n打包失败，退出码 %d" % r.returncode)
        sys.exit(r.returncode)


def ensure_pyinstaller():
    try:
        import PyInstaller                                  # noqa: F401
        return
    except ImportError:
        print("未检测到 PyInstaller，正在安装…")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def main():
    args = sys.argv[1:]
    if "--clean" in args:
        for d in ("build", "dist", "__pycache__"):
            p = os.path.join(HERE, d)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
                print("已清理 %s/" % d)

    ensure_pyinstaller()

    if "--onedir" in args:
        cmd = [sys.executable, "-m", "PyInstaller",
               "--noconfirm", "--onedir", "--windowed",
               "--icon", "app.ico", "--name", NAME,
               "--hidden-import", "nhv4",
               "news_hotspots_v4.py"]
    else:
        cmd = [sys.executable, "-m", "PyInstaller", SPEC, "--noconfirm"]
    run(cmd)

    exe = os.path.join(HERE, "dist", NAME + ".exe")
    if os.path.exists(exe):
        mb = os.path.getsize(exe) / 1048576.0
        print("\n打包完成：%s （%.1f MB）" % (exe, mb))
        print("接下来：用 Inno Setup 编译 setup_v4.iss 生成安装程序。")
    else:
        print("\n未找到产物，请检查上方输出。")


if __name__ == "__main__":
    main()
