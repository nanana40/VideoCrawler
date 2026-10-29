@echo off
REM ================================================================
REM 【已废弃】公网隧道不再需要单独启动 cloudflared
REM ----------------------------------------------------------------
REM 原 cloudflared.exe 已从 web/ 移除, 本脚本不再调用任何隧道程序。
REM 远程访问 / 公网控制已迁移至 GUI 内嵌 Web + MQTT 通道:
REM   双击 start_gui.bat (或 start_all.bat) 启动图形界面,
REM   Web 服务 (:8000) 与 MQTT 远程通道会随 GUI 自动运行。
REM 本文件保留仅为占位, 请勿再以旧方式使用。
REM ================================================================
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  [已废弃] 公网隧道请通过 GUI 内嵌 Web 使用:
echo           请运行 start_gui.bat, Web 与 MQTT 远程通道会自动启动。
echo.
pause
