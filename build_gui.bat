@echo off
REM ============================================================
REM VideoCrawler GUI 版 — 一键打包成 EXE 启动器
REM 用法：双击运行 build_gui.bat
REM 输出：dist_gui\VideoCrawler\VideoCrawler.exe（双击即可启动 GUI）
REM ============================================================

setlocal
chcp 65001 >nul

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo ============================================================
echo  VideoCrawler GUI 版 打包工具
echo  入口: main_gui.py   框架: PySide6
echo ============================================================
echo.

REM ---------- 检查 Python ----------
set "PYTHON="
for %%p in (D:\python\python.exe python.exe) do (
    if exist %%p (
        set "PYTHON=%%p"
        goto :python_found
    )
)
echo ❌ 未找到 Python
pause & exit /b 1
:python_found
echo ✅ Python: %PYTHON%

REM ---------- 检查 PyInstaller ----------
%PYTHON% -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo 📦 安装 PyInstaller...
    %PYTHON% -m pip install pyinstaller --quiet
)
echo ✅ PyInstaller 已就绪

REM ---------- 清理旧输出 ----------
echo.
echo 🧹 清理旧的 build/dist_gui...
if exist build rmdir /s /q build
if exist dist_gui rmdir /s /q dist_gui
echo ✅ 清理完成

REM ---------- PyInstaller 打包 ----------
echo.
echo 📦 PyInstaller 打包中（GUI 版，含 PySide6，可能需要 2-6 分钟）...
%PYTHON% -m PyInstaller --clean --noconfirm --distpath dist_gui build_gui.spec
if errorlevel 1 (
    echo ❌ PyInstaller 打包失败！
    pause & exit /b 1
)
echo ✅ PyInstaller 打包完成

REM ---------- 复制外部资源 ----------
echo.
echo 📂 复制外部资源...

set "DIST=dist_gui\VideoCrawler"

REM ffmpeg
echo   - ffmpeg...
if exist "bin\ffmpeg" (
    xcopy /e /i /y "bin\ffmpeg" "%DIST%\bin\ffmpeg" >nul
) else if exist "bin" (
    xcopy /e /i /y "bin" "%DIST%\bin" >nul
)

REM yt-dlp
if exist "bin\yt-dlp.exe" copy /y "bin\yt-dlp.exe" "%DIST%\bin\" >nul

REM ASR 模型
echo   - ASR 模型...
if exist "models" (
    xcopy /e /i /y "models" "%DIST%\models" >nul
)

REM config（首次运行时如果不存在会自动生成默认值，但带上更方便）
echo   - 配置文件...
if exist "config.yaml" copy /y "config.yaml" "%DIST%\" >nul
if exist "api_secret.yaml.enc" copy /y "api_secret.yaml.enc" "%DIST%\" >nul
if exist "resources\schema.sql" (
    if not exist "%DIST%\resources" mkdir "%DIST%\resources"
    copy /y "resources\schema.sql" "%DIST%\resources\" >nul
)

REM ---------- 可选：生成一个带控制台的 debug 启动器 ----------
echo   - Debug 启动器（带控制台窗口，方便排错）...
(
echo @echo off
echo chcp 65001 ^>nul
echo cd /d "%%~dp0"
echo echo.
echo echo   VideoCrawler GUI Debug 模式
echo echo   ====================================
echo echo echo.
echo start "" cmd /c "VideoCrawler.exe --console"
echo timeout /t 2 ^>nul
echo VideoCrawler.exe
) > "%DIST%\VideoCrawler_Debug.bat"

REM ---------- 生成 README ----------
echo   - README...
(
echo VideoCrawler GUI 版 — 使用说明
echo ====================================
echo.
echo 启动方式:
echo   👉 双击 VideoCrawler.exe    — 直接启动 GUI 工作台（推荐）
echo   👉 双击 VideoCrawler_Debug.bat — 启动并打开控制台窗口（排错用）
echo.
echo 界面功能:
echo   ① 搜索与下载   ② 语音识别与翻译   ③ 字幕参数与预览   ④ 文案生成
echo.
echo 首次运行会自动创建:
echo   output\  — 下载的视频成品
echo   logs\    — 运行日志
echo   data\    — 数据库
echo   tmp\     — 临时文件
echo.
echo 配置文件:
echo   - config.yaml      API key 和参数（如需修改请用文本编辑器打开）
echo   - bin\ffmpeg\      ffmpeg 视频处理工具
echo   - models\asr\      ASR 语音识别模型
echo.
echo 迁移到新电脑:
echo   将整个 VideoCrawler\ 文件夹复制过去，双击 VideoCrawler.exe 即可运行。
) > "%DIST%\README.txt"

REM ---------- 结果 ----------
echo.
echo ============================================================
echo  ✅ GUI 版打包完成！
echo ============================================================
echo.
for /f "delims=" %%A in ('powershell -command "(Get-ChildItem -Recurse '%DIST%' ^| Measure-Object Length -Sum).Sum / 1MB"') do set "SIZE=%%A"
echo  输出目录: %DIST%
echo  大小: ~%SIZE% MB
echo.
echo  启动器: %DIST%\VideoCrawler.exe
echo  （双击即可打开 GUI，无需任何安装步骤）
echo.
pause
