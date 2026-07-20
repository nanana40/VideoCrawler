@echo off
chcp 65001 >nul

echo =====================================================
echo MultiLangVideoCrawler 虚拟环境一键初始化脚本
echo =====================================================
echo.

:: 切换到脚本所在目录
cd /d "%~dp0"

:: ========== 1. 检查Python是否安装 ==========
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请先安装 Python 3.11 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: ========== 2. 强制校验Python版本 >= 3.11 ==========
for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set PY_VER=%%a
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)

if %PY_MAJOR% LSS 3 (
    echo [错误] 当前Python版本 %PY_VER% 过低，需要 Python 3.11+
    echo 请升级Python后重试
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 (
    echo [错误] 当前Python版本 %PY_VER% 过低，需要 Python 3.11+
    echo 请升级Python后重试
    pause
    exit /b 1
)

echo [信息] Python版本检测通过: %PY_VER%
echo.

:: ========== 3. 预检bin目录二进制文件 ==========
set BIN_WARN=0
if not exist "bin\ffmpeg.exe" (
    echo [警告] 未检测到 bin\ffmpeg.exe，下载功能将无法使用
    echo        请将 ffmpeg.exe 放入 bin 目录
    set BIN_WARN=1
)
if not exist "bin\yt-dlp.exe" (
    echo [警告] 未检测到 bin\yt-dlp.exe，下载功能将无法使用
    echo        请将 yt-dlp.exe 放入 bin 目录
    set BIN_WARN=1
)
if %BIN_WARN%==1 echo.

:: ========== 4. 创建/复用虚拟环境 ==========
if exist "venv\Scripts\python.exe" (
    echo [信息] 检测到已有虚拟环境 venv，将直接使用
) else (
    echo [信息] 正在创建虚拟环境 venv ...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败！
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境创建完成
)
echo.

:: ========== 5. 升级虚拟环境内部pip ==========
echo [信息] 正在升级pip ...
venv\Scripts\python.exe -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] pip升级失败，继续安装依赖...
)
echo.

:: ========== 6. 选择安装模式 ==========
echo 请选择依赖安装模式:
echo   1. 轻量化运行版 (requirements-runtime.txt) - 推荐生产环境
echo   2. 完整开发版 (requirements-dev.txt) - 含类型检查、打包工具
echo.
set /p MODE=请输入选项 [1/2]，默认1: 
if "%MODE%"=="" set MODE=1

if "%MODE%"=="1" (
    set REQ_FILE=requirements-runtime.txt
    set MODE_NAME=轻量化运行版
) else if "%MODE%"=="2" (
    set REQ_FILE=requirements-dev.txt
    set MODE_NAME=完整开发版
) else (
    echo [错误] 无效的选项: %MODE%
    pause
    exit /b 1
)

if not exist "%REQ_FILE%" (
    echo [错误] 未找到依赖文件 %REQ_FILE%
    pause
    exit /b 1
)

echo.
echo [信息] 安装模式: %MODE_NAME%
echo [信息] 正在安装依赖（使用清华镜像源），可能需要几分钟...
echo.

:: ========== 7. 安装依赖（全部通过venv绝对路径调用，不使用activate） ==========
venv\Scripts\pip.exe install -r "%REQ_FILE%" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败！
    echo 可能原因:
    echo   1. 网络连接异常，请检查网络或更换镜像源
    echo   2. 部分包版本冲突，可尝试手动安装
    echo.
    pause
    exit /b 1
)

echo.
echo [成功] 所有依赖安装完成！
echo.

:: ========== 8. 完成提示 ==========
echo =====================================================
echo 初始化完成！
echo =====================================================
echo.
echo 启动命令:
echo   venv\Scripts\python.exe main.py
echo.
echo 注意:
echo   - 请确保 bin 目录下有 ffmpeg.exe 和 yt-dlp.exe
echo   - 敏感密钥请通过 crypto_util 加密后存入 api_secret.yaml.enc
echo.

pause
