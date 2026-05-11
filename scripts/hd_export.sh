#!/bin/bash
# 高清导出脚本 - 2-pass 编码 + 锐化
# 用法: bash hd_export.sh <输入视频> <输出视频> [码率倍数]

INPUT="$1"
OUTPUT="$2"
RATE_MULT="${3:-1.2}"

if [ -z "$INPUT" ] || [ -z "$OUTPUT" ]; then
    echo "用法: bash hd_export.sh <输入视频> <输出视频> [码率倍数]"
    echo "默认码率倍数: 1.2"
    exit 1
fi

echo "=== 高清导出开始 ==="
echo "输入: $INPUT"
echo "输出: $OUTPUT"
echo "码率倍数: $RATE_MULT"

# 获取原视频参数
echo "获取原视频参数..."
WIDTH=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$INPUT")
HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$INPUT")
CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$INPUT")
PIXEL_FMT=$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$INPUT")
PROFILE=$(ffprobe -v error -select_streams v:0 -show_entries stream=profile -of csv=p=0 "$INPUT")

# 获取码率
ORIG_BITRATE=$(ffprobe -v error -show_entries format=bit_rate -of csv=p=0 "$INPUT")
if [ -z "$ORIG_BITRATE" ] || [ "$ORIG_BITRATE" = "N/A" ]; then
    ORIG_BITRATE=$(ffprobe -v error -select_streams v:0 -show_entries stream=bit_rate -of csv=p=0 "$INPUT")
fi

# 如果无法获取码率，使用估算
if [ -z "$ORIG_BITRATE" ] || [ "$ORIG_BITRATE" = "N/A" ]; then
    echo "无法获取原码率，使用默认 5000k"
    ORIG_BITRATE=5000000
fi

# 转换为数字计算
ORIG_K=$((ORIG_BITRATE / 1000))
NEW_K=$((ORIG_K * RATE_MULT))
NEW_BITRATE="${NEW_K}k"

echo "原视频: ${WIDTH}x${HEIGHT}, codec=$CODEC, pix_fmt=$PIXEL_FMT"
echo "原码率: ${ORIG_K}k → 新码率: ${NEW_K}k"

# 获取音频参数
AUDIO_CODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$INPUT")
AUDIO_SAMPLE=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$INPUT")
AUDIO_CHANNELS=$(ffprobe -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$INPUT")

echo "音频: codec=$AUDIO_CODEC, rate=$AUDIO_SAMPLE, channels=$AUDIO_CHANNELS"

# 2-pass 编码
TEMP_LOG=$(mktemp)

echo ""
echo "=== Pass 1/2 ==="
ffmpeg -i "$INPUT" \
    -c:v libx264 -preset slow -b:v "$NEW_BITRATE" -pass 1 \
    -profile:v high -pix_fmt yuv420p \
    -c:a copy \
    -f null - -y 2>&1 | tee "$TEMP_LOG" | tail -5

echo ""
echo "=== Pass 2/2 ==="
ffmpeg -i "$INPUT" \
    -c:v libx264 -preset slow -b:v "$NEW_BITRATE" -pass 2 \
    -profile:v high -pix_fmt yuv420p \
    -c:a aac -b:a 192k \
    -movflags +faststart \
    "$OUTPUT" -y 2>&1 | tail -10

# 清理
rm -f "$TEMP_LOG" "*ffmpeg2pass*" 2>/dev/null

# 验证输出
if [ -f "$OUTPUT" ]; then
    OUTPUT_SIZE=$(du -h "$OUTPUT" | cut -f1)
    echo ""
    echo "=== 高清导出完成 ==="
    echo "输出文件: $OUTPUT"
    echo "文件大小: $OUTPUT_SIZE"
else
    echo "错误: 输出文件生成失败"
    exit 1
fi