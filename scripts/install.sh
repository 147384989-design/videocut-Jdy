#!/bin/bash
# 自动安装脚本 - 安装口播剪辑工具所需依赖
# 用法: bash install.sh

set -e

echo "=========================================="
echo "  口播剪辑工具 - 自动安装脚本"
echo "=========================================="
echo ""

# 检测操作系统
OS=$(uname -s)
if [ "$OS" != "Linux" ]; then
    echo "警告: 本脚本设计用于 Linux/WSL 环境"
fi

# 检测 WSL
IS_WSL=false
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
    IS_WSL=true
    echo "检测到 WSL 环境"
fi

# 检查 Python
echo "[1/6] 检查 Python..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "  $PYTHON_VERSION"

# 检查 pip
echo "[2/6] 检查 pip..."
if ! python3 -m pip --version &> /dev/null; then
    echo "错误: 未找到 pip，请先安装 pip"
    exit 1
fi

# 检查 FFmpeg
echo "[3/6] 检查 FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "  未找到 FFmpeg，正在安装..."
    if [ "$IS_WSL" = true ]; then
        if command -v apt-get &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y ffmpeg
        fi
    fi
fi
FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1)
echo "  $FFMPEG_VERSION"

# 检查 Whisper
echo "[4/6] 检查 Whisper..."
if python3 -c "import whisper" 2>/dev/null; then
    echo "  Whisper 已安装"
else
    echo "  未找到 Whisper，正在安装..."
    pip install openai-whisper
fi

# 检查 Node.js
echo "[5/6] 检查 Node.js..."
if command -v node &> /dev/null; then
    echo "  Node.js $(node --version) 已安装"
else
    echo "  未找到 Node.js，正在安装..."
    if [ "$IS_WSL" = true ]; then
        if command -v apt-get &> /dev/null; then
            curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
            sudo apt-get install -y nodejs
        fi
    fi
fi

# 检查 Express (审核服务器依赖)
echo "[6/6] 检查审核服务器依赖..."
NODE_DIR="$(dirname "$(readlink -f "$0")")/scripts"
if [ -f "$NODE_DIR/package.json" ]; then
    if command -v npm &> /dev/null; then
        cd "$NODE_DIR"
        npm install express 2>/dev/null || echo "  npm 不可用，跳过"
    fi
fi

echo ""
echo "=========================================="
echo "  依赖检查完成"
echo "=========================================="
echo ""

# 验证安装
echo "验证安装..."
python3 -c "import whisper; print('  Whisper OK')" 2>/dev/null || echo "  Whisper 未正确安装"
ffmpeg -version 2>&1 | head -1 | sed 's/^/  /'

echo ""
echo "安装完成！"
echo ""
echo "使用说明："
echo "  1. 将视频文件放入项目目录"
echo "  2. 运行: bash scripts/transcribe.sh <视频文件>"
echo "  3. 打开 http://localhost:8899 审核"
echo "  4. 确认后自动剪辑"
echo ""