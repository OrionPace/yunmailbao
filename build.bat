@echo off
chcp 65001 >nul
echo ============================================================
echo    云邮宝 (AutoEmail) - Windows EXE 一键打包脚本
echo ============================================================
echo.

:: Check if uv is available
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 未找到 uv 命令. 请先安装 uv: https://docs.astral.sh/uv/
    pause
    exit /b 1
)

:: Install pyinstaller via uv
echo [1/4] 正在安装 PyInstaller...
uv add --dev pyinstaller
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PyInstaller 安装失败!
    pause
    exit /b 1
)
echo [OK] PyInstaller 安装完成.
echo.

:: Create assets dir if needed
if not exist "assets" mkdir assets

:: Run PyInstaller
echo [2/4] 正在打包应用...
uv run pyinstaller auto_email.spec --noconfirm --clean
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 打包失败! 请检查错误信息.
    pause
    exit /b 1
)
echo [OK] 打包完成.
echo.

:: Copy .env.example to dist
echo [3/4] 正在复制配置模板...
copy /Y ".env.example" "dist\云邮宝\.env.example" >nul 2>&1
if not exist "dist\云邮宝\.env" (
    copy /Y ".env.example" "dist\云邮宝\.env" >nul 2>&1
)
echo [OK] 配置模板已复制.
echo.

echo [4/4] ============================================================
echo    打包完成! 输出目录: dist\云邮宝\
echo    
echo    使用方法:
echo    1. 将 dist\云邮宝\ 文件夹整体复制到目标电脑
echo    2. 编辑 .env 文件, 填入真实的邮箱账号密码
echo    3. 双击 云邮宝.exe 即可启动
echo ============================================================
echo.
pause
