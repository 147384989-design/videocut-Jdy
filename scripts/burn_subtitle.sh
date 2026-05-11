#!/bin/bash
# 字幕烧录脚本 - 将字幕文件烧录到视频中
# 用法: bash burn_subtitle.sh <视频> <字幕> <输出视频>

VIDEO_INPUT="$1"
SUBTITLE_FILE="$2"
VIDEO_OUTPUT="$3"

if [ -z "$VIDEO_INPUT" ] || [ -z "$SUBTITLE_FILE" ] || [ -z "$VIDEO_OUTPUT" ]; then
    echo "用法: bash burn_subtitle.sh <视频> <字幕> <输出视频>"
    echo "示例: bash burn_subtitle.sh input.mp4 subtitle.srt output.mp4"
    exit 1
fi

# 检查文件是否存在
if [ ! -f "$VIDEO_INPUT" ]; then
    echo "错误: 视频文件不存在: $VIDEO_INPUT"
    exit 1
fi

if [ ! -f "$SUBTITLE_FILE" ]; then
    echo "错误: 字幕文件不存在: $SUBTITLE_FILE"
    exit 1
fi

echo "开始烧录字幕..."
echo "输入视频: $VIDEO_INPUT"
echo "字幕文件: $SUBTITLE_FILE"
echo "输出视频: $VIDEO_OUTPUT"

# 获取视频信息
WIDTH=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO_INPUT")
HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO_INPUT")
CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO_INPUT")
FPS=$(ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of csv=p=0 "$VIDEO_INPUT")
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO_INPUT")

echo "视频信息: ${WIDTH}x${HEIGHT}, codec=$CODEC, fps=$FPS, duration=$DURATION"

# 判断字幕格式并构建滤镜
SUB_EXT="${SUBTITLE_FILE##*.}"
SUB_EXT=$(echo "$SUB_EXT" | tr '[:upper:]' '[:lower:]')

if [ "$SUB_EXT" = "srt" ]; then
    SUB_FILTER="subtitles='$SUBTITLE_FILE'"
elif [ "$SUB_EXT" = "ass" ]; then
    SUB_FILTER="ass='$SUBTITLE_FILE'"
else
    echo "错误: 不支持的字幕格式: $SUB_EXT (仅支持 srt, ass)"
    exit 1
fi

# 获取音频信息（用于判断是否需要复制音频）
AUDIO_CODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO_INPUT")

echo "音频 codec: $AUDIO_CODEC"

# 构建 FFmpeg 命令
# 字幕烧录需要用 libass 滤镜
echo "构建 FFmpeg 命令..."

# 检查是否已有字幕流
HAS_SUB_STREAM=$(ffprobe -v error -select_streams s -show_entries stream=codec_name -of csv=p=0 "$VIDEO_INPUT" | grep -c "srt\|ass\|subtitle" || echo "0")

if [ "$CODEC" = "h264" ] || [ "$CODEC" = "hevc" ]; then
    # 重新编码视频以烧录字幕
    if [ -n "$AUDIO_CODEC" ]; then
        # 有音频，保留音频
        ffmpeg -i "$VIDEO_INPUT" -i "$SUBTITLE_FILE" \
            -c:v libx264 -preset fast -crf 23 \
            -c:a copy -c:s copy \
            -attach "$SUBTITLE_FILE" \
            -metadata:s:s:0 title="字幕" \
            "$VIDEO_OUTPUT" -y 2>&1 | tail -30
    else
        # 无音频，重新编码
        ffmpeg -i "$VIDEO_INPUT" -i "$SUBTITLE_FILE" \
            -c:v libx264 -preset fast -crf 23 \
            -c:a aac -b:a 128k \
            -c:s copy \
            "$VIDEO_OUTPUT" -y 2>&1 | tail -30
    fi
else
    # 其他编码器，重新编码
    if [ -n "$AUDIO_CODEC" ]; then
        ffmpeg -i "$VIDEO_INPUT" -i "$SUBTITLE_FILE" \
            -c:v libx264 -preset fast -crf 23 \
            -vf "$SUB_FILTER:force_style='FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H00000000,Outline=2'" \
            -c:a copy \
            -c:s copy \
            "$VIDEO_OUTPUT" -y 2>&1 | tail -30
    else
        ffmpeg -i "$VIDEO_INPUT" -i "$SUBTITLE_FILE" \
            -c:v libx264 -preset fast -crf 23 \
            -vf "$SUB_FILTER:force_style='FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H00000000,Outline=2'" \
            -c:a aac -b:a 128k \
            -c:s copy \
            "$VIDEO_OUTPUT" -y 2>&1 | tail -30
    fi
fi

if [ $? -eq 0 ]; then
    # 验证输出文件
    OUTPUT_SIZE=$(stat -c%s "$VIDEO_OUTPUT" 2>/dev/null || stat -f%z "$VIDEO_OUTPUT" 2>/dev/null)
    OUTPUT_DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO_OUTPUT")

    echo ""
    echo "========== 烧录完成 =========="
    echo "输出文件: $VIDEO_OUTPUT"
    echo "文件大小: $OUTPUT_SIZE bytes"
    echo "视频时长: $OUTPUT_DURATION 秒"
    echo "==============================="
else
    echo ""
    echo "烧录失败，请检查错误信息"
    exit 1
fi