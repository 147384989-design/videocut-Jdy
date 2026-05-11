#!/bin/bash
# 转录脚本 - 提取音频并转录
# 用法: bash transcribe.sh <视频文件路径>

VIDEO_PATH="$1"
OUTPUT_DIR="$2"

if [ -z "$VIDEO_PATH" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "用法: bash transcribe.sh <视频文件路径> <输出目录>"
    exit 1
fi

mkdir -p "$OUTPUT_DIR/1_转录"

echo "[1/4] 提取音频..."
ffmpeg -i "$VIDEO_PATH" -vn -acodec pcm_s16le -ar 16000 -ac 1 "$OUTPUT_DIR/1_转录/audio.wav" -y 2>&1 | tail -2

echo "[2/4] 检测静音段..."
ffmpeg -i "$OUTPUT_DIR/1_转录/audio.wav" -af "silencedetect=d=0.5:n=-30dB" -f null - 2>&1 | \
grep -E "silence_(start|end)" > "$OUTPUT_DIR/1_转录/silence.txt"

echo "[3/4] Whisper 转录..."
cd /home/jbm181818  # 确保在正确的WSL环境
python3 << 'PYEOF'
import whisper
import json
import sys

model = whisper.load_model('base', device='cpu')
result = model.transcribe('/tmp/audio.wav', language='zh', word_timestamps=True)

# 保存结果
with open('/tmp/whisper_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# 输出摘要
print(f"转录完成: {len(result['segments'])} 段")
PYEOF

if [ -f /tmp/whisper_result.json ]; then
    cp /tmp/whisper_result.json "$OUTPUT_DIR/1_转录/"
fi

echo "[4/4] 整理完成..."
echo "输出目录: $OUTPUT_DIR/1_转录/"