#!/usr/bin/env python3
"""
Phrase 打包模块 - 将 Whisper 短句合并为完整语义单元

原版 video-use 的核心思想：Whisper 按音频切片输出，字级时间戳但语义不完整。
需要按"语义相关性"打包成更长的 phrase，便于 AI 理解和剪辑决策。

打包策略：
1. 标点边界：句号/问号/感叹号 → 断句
2. 语义连贯：相同话题/无明显停顿 → 合并
3. 时长限制：最长不超过 30 秒
4. 静音打断：静音 > 0.8s → 断句

输出格式：合并后的 phrase 列表，包含时间范围和完整文本
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
import re

# 配置
MAX_PHRASE_DURATION = 30.0  # 最大时长（秒）
MIN_PAUSE_DURATION = 0.8    # 静音打断阈值
PUNCTUATION_BREAKS = ['。', '？', '！', '；', '…']  # 标点断句


def load_whisper_result(json_path: str) -> Dict:
    """加载 Whisper 结果"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_word_timestamps(segment: Dict) -> List[Dict]:
    """提取段落中的字级时间戳"""
    words = segment.get('words', [])
    if not words and 'word' in segment:
        # 某些 Whisper 版本用 'word' 而不是 'words'
        words = [{'word': w, 'start': segment['start'] + i * 0.05, 'end': segment['start'] + (i+1) * 0.05}
                 for i, w in enumerate(segment.get('word', '').split())]

    # 兼容没有 word 级别的情况
    if not words:
        words = [{'word': segment['text'], 'start': segment['start'], 'end': segment['end']}]

    return words


def is_punctuation_end(text: str) -> bool:
    """检查文本是否以标点结尾"""
    text = text.strip()
    if not text:
        return False
    return any(text[-1] in p for p in PUNCTUATION_BREAKS)


def should_break(seg1: Dict, seg2: Dict, silences: List[Dict] = None) -> Tuple[bool, str]:
    """
    判断两个段之间是否应该断开

    返回: (should_break, reason)
    """
    gap = seg2['start'] - seg1['end']
    text1 = seg1['text'].strip()
    text2 = seg2['text'].strip()

    # 1. 时间间隙检查（静音打断）
    if silences:
        for s in silences:
            if s['start'] >= seg1['end'] and s['end'] <= seg2['start']:
                if s.get('duration', 0) >= MIN_PAUSE_DURATION:
                    return True, f"静音打断 {s['duration']:.1f}s"

    # 2. 时间过长
    if gap >= MIN_PAUSE_DURATION:
        return True, f"间隔 {gap:.1f}s"

    # 3. 前句以标点结尾
    if is_punctuation_end(text1):
        return True, "前句以标点结尾"

    # 4. 后句是新的开始（连词开头）
    new_starts = ['然后', '但是', '因为', '所以', '如果', '虽然', '而且', '或者', '不过', '于是', '于是乎']
    for start in new_starts:
        if text2.startswith(start) and len(text1) > 5:
            return True, f"话题转换（{start}...）"

    # 5. 时长超限
    combined_duration = seg2['end'] - seg1['start']
    if combined_duration >= MAX_PHRASE_DURATION:
        return True, f"时长超限 {combined_duration:.1f}s"

    return False, ""


def pack_phrases(segments: List[Dict], silences: List[Dict] = None) -> List[Dict]:
    """
    将 Whisper 段落打包为完整语义单元

    Args:
        segments: Whisper 输出的 segments 列表
        silences: 静音段列表（可选）

    Returns:
        打包后的 phrase 列表
    """
    if not segments:
        return []

    phrases = []
    current_phrase = {
        'start': segments[0]['start'],
        'end': segments[0]['end'],
        'text': segments[0]['text'].strip(),
        'segments_idx': [0],
        'word_count': len(segments[0].get('words', [])) if segments[0].get('words') else 0
    }

    for i in range(1, len(segments)):
        seg = segments[i]
        break_now, reason = should_break(current_phrase, seg, silences)

        if break_now:
            # 保存当前 phrase
            current_phrase['duration'] = current_phrase['end'] - current_phrase['start']
            current_phrase['word_count'] = count_words(current_phrase['text'])
            phrases.append(current_phrase)

            # 开始新 phrase
            current_phrase = {
                'start': seg['start'],
                'end': seg['end'],
                'text': seg['text'].strip(),
                'segments_idx': [i],
                'word_count': len(seg.get('words', [])) if seg.get('words') else 0
            }
        else:
            # 合并到当前 phrase
            current_phrase['end'] = seg['end']
            current_phrase['text'] += seg['text']
            current_phrase['segments_idx'].append(i)
            if seg.get('words'):
                current_phrase['word_count'] += len(seg['words'])

    # 保存最后一个 phrase
    if current_phrase['text']:
        current_phrase['duration'] = current_phrase['end'] - current_phrase['start']
        current_phrase['word_count'] = count_words(current_phrase['text'])
        phrases.append(current_phrase)

    return phrases


def count_words(text: str) -> int:
    """统计字数（中文按字，英文按词）"""
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    return chinese_chars + english_words


def split_by_punctuation(text: str) -> List[str]:
    """按标点分割文本（保留标点）"""
    parts = []
    current = ""
    for char in text:
        current += char
        if char in PUNCTUATION_BREAKS:
            parts.append(current)
            current = ""
    if current.strip():
        parts.append(current)
    return [p for p in parts if p.strip()]


def enhance_phrases(phrases: List[Dict]) -> List[Dict]:
    """
    增强 phrase 信息：添加句子边界、情感标记等
    """
    enhanced = []
    for phrase in phrases:
        e = phrase.copy()

        # 检测句子边界（用于审核UI）
        sentences = split_by_punctuation(e['text'])
        e['sentences'] = [s.strip() for s in sentences if s.strip()]

        # 检测是否有语气词/卡顿词
        filler_count = count_filler_words(e['text'])
        e['filler_count'] = filler_count
        e['has_issue'] = filler_count > 0

        # 计算信息密度（字数/时长）
        duration = e.get('duration', 1)
        word_count = e.get('word_count', count_words(e['text']))
        e['density'] = word_count / duration if duration > 0 else 0

        enhanced.append(e)

    return enhanced


FILLER_WORDS = ['嗯', '啊', '呃', '哦', '呀', '哇', '嘛', '呢', '啦', '呐',
                '这个', '那个', '就是', '就是说']


def count_filler_words(text: str) -> int:
    """统计语气词出现次数"""
    count = 0
    text_lower = text.lower()
    for fw in FILLER_WORDS:
        count += text.count(fw)
    return count


def main():
    if len(sys.argv) < 3:
        print("用法: python3 pack_phrases.py <whisper_result.json> <silence.txt> [output.json]")
        print("")
        print("  输入:")
        print("    whisper_result.json  - Whisper 转录结果")
        print("    silence.txt          - FFmpeg 静音检测输出（可选）")
        print("")
        print("  输出:")
        print("    phrases.json         - 打包后的语义单元列表")
        sys.exit(1)

    whisper_json = sys.argv[1]
    silence_txt = sys.argv[2] if len(sys.argv) > 2 else None
    output_path = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"加载转录: {whisper_json}")
    data = load_whisper_result(whisper_json)
    segments = data.get('segments', [])

    # 加载静音信息
    silences = []
    if silence_txt and Path(silence_txt).exists():
        print(f"加载静音: {silence_txt}")
        with open(silence_txt, 'r') as f:
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

    print(f"Whisper 段落: {len(segments)}")
    print(f"静音段: {len(silences)}")
    print("打包 phrase...")

    phrases = pack_phrases(segments, silences)
    phrases = enhance_phrases(phrases)

    print(f"打包完成: {len(phrases)} phrases")

    # 统计
    total_duration = sum(p.get('duration', 0) for p in phrases)
    avg_duration = total_duration / len(phrases) if phrases else 0
    print(f"  总时长: {total_duration:.1f}s")
    print(f"  平均时长: {avg_duration:.1f}s")
    print(f"  字数: {sum(p.get('word_count', 0) for p in phrases)}")

    # 保存
    output = {
        'generated_at': None,  # 填充时间
        'total_segments': len(segments),
        'total_phrases': len(phrases),
        'total_duration': total_duration,
        'avg_phrase_duration': avg_duration,
        'phrases': phrases
    }

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"已保存: {output_path}")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return phrases


if __name__ == '__main__':
    main()