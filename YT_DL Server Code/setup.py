import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "include_files": [
        ("ffmpeg.exe", "ffmpeg.exe"),
        ("static", "static"),
        ("templates", "templates"),
    ],
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
    version="2.0.3",
    description="YouTube Download Server",
    options={"build_exe": build_exe_options},
    executables=executables,
)
