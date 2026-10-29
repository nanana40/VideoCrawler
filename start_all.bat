@echo off
REM ================================================================
REM VideoCrawler 一键启动 —— GUI 内嵌 Web 模式
REM 直接启动图形界面, Web 服务由 GUI 进程内自动拉起 (端口 8000)
REM 原独立 watchdog (:8001) 保活 + 单独 cloudflared 隧道方式已废弃
REM 关闭图形窗口即停止全部服务
REM ================================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  ================================================
echo   VideoCrawler · 一键启动 (GUI 内嵌 Web)
echo   Uvicorn  :8000  随 GUI 自动启动
echo   MQTT     远程控制通道随 GUI 自动连接
echo   关闭图形窗口即停止全部服务
echo  ================================================
echo.

D:\python\python.exe main_gui.py

pause
