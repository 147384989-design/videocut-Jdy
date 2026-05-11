#!/bin/bash
# 视频剪辑脚本 - 根据删除列表剪辑视频
# 用法: bash cut_video.sh <原视频> <输出视频> <删除片段JSON>

VIDEO_INPUT="$1"
VIDEO_OUTPUT="$2"
DELETE_JSON="$3"

if [ -z "$VIDEO_INPUT" ] || [ -z "$VIDEO_OUTPUT" ] || [ -z "$DELETE_JSON" ]; then
    echo "用法: bash cut_video.sh <原视频> <输出视频> <删除片段JSON>"
    exit 1
fi

# 检查文件是否存在
if [ ! -f "$VIDEO_INPUT" ]; then
    echo "错误: 视频文件不存在: $VIDEO_INPUT"
    exit 1
fi

echo "开始剪辑视频..."
echo "输入: $VIDEO_INPUT"
echo "输出: $VIDEO_OUTPUT"

# 获取原视频信息
echo "获取原视频参数..."
WIDTH=$(ffprobe -v error -select_streams v:0 -show_entries stream=width -of csv=p=0 "$VIDEO_INPUT")
HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$VIDEO_INPUT")
CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO_INPUT")
BITRATE=$(ffprobe -v error -select_streams v:0 -show_entries stream=bit_rate -of csv=p=0 "$VIDEO_INPUT")
if [ -z "$BITRATE" ]; then
    BITRATE=$(ffprobe -v error -show_entries format=bit_rate -of csv=p=0 "$VIDEO_INPUT")
fi
AUDIO_CODEC=$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$VIDEO_INPUT")
SAMPLE_RATE=$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$VIDEO_INPUT")

echo "视频: ${WIDTH}x${HEIGHT}, codec=$CODEC, bitrate=$BITRATE"
echo "音频: codec=$AUDIO_CODEC, rate=$SAMPLE_RATE"

# 解析删除列表
# DELETE_JSON 格式: [{"start": 1.5, "end": 2.3}, ...]
SEGMENTS=$(echo "$DELETE_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and len(data) > 0:
        if 'to_delete' in data[0]:
            data = [x for item in data for x in item.get('to_delete', [])]
    segments = []
    for d in data:
        if isinstance(d, dict) and 'start' in d and 'end' in d:
            segments.append((d['start'], d['end']))
    print(json.dumps(segments))
except Exception as e:
    print('[]')
    print(f'Error: {e}', file=sys.stderr)
")

if [ "$SEGMENTS" = "[]" ] || [ -z "$SEGMENTS" ]; then
    echo "没有需要删除的片段，复制原视频..."
    cp "$VIDEO_INPUT" "$VIDEO_OUTPUT"
    exit 0
fi

# 计算保留片段
# 反向遍历删除列表，从后往前计算保留片段
echo "计算保留片段..."

KEEP_FILE=$(mktemp)
echo "$SEGMENTS" | python3 -c "
import sys, json

segments = json.loads(sys.stdin.read())
segments.sort(key=lambda x: x[0])  # 按开始时间排序

# 计算保留片段（删除片段的补集）
keeps = []
if segments:
    # 第一个片段前
    if segments[0][0] > 0:
        keeps.append((0, segments[0][0]))

    # 中间片段
    for i in range(len(segments) - 1):
        if segments[i][1] < segments[i+1][0]:
            keeps.append((segments[i][1], segments[i+1][0]))

    # 最后一个片段后（取原视频总时长，这里用大数字估计）
    last_end = segments[-1][1]
    keeps.append((last_end, 9999))  # 用大数字，实际会用视频时长截断

# 过滤掉时长为0或负数的片段
keeps = [(s, e) for s, e in keeps if e > s and e > 0]

print(json.dumps(keeps))
" > "$KEEP_FILE"

# 读取保留片段
KEEP_SEGMENTS=$(cat "$KEEP_FILE")
echo "保留片段: $KEEP_SEGMENTS"

if [ "$KEEP_SEGMENTS" = "[]" ]; then
    echo "没有有效的保留片段"
    rm -f "$KEEP_FILE"
    exit 1
fi

# 获取视频总时长
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO_INPUT")
echo "视频总时长: $DURATION 秒"

# 构建 FFmpeg 滤镜
# 使用 select 滤镜配合 setpts 和 asetpts 来选择保留片段
BEFORE_SEGMENTS=""
AFTER_SEGMENTS=""
SELECT_EXPR=""

# 构建复杂滤镜
# 用 filter_complex 配合 concat 或 select

# 方法1: 使用 trim + setpts + concat
FILTER_COMPLEX=""
CONCAT_INPUTS=""

# 将保留片段转为 FFmpeg trim 指令
echo "$KEEP_SEGMENTS" | python3 -c "
import sys, json
keeps = json.loads(sys.stdin.read())
n = 0
for start, end in keeps:
    end = min(end, float('${DURATION:-9999}'))
    if end > start:
        print(f'[{n}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{n}];[{n}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{n}]')
        n += 1
" > /tmp/filter_parts.txt

# 读取并构建 filter_complex
N=$(cat /tmp/filter_parts.txt | grep -c "^\\[")
if [ "$N" -gt 0 ]; then
    # 构建 filter_complex
    FILTER_COMPLEX=""
    V_CONCAT=""
    A_CONCAT=""

    while IFS= read -r line; do
        idx=$(echo "$line" | grep -oP '^\[\K[^:]+')
        FILTER_COMPLEX="${FILTER_COMPLEX}${line},"
        V_CONCAT="${V_CONCAT}[v${idx}]"
        A_CONCAT="${A_CONCAT}[a${idx}]"
    done < /tmp/filter_parts.txt

    # 移除最后一个逗号，添加 concat
    FILTER_COMPLEX="${FILTER_COMPLEX%,}"
    FILTER_COMPLEX="${FILTER_COMPLEX}${V_CONX:=${V_CONCAT}}concat=n=${N}:v=1:a=1[outv][outa]"

    echo "执行 FFmpeg..."
    echo "Filter: $FILTER_COMPLEX"

    ffmpeg -i "$VIDEO_INPUT" -filter_complex "$FILTER_COMPLEX" \
        -map "[outv]" -map "[outa]" \
        -c:v libx264 -preset fast -crf 23 \
        -c:a aac -b:a 128k \
        -movflags +faststart \
        "$VIDEO_OUTPUT" -y 2>&1 | tail -20

    echo "FFmpeg 完成"
else
    echo "没有有效的保留片段"
    cp "$VIDEO_INPUT" "$VIDEO_OUTPUT"
fi

rm -f "$KEEP_FILE" /tmp/filter_parts.txt

echo "剪辑完成: $VIDEO_OUTPUT"