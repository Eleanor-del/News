# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置（单文件 / 无控制台窗口）

    pyinstaller 新闻热点速览.spec --noconfirm
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("nhv4")
hiddenimports += [
    "sqlite3",
    "xml.etree.ElementTree",
    "PIL",
    "PIL.ImageTk",
]

# 用不到的重型库，剔除可显著减小体积
excludes = [
    "matplotlib", "numpy", "pandas", "scipy", "PyQt5", "PySide2", "PySide6",
    "IPython", "notebook", "pytest", "tkinter.test", "unittest",
    "curses", "distutils", "setuptools", "wheel",
]

block_cipher = None

a = Analysis(
    ["news_hotspots_v4.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="新闻热点速览",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="app.ico",
)
