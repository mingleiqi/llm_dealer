@echo off
setlocal enabledelayedexpansion

:: 设置变量
set SCRIPT_DIR=%~dp0
set MINICONDA_URL=https://mirror.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py312_24.5.0-0-Windows-x86_64.exe
set INSTALLER_PATH=%SCRIPT_DIR%\miniconda_installer.exe
set ENV_PATH=%SCRIPT_DIR%\env

:: 检查指定的路径是否已安装 Conda
set CONDA_FOUND=0
for %%P in (C:\Users\%USERNAME%\miniconda3 c:\app\conda\ d:\app\conda\) do (
    if exist "%%P\Scripts\conda.exe" (
        set CONDA_FOUND=1
        set MINICONDA_PATH=%%P
        echo Conda is already installed at %MINICONDA_PATH%
        goto skip_install
    )
)

:: 1. 检查 C、D、E 盘剩余空间
for %%D in (C D E) do (
    set "FREE_SPACE=%%D:"
    for /f "tokens=3" %%F in ('dir /-c "%%D:\" ^| find "字节可用"') do set FREE_SPACE=%%F
    set FREE_SPACE=!FREE_SPACE:,=!  
    set "DISK_FREE[%%D]=!FREE_SPACE!"
)

:: 2. 找到剩余空间最大的盘符
set MAX_DISK=C
for /f "tokens=2,3 delims=[]" %%D in ('set DISK_FREE[') do (
    if !DISK_FREE[%%D]! gtr !DISK_FREE[%MAX_DISK%]! set MAX_DISK=%%D
)

:: 3. 设置 Miniconda 安装路径
set MINICONDA_PATH=%MAX_DISK%:\miniconda3

:: 4. 下载并安装 Miniconda (如果未找到)
:skip_install
if %CONDA_FOUND%==0 (
    echo Downloading Miniconda...
    powershell -Command "Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%INSTALLER_PATH%'"

    echo Installing Miniconda...
    start /wait "" "%INSTALLER_PATH%" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D="%MINICONDA_PATH%"

    del "%INSTALLER_PATH%"
)

:: 5. 创建虚拟环境
echo Creating virtual environment...
"%MINICONDA_PATH%\Scripts\conda.exe" create -y -p "%ENV_PATH%" python=3.12

:: 6. 激活环境并安装依赖
echo Activating environment and installing dependencies...
call "%ENV_PATH%\Scripts\activate.bat"
pip install -r requirements.txt

:: 7. 下载 7-Zip
echo Downloading 7-Zip...
powershell -Command "Invoke-WebRequest -Uri 'https://www.7-zip.org/a/7z2407-x64.exe' -OutFile '.\7z2407-x64.exe'"

:: 8. 静默安装 7-Zip (指定安装路径)
echo Installing 7-Zip...
.\7z2407-x64.exe /S /D="%SCRIPT_DIR%\7zip"

:: 9. 下载 xtquant_240613.rar
echo Downloading xtquant_240613.rar...
powershell -Command "Invoke-WebRequest -Uri 'https://dict.thinktrader.net/packages/xtquant_240613.rar' -OutFile '.\xtquant_240613.rar'"

:: 10. 解压 xtquant_240613.rar (指定解压路径)
echo Extracting xtquant_240613.rar...
"%SCRIPT_DIR%\7zip\7z.exe" x .\xtquant_240613.rar -o"%ENV_PATH%\Lib\site-packages"

:: 清理临时文件
echo Cleaning up temporary files...
del .\7z2407-x64.exe
del .\xtquant_240613.rar
