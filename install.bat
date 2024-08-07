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

:: 3. 激活环境并安装依赖
echo Activating environment and installing dependencies...
call .\env\Scripts\activate.bat
pip install -r requirements.txt

:: 4. 下载 7-Zip
echo Downloading 7-Zip...
powershell -Command "Invoke-WebRequest -Uri 'https://www.7-zip.org/a/7z2407-x64.exe' -OutFile '.\7z2407-x64.exe'"

:: 5. 静默安装 7-Zip (指定安装路径)
echo Installing 7-Zip...
.\7z2407-x64.exe /S /D="%SCRIPT_DIR%\7zip"

:: 6. 下载 xtquant_240613.rar
echo Downloading xtquant_240613.rar...
powershell -Command "Invoke-WebRequest -Uri 'https://dict.thinktrader.net/packages/xtquant_240613.rar' -OutFile '.\xtquant_240613.rar'"

:: 7. 解压 xtquant_240613.rar (指定解压路径)
echo Extracting xtquant_240613.rar...
"%SCRIPT_DIR%\7zip\7z.exe" x .\xtquant_240613.rar -o"%SCRIPT_DIR%\env\Lib\site-packages"

:: 清理临时文件
echo Cleaning up temporary files...
del "%INSTALLER_PATH%"
del .\7z2407-x64.exe
del .\xtquant_240613.rar
