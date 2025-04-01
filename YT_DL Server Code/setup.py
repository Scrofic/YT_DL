import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "include_files": [
        ("ffmpeg.exe", "ffmpeg.exe"),
        ("static", "static"),
        ("templates", "templates"),
    ],
    # 將 yt_dlp 模組由打包內部引用（不加入自動更新功能）
    "packages": [],
}

base = "Console" if sys.platform == "win32" else None

executables = [
    Executable(
        script="app.py",
        base=base,
        target_name="YT_DL Server.exe",
        icon="static/icon.ico",
    )
]

setup(
    name="YT_DL Server",
    version="2.0.0",
    description="YouTube Download Server",
    options={"build_exe": build_exe_options},
    executables=executables,
)