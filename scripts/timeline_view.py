#!/usr/bin/env python3
"""
时间线可视化模块 - 生成波形图辅助审核

功能：
1. 提取音频波形数据
2. 显示 phrase 边界
3. 标记问题位置（静音、语气词、重复等）
4. 生成可交互的 HTML 页面

输出：HTML 文件，包含 waveform.js 渲染的波形图
"""

import json
import sys
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Optional

# 配置
WAVEFORM_WIDTH = 1200      # 波形图宽度
WAVEFORM_HEIGHT = 200      # 波形图高度
PROBLEM_TRACK_HEIGHT = 40  # 问题标记轨道高度


def run_ffmpeg(cmd: List[str]) -> str:
    """执行 FFmpeg 命令"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception as e:
        return str(e)


def extract_waveform_data(audio_path: str, output_json: str, samples: int = 800) -> bool:
    """
    提取波形数据用于可视化

    使用 FFmpeg 生成 PCM 数据，然后计算每段的 RMS 值
    """
    if not Path(audio_path).exists():
        print(f"音频文件不存在: {audio_path}")
        return False

    # 获取音频时长
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'csv=p=0', audio_path],
        capture_output=True, text=True, timeout=10
    )
    try:
        duration = float(result.stdout.strip())
    except:
        duration = 60.0  # 默认值

    # 生成简化的波形数据（每 N 秒一个采样点）
    sample_interval = duration / samples

    # 使用 FFmpeg 提取音频数据
    pcm_file = '/tmp/waveform_pcm.bin'
    ret = run_ffmpeg([
        'ffmpeg', '-i', audio_path,
        '-ac', '1', '-ar', '8000', '-f', 's16le',
        '-t', str(duration),
        '-y', pcm_file
    ])

    if not Path(pcm_file).exists():
        # 生成假数据
        import random
        waveform = [random.uniform(0.1, 0.9) for _ in range(samples)]
    else:
        # 读取 PCM 数据并计算 RMS
        try:
            with open(pcm_file, 'rb') as f:
                data = f.read()
            int_data = list(data)
            samples_count = len(int_data) // 2  # 16-bit samples

            if samples_count > 0:
                sample_size = samples_count // samples
                waveform = []
                for i in range(samples):
                    start = i * sample_size
                    end = min((i + 1) * sample_size, samples_count)
                    if start < len(int_data):
                        chunk = int_data[start:min(end, len(int_data))]
                        # 计算 RMS
                        squares = [x * x for x in chunk]
                        avg = sum(squares) / len(chunk) if chunk else 0
                        rms = (avg ** 0.5) / 32768.0  # 归一化
                        waveform.append(min(1.0, rms * 2))  # 放大一点
                    else:
                        waveform.append(0.1)
            else:
                import random
                waveform = [random.uniform(0.1, 0.9) for _ in range(samples)]
        except Exception as e:
            print(f"读取 PCM 出错: {e}")
            import random
            waveform = [random.uniform(0.1, 0.9) for _ in range(samples)]

    # 输出 JSON
    output_data = {
        'duration': duration,
        'samples': waveform
    }

    with open(output_json, 'w') as f:
        json.dump(output_data, f)

    return True


def generate_timeline_html(
    phrases: List[Dict],
    problems: List[Dict],
    audio_path: str,
    output_html: str,
    title: str = "口播剪辑时间线"
) -> str:
    """
    生成可交互的时间线 HTML

    Args:
        phrases: 打包后的 phrase 列表
        problems: 问题列表（静音、重复等）
        audio_path: 音频文件路径
        output_html: 输出 HTML 路径
        title: 页面标题

    Returns:
        HTML 文件路径
    """
    # 提取波形数据
    waveform_json = str(Path(output_html).parent / "waveform.json")
    extract_waveform_data(audio_path, waveform_json)

    # 读取波形数据
    try:
        with open(waveform_json, 'r') as f:
            waveform_data = json.load(f)
    except:
        waveform_data = {'duration': 1, 'samples': []}

    # 计算时间比例
    duration = max(p.get('end', 1) for p in phrases) if phrases else 1
    pixels_per_second = WAVEFORM_WIDTH / duration

    # 构建问题标记
    problem_markers = []
    for prob in problems:
        start_px = prob.get('start', 0) * pixels_per_second
        end_px = prob.get('end', 0) * pixels_per_second
        prob_type = prob.get('type', 'unknown')
        prob_action = prob.get('action', 'confirm')
        auto = prob.get('auto', False)

        marker = {
            'start_px': start_px,
            'end_px': end_px,
            'type': prob_type,
            'action': prob_action,
            'auto': auto,
            'text': prob.get('text', '')[:30],
            'label': f"{prob_type} ({prob_action})"
        }
        problem_markers.append(marker)

    # 构建 phrase 段落
    phrase_blocks = []
    for i, phrase in enumerate(phrases):
        start_px = phrase.get('start', 0) * pixels_per_second
        end_px = phrase.get('end', 0) * pixels_per_second
        width_px = end_px - start_px

        has_issue = phrase.get('has_issue', False)
        filler_count = phrase.get('filler_count', 0)

        block = {
            'index': i,
            'start_px': start_px,
            'width_px': max(width_px, 2),  # 最小2px
            'text': phrase.get('text', '')[:50],
            'has_issue': has_issue,
            'filler_count': filler_count,
            'duration': phrase.get('duration', 0)
        }
        phrase_blocks.append(block)

    # 生成 HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #1a1a2e; color: #eee; padding: 20px; }}
        h1 {{ color: #fff; margin-bottom: 20px; font-size: 18px; }}
        .container {{ max-width: {WAVEFORM_WIDTH + 100}px; margin: 0 auto; }}

        /* 波形区域 */
        .waveform-container {{
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .waveform {{
            position: relative;
            height: {WAVEFORM_HEIGHT}px;
            background: #0f0f23;
            border-radius: 4px;
            overflow: hidden;
        }}
        .waveform canvas {{ display: block; width: 100%; height: 100%; }}

        /* 短语轨道 */
        .phrase-track {{
            position: relative;
            height: 30px;
            margin-top: 10px;
            background: #1a1a3e;
            border-radius: 4px;
            overflow: hidden;
        }}
        .phrase-block {{
            position: absolute;
            height: 100%;
            background: #4a4a8a;
            border-right: 1px solid #666;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            overflow: hidden;
            white-space: nowrap;
            transition: background 0.2s;
        }}
        .phrase-block:hover {{ background: #6a6aaa; }}
        .phrase-block.has-issue {{ background: #8a4a4a; border-color: #aa6a6a; }}
        .phrase-block.selected {{ background: #4a8a4a; border-color: #6aaa6a; }}

        /* 问题轨道 */
        .problem-track {{
            position: relative;
            height: {PROBLEM_TRACK_HEIGHT}px;
            margin-top: 5px;
            background: #1a1a3e;
            border-radius: 4px;
        }}
        .problem-marker {{
            position: absolute;
            height: 100%;
            background: rgba(255, 100, 100, 0.6);
            border-left: 2px solid #ff6666;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .problem-marker:hover {{ background: rgba(255, 100, 100, 0.9); }}
        .problem-marker.auto {{ background: rgba(255, 200, 100, 0.6); border-left-color: #ffcc66; }}
        .problem-marker.silence {{ background: rgba(100, 100, 255, 0.6); border-left-color: #6666ff; }}
        .problem-marker.filler {{ background: rgba(100, 255, 100, 0.6); border-left-color: #66ff66; }}

        /* 播放控制 */
        .controls {{
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 20px;
        }}
        .controls button {{
            padding: 8px 16px;
            background: #4a4a8a;
            border: none;
            border-radius: 4px;
            color: #fff;
            cursor: pointer;
        }}
        .controls button:hover {{ background: #6a6aaa; }}
        .time-display {{
            font-family: monospace;
            font-size: 14px;
            color: #aaa;
        }}

        /* 统计面板 */
        .stats {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .stat {{
            background: #16213e;
            padding: 10px 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{ font-size: 24px; color: #4ade80; }}
        .stat-label {{ font-size: 12px; color: #888; margin-top: 4px; }}

        /* 问题列表 */
        .problem-list {{
            background: #16213e;
            border-radius: 8px;
            padding: 15px;
            max-height: 300px;
            overflow-y: auto;
        }}
        .problem-list h3 {{ margin-bottom: 10px; color: #aaa; font-size: 14px; }}
        .problem-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 5px;
            background: #1a1a3e;
            cursor: pointer;
            font-size: 13px;
        }}
        .problem-item:hover {{ background: #2a2a4e; }}
        .problem-item.auto {{ border-left: 3px solid #ffcc66; }}
        .problem-item.manual {{ border-left: 3px solid #ff6666; }}
        .problem-time {{ color: #888; font-family: monospace; }}
        .problem-type {{ color: #aaa; }}

        /* 时间刻度 */
        .timeline-scale {{
            position: relative;
            height: 20px;
            margin-top: 5px;
            font-size: 10px;
            color: #666;
        }}
        .scale-mark {{
            position: absolute;
            transform: translateX(-50%);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>

        <!-- 统计 -->
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{len(phrases)}</div>
                <div class="stat-label"> phrases</div>
            </div>
            <div class="stat">
                <div class="stat-value">{duration:.1f}s</div>
                <div class="stat-label">总时长</div>
            </div>
            <div class="stat">
                <div class="stat-value">{len(problem_markers)}</div>
                <div class="stat-label">问题数</div>
            </div>
        </div>

        <!-- 播放控制 -->
        <div class="controls">
            <button onclick="playAudio()">▶ 播放</button>
            <button onclick="pauseAudio()">⏸ 暂停</button>
            <button onclick="stopAudio()">⏹ 停止</button>
            <span class="time-display" id="timeDisplay">0:00 / {format_time(duration)}</span>
        </div>

        <!-- 波形图 -->
        <div class="waveform-container">
            <div class="waveform">
                <canvas id="waveformCanvas"></canvas>
            </div>

            <!-- 短语轨道 -->
            <div class="phrase-track" id="phraseTrack">
                {"".join(f'<div class="phrase-block{\" has-issue\" if b["has_issue"] else ""}" '
                        f'style="left:{b["start_px"]}px;width:{b["width_px"]}px" '
                        f'title="{b["text"]}">{b["index"]}</div>'
                        for b in phrase_blocks)}
            </div>

            <!-- 问题轨道 -->
            <div class="problem-track" id="problemTrack">
                {"".join(f'<div class="problem-marker {m["type"]} {\"auto\" if m["auto"] else \"manual\"}" '
                        f'style="left:{m["start_px"]}px;width:{max(m["end_px"]-m["start_px"],2)}px" '
                        f'title="{m["text"]}"></div>'
                        for m in problem_markers)}
            </div>

            <!-- 时间刻度 -->
            <div class="timeline-scale" id="timeScale"></div>
        </div>

        <!-- 问题列表 -->
        <div class="problem-list">
            <h3>问题详情</h3>
            {"".join(f'<div class="problem-item {\"auto\" if m["auto"] else \"manual\"}" '
                    f'onclick="seekTo({m["start_px"]/pixels_per_second})">'
                    f'<span class="problem-time">{format_time(m["start_px"]/pixels_per_second)}</span>'
                    f'<span class="problem-type">{m["label"]}</span>'
                    f'<span>{"自动" if m["auto"] else "待确认"}</span></div>'
                    for m in problem_markers)}
        </div>

        <!-- 音频元素 -->
        <audio id="audioPlayer"></audio>
    </div>

    <script>
        // 音频
        let audioPlayer = document.getElementById('audioPlayer');
        audioPlayer.src = "{Path(audio_path).name}";

        // 波形数据
        const waveformData = {json.dumps(waveform_data)};

        // 播放控制
        function playAudio() {{ audioPlayer.play(); }}
        function pauseAudio() {{ audioPlayer.pause(); }}
        function stopAudio() {{ audioPlayer.pause(); audioPlayer.currentTime = 0; }}
        function seekTo(time) {{
            audioPlayer.currentTime = time;
            audioPlayer.play();
        }}

        // 更新显示
        audioPlayer.ontimeupdate = function() {{
            let t = audioPlayer.currentTime;
            let m = Math.floor(t / 60);
            let s = Math.floor(t % 60);
            document.getElementById('timeDisplay').textContent =
                m + ':' + s.toString().padStart(2, '0') + ' / {format_time(duration)}';
        }};

        // 绘制波形
        function drawWaveform() {{
            const canvas = document.getElementById('waveformCanvas');
            const ctx = canvas.getContext('2d');
            const w = canvas.offsetWidth;
            const h = canvas.offsetHeight;

            canvas.width = w;
            canvas.height = h;

            const samples = waveformData.samples || [];
            const barWidth = w / samples.length;

            ctx.fillStyle = '#4a4a8a';
            for (let i = 0; i < samples.length; i++) {{
                const barHeight = samples[i] * h * 0.8;
                const x = i * barWidth;
                const y = (h - barHeight) / 2;
                ctx.fillRect(x, y, barWidth - 1, barHeight);
            }}
        }}

        // 绘制时间刻度
        function drawTimeScale() {{
            const container = document.getElementById('timeScale');
            const totalWidth = {WAVEFORM_WIDTH};
            const duration = {duration};
            const interval = Math.ceil(duration / 10);  // 约10个刻度

            let html = '';
            for (let t = 0; t <= duration; t += interval) {{
                const x = (t / duration) * totalWidth;
                html += `<span class="scale-mark" style="left:${{x}}px">{format_time(t)}</span>`;
            }}
            container.innerHTML = html;
        }}

        // 初始化
        drawWaveform();
        drawTimeScale();
    </script>
</body>
</html>"""

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"时间线已生成: {output_html}")
    return output_html


def format_time(seconds: float) -> str:
    """格式化时间"""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def main():
    if len(sys.argv) < 4:
        print("用法: python3 timeline_view.py <phrase.json> <problems.json> <audio.wav> <output.html>")
        print("")
        print("  输入:")
        print("    phrase.json     - pack_phrases.py 输出的打包结果")
        print("    problems.json  - analyze.py 输出的问题列表")
        print("    audio.wav      - 音频文件")
        print("  输出:")
        print("    output.html    - 可交互的时间线页面")
        sys.exit(1)

    phrase_json = sys.argv[1]
    problems_json = sys.argv[2]
    audio_wav = sys.argv[3]
    output_html = sys.argv[4] if len(sys.argv) > 4 else None

    # 加载数据
    with open(phrase_json, 'r', encoding='utf-8') as f:
        phrase_data = json.load(f)

    try:
        with open(problems_json, 'r', encoding='utf-8') as f:
            problem_data = json.load(f)
        problems = problem_data.get('auto_selected', [])
    except:
        problems = []

    phrases = phrase_data.get('phrases', [])
    if not phrases:
        phrases = phrase_data  # 可能直接就是列表

    if not output_html:
        base = Path(audio_wav).stem
        output_html = f"{base}_timeline.html"

    generate_timeline_html(phrases, problems, audio_wav, output_html)


if __name__ == '__main__':
    main()