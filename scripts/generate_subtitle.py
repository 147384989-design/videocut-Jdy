#!/usr/bin/env python3
"""
字幕生成脚本 - 从Whisper结果生成SRT/ASS字幕
用法: python3 generate_subtitle.py <whisper_result.json> <output.srt>
"""

import json
import sys
from pathlib import Path

def format_time_srt(seconds):
    """转换为 SRT 时间格式: HH:MM:SS,mmm"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_time_ass(seconds):
    """转换为 ASS 时间格式: HH:MM:SS.cc"""
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

def generate_srt(segments, output_path):
    """生成 SRT 字幕"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, seg in enumerate(segments, 1):
            start = format_time_srt(seg['start'])
            end = format_time_srt(seg['end'])
            text = seg['text'].strip()

            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n")
            f.write("\n")

    print(f"SRT 字幕已生成: {output_path}")

def generate_ass(segments, output_path):
    """生成 ASS 字幕（带样式）"""
    with open(output_path, 'w', encoding='utf-8') as f:
        # ASS 头
        f.write("[Script Info]\n")
        f.write("Title: 口播字幕\n")
        f.write("ScriptType: v4.00+\n")
        f.write("WrapStyle: 0\n")
        f.write("ScaledBorderAndShadow: Yes\n")
        f.write("\n")

        # V4 样式
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n")
        f.write("\n")

        # 事件
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for seg in segments:
            start = format_time_ass(seg['start'])
            end = format_time_ass(seg['end'])
            text = seg['text'].strip().replace('\n', ' ').replace('<', '&lt;').replace('>', '&gt;')

            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    print(f"ASS 字幕已生成: {output_path}")

def main():
    if len(sys.argv) < 3:
        print("用法: python3 generate_subtitle.py <whisper_result.json> <output.srt> [--ass]")
        sys.exit(1)

    whisper_json = sys.argv[1]
    output_path = sys.argv[2]
    use_ass = '--ass' in sys.argv

    # 加载 Whisper 结果
    with open(whisper_json, 'r', encoding='utf-8') as f:
        data = json.load(f)

    segments = data.get('segments', [])
    if not segments:
        print("错误: 没有找到转录段落")
        sys.exit(1)

    print(f"共 {len(segments)} 段字幕")

    if use_ass:
        generate_ass(segments, output_path)
    else:
        generate_srt(segments, output_path)

if __name__ == '__main__':
    main()