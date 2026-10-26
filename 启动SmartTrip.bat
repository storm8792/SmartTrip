@echo off
chcp 65001 >nul
title SmartTrip - 行程播报系统
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 及以上版本，并勾选 Add to PATH。
    pause
    exit /b 1
)

echo 正在启动 SmartTrip...
python app.py

if errorlevel 1 (
    echo.
    echo 服务已退出，请查看上方错误信息。
    pause
)
