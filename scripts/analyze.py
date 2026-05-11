#!/usr/bin/env python3
"""
口播分析脚本 - 分析转录结果，生成删除列表
基于用户习惯规则：语气词、卡顿词、句内重复、残句检测

用法: python3 analyze.py <转录JSON> <静音文件> <输出目录>
"""

import json
import sys
import re
from pathlib import Path
from datetime import datetime

# ===== 加载用户习惯规则 =====
USER_HABITS_DIR = Path(__file__).parent.parent / "用户习惯"
RULES_DIR = USER_HABITS_DIR / "rules" if (USER_HABITS_DIR / "rules").exists() else None

# 语气词表（从规则文档）
FILLER_WORDS = ['嗯', '啊', '呃', '哦', '呀', '哇', '嘛', '呢', '啦', '呐',
                '这个', '那个', '就是', '就是说', '然后', '其实', '的话',
                '这个这个', '那个那个', '就是就是', '的话的话', '对对对', '不不不']

# 卡顿词（重复词）模式
STUTTER_PATTERNS = [
    (r'那个那个+', '那个'),
    (r'这个这个+', '这个'),
    (r'就是就是+', '就是'),
    (r'的话的话+', '的话'),
    (r'对对对+', '对'),
    (r'不不不+', '不'),
]

# 静音阈值配置
AUTO_DELETE_SILENCE = 1.0  # 秒 - 全自动删除
CONFIRM_SILENCE = 0.5      # 秒 - 需确认
REPETITION_CHARS = 5        # 重复判断字符数

def load_whisper_result(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_silence(silence_path):
    """解析FFmpeg静音检测结果"""
    silences = []
    if not Path(silence_path).exists():
        return silences

    with open(silence_path, 'r') as f:
        lines = f.readlines()

    current = None
    for line in lines:
        line = line.strip()
        if 'silence_start' in line:
            match = re.search(r'silence_start: ([\d.]+)', line)
            if match:
                current = {'start': float(match.group(1))}
        elif 'silence_end' in line and current:
            match = re.search(r'silence_end: ([\d.]+)', line)
            if match:
                current['end'] = float(match.group(1))
                match2 = re.search(r'silence_duration: ([\d.]+)', line)
                if match2:
                    current['duration'] = float(match2.group(1))
                silences.append(current)
                current = None

    return silences

def load_dictionary():
    """加载词表纠错词典"""
    dict_path = USER_HABITS_DIR / "词典.txt"
    corrections = {}
    if dict_path.exists():
        with open(dict_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '->' in line and not line.startswith('#'):
                    parts = line.split('->')
                    if len(parts) == 2:
                        corrections[parts[0].strip()] = parts[1].strip()
    return corrections

def correct_text(text, corrections):
    """应用词典纠错"""
    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)
    return text

def detect_silences(silences, segments):
    """检测静音并分类处理"""
    detected = []

    for s in silences:
        duration = s.get('duration', 0)
        start = s['start']
        end = s['end']

        # 分类
        if duration >= AUTO_DELETE_SILENCE:
            action = 'auto_delete'
        elif duration >= CONFIRM_SILENCE:
            action = 'confirm'
        else:
            action = 'ignore'  # 自然停顿

        # 查找静音前后的句子
        prev_sentence = None
        next_sentence = None
        for i, seg in enumerate(segments):
            if seg['end'] <= start:
                prev_sentence = seg
            if seg['start'] >= end:
                next_sentence = seg
                break

        detected.append({
            'type': 'silence',
            'start': start,
            'end': end,
            'duration': duration,
            'action': action,
            'prev_sentence': prev_sentence['text'][:30] if prev_sentence else None,
            'next_sentence': next_sentence['text'][:30] if next_sentence else None,
            'auto': action == 'auto_delete'
        })

    return detected

def detect_stutters(segments):
    """检测卡顿词（重复词如"那个那个"）"""
    detected = []

    for i, seg in enumerate(segments):
        text = seg['text']

        for pattern, replacement in STUTTER_PATTERNS:
            matches = list(re.finditer(pattern, text))
            if matches:
                for match in matches:
                    start_char = match.start()
                    end_char = match.end()

                    # 计算在时间轴上的位置（估算）
                    char_ratio = len(text) / (seg['end'] - seg['start']) if seg['end'] > seg['start'] else 1
                    start_time = seg['start'] + start_char / char_ratio
                    end_time = seg['start'] + end_char / char_ratio

                    detected.append({
                        'type': 'stutter',
                        'start': start_time,
                        'end': end_time,
                        'text': match.group(),
                        'replacement': replacement,
                        'segment_idx': i,
                        'action': 'auto_delete',
                        'auto': True
                    })

    return detected

def detect_filler_words(segments):
    """检测语气词（单次出现）"""
    detected = []

    for i, seg in enumerate(segments):
        text = seg['text'].strip()

        for fw in FILLER_WORDS:
            if fw in text:
                # 检查连续出现次数
                count = text.count(fw)

                if count >= 3:
                    action = 'auto_delete'
                elif count >= 2:
                    action = 'confirm'
                else:
                    action = 'mark'  # 仅标记

                detected.append({
                    'type': 'filler',
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': text[:50],
                    'word': fw,
                    'count': count,
                    'action': action,
                    'auto': count >= 3
                })

    return detected

def detect_repetitions(segments):
    """检测句内重复（被静音截断的重复，如"你再关[静]你关掉"）"""
    detected = []

    for i in range(len(segments) - 1):
        curr = segments[i]
        next_seg = segments[i + 1]

        curr_text = curr['text'].strip()
        next_text = next_seg['text'].strip()

        if not curr_text or not next_text:
            continue

        # 检查中间是否有静音
        gap = next_seg['start'] - curr['end']
        has_silence = gap >= CONFIRM_SILENCE

        # 取前N字比较
        min_len = min(len(curr_text), len(next_text), REPETITION_CHARS)
        if min_len >= REPETITION_CHARS:
            if curr_text[:REPETITION_CHARS] == next_text[:REPETITION_CHARS]:
                # 判断是哪种重复
                if has_silence:
                    # 被静音截断的重说 - 删前保后
                    detected.append({
                        'type': 'repetition',
                        'start': curr['start'],
                        'end': next_seg['start'],  # 包含静音
                        'before': curr_text[:20],
                        'after': next_text[:20],
                        'gap': gap,
                        'action': 'delete_before',  # 删前保后
                        'auto': True
                    })
                elif len(next_text) > len(curr_text):
                    # 后者更长，可能更完整
                    detected.append({
                        'type': 'repetition',
                        'start': curr['start'],
                        'end': curr['end'],
                        'before': curr_text[:20],
                        'after': next_text[:20],
                        'gap': 0,
                        'action': 'confirm',
                        'auto': False
                    })

    return detected

def detect_incomplete_sentences(segments, silences):
    """检测残句（话说一半+静音）"""
    detected = []

    # 建立静音索引
    silence_map = []
    for s in silences:
        silence_map.append((s['start'], s['end'], s.get('duration', 0)))

    for i, seg in enumerate(segments):
        text = seg['text'].strip()

        # 检查是否是不完整的句子开头
        is_incomplete = False
        reasons = []

        # 情况1: 以连词开头（"然后..."、"但是..."）
        if re.match(r'^(然后|但是|因为|所以|如果|虽然|而且|或者)', text):
            is_incomplete = True
            reasons.append('以连词开头')

        # 情况2: 以代词开头但无主语
        if re.match(r'^(我|你|他|她|它|我们|你们|他们)', text):
            # 检查是否有谓语（简单判断：是否有动词）
            if len(text) < 10:
                is_incomplete = True
                reasons.append('短句代词开头')

        # 情况3: 句子明显不完整（无动词）
        if len(text) < 5 and re.match(r'^(关于|这个|那个|对于)', text):
            is_incomplete = True
            reasons.append('简短残句')

        # 检查后面是否有静音
        has_following_silence = False
        for s_start, s_end, duration in silence_map:
            if s_start >= seg['end'] and s_start - seg['end'] < 2:
                has_following_silence = True
                break

        if is_incomplete and has_following_silence:
            detected.append({
                'type': 'incomplete',
                'start': seg['start'],
                'end': seg['end'],
                'text': text[:30],
                'reason': '; '.join(reasons),
                'action': 'delete',
                'auto': True
            })

    return detected

def main():
    if len(sys.argv) < 4:
        print("用法: python3 analyze.py <转录JSON> <静音文件> <输出目录>")
        sys.exit(1)

    whisper_json = sys.argv[1]
    silence_file = sys.argv[2]
    output_dir = sys.argv[3]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 加载数据
    print("[1/5] 加载转录数据...")
    result = load_whisper_result(whisper_json)
    segments = result['segments']

    print("[2/5] 检测静音...")
    silences = load_silence(silence_file)

    print("[3/5] 分析口误...")
    corrections = load_dictionary()
    auto_selected = []

    # 1. 静音检测（分类处理）
    silence_results = detect_silences(silences, segments)
    for s in silence_results:
        if s['action'] != 'ignore':
            auto_selected.append(s)

    # 2. 卡顿词检测
    stutter_results = detect_stutters(segments)
    auto_selected.extend(stutter_results)

    # 3. 语气词检测
    filler_results = detect_filler_words(segments)
    auto_selected.extend(filler_results)

    # 4. 句内重复检测
    repetition_results = detect_repetitions(segments)
    auto_selected.extend(repetition_results)

    # 5. 残句检测
    incomplete_results = detect_incomplete_sentences(segments, silences)
    auto_selected.extend(incomplete_results)

    # 统计
    stats = {
        'silence': sum(1 for x in auto_selected if x['type'] == 'silence'),
        'stutter': sum(1 for x in auto_selected if x['type'] == 'stutter'),
        'filler': sum(1 for x in auto_selected if x['type'] == 'filler'),
        'repetition': sum(1 for x in auto_selected if x['type'] == 'repetition'),
        'incomplete': sum(1 for x in auto_selected if x['type'] == 'incomplete'),
    }

    print(f"[4/5] 发现 {len(auto_selected)} 个问题:")
    for k, v in stats.items():
        print(f"  - {k}: {v}")

    # 保存结果
    output = {
        'generated_at': datetime.now().isoformat(),
        'segments': segments,
        'auto_selected': auto_selected,
        'silences': silences,
        'stats': stats,
        'rules_used': ['语气词检测', '卡顿词检测', '句内重复检测', '残句检测', '静音检测']
    }

    output_path = f"{output_dir}/auto_selected.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[5/5] 结果已保存: {output_path}")

if __name__ == '__main__':
    main()