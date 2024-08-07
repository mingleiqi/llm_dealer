@echo off

:: 设置变量
set SCRIPT_DIR=%~dp0
set MINICONDA_URL=https://mirror.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py312_24.5.0-0-Windows-x86_64.exe
set INSTALLER_PATH=%SCRIPT_DIR%\miniconda_installer.exe

:: 1. 下载 Miniconda
echo Downloading Miniconda...
powershell -Command "Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%INSTALLER_PATH%'"

:: 2. 静默安装 Miniconda (指定安装路径)
echo Installing Miniconda...
start /wait "" "%INSTALLER_PATH%" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0  /S /D="%SCRIPT_DIR%\env"
