#!/bin/bash

# 1. 下载 Miniconda
wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py311_24.5.0-0-Linux-x86_64.sh

# 2. 静默安装 Miniconda
bash Miniconda3-py311_24.5.0-0-Linux-x86_64.sh -b -p ./env

# 3. 激活环境并安装依赖
source ./env/bin/activate
pip install -r requirements.txt

# 4. 下载 7-Zip
wget https://www.7-zip.org/a/7z2407-linux-x64.tar.xz

# 5. 解压 7-Zip
tar -xf 7z2407-linux-x64.tar.xz

# 6. 下载 xtquant
wget https://download.thinkfunds.cn/xtquant_240329_cp36m-37m-38-39-310-311_linux-gnu_x86_64.zip

# 7. 解压 xtquant 到指定目录
unzip xtquant_240329_cp36m-37m-38-39-310-311_linux-gnu_x66_64.zip -d ./env/lib/python3.11/site-packages

# 清理临时文件
rm Miniconda3-py311_24.5.0-0-Linux-x86_64.sh
rm 7z2407-linux-x64.tar.xz
rm xtquant_240329_cp36m-37m-38-39-310-311_linux-gnu_x86_64.zip
