#!/usr/bin/env python3
"""
自我评估模块 - 验证剪辑质量

在完成剪辑后运行，评估：
1. 剪辑前后时长对比
2. 剩余问题检测（漏检）
3. 流畅度评估（句子连贯性）
4. 生成质量报告

输出：quality_report.json + 评估结论
"""

import json
import sys
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime

# 语气词/卡顿词检测（与 analyze.py 保持一致）
FILLER_WORDS = ['嗯', '啊', '呃', '哦', '呀', '哇', '嘛', '呢', '啦', '呐',
                '这个', '那个', '就是', '就是说', '然后', '其实', '的话']

STUTTER_PATTERNS = [
    (r'那个那个+', '那个'),
    (r'这个这个+', '这个'),
    (r'就是就是+', '就是'),
    (r'的话的话+', '的话'),
    (r'对对对+', '对'),
    (r'不不不+', '不'),
]


class QualityReviewer:
    """质量评估器"""

    def __init__(self):
        self.issues = []

    def check_filler_words(self, text: str) -> List[Dict]:
        """检测语气词"""
        findings = []
        for fw in FILLER_WORDS:
            count = text.count(fw)
            if count >= 2:
                findings.append({
                    'type': 'filler',
                    'word': fw,
                    'count': count,
                    'severity': 'high' if count >= 3 else 'medium'
                })
        return findings

    def check_stutters(self, text: str) -> List[Dict]:
        """检测卡顿词"""
        findings = []
        for pattern, _ in STUTTER_PATTERNS:
            matches = re.findall(pattern, text)
            if matches:
                findings.append({
                    'type': 'stutter',
                    'pattern': pattern,
                    'count': len(matches),
                    'severity': 'high'
                })
        return findings

    def check_incomplete_sentence(self, text: str) -> Optional[Dict]:
        """检测不完整句子"""
        # 以连词开头
        if re.match(r'^(然后|但是|因为|所以|如果|虽然|而且|或者)', text):
            return {'type': 'incomplete', 'reason': '以连词开头', 'severity': 'medium'}
        # 句子太短
        if len(text) < 5 and re.match(r'^(关于|这个|那个|对于)', text):
            return {'type': 'incomplete', 'reason': '简短残句', 'severity': 'medium'}
        return None

    def check_sentence_coherence(self, sentences: List[str]) -> List[Dict]:
        """检查句子连贯性"""
        issues = []
        for i in range(len(sentences) - 1):
            curr = sentences[i].strip()
            next_s = sentences[i + 1].strip()

            if not curr or not next_s:
                continue

            # 检查衔接词是否突兀
            new_starts = ['然后', '但是', '因为', '所以', '如果', '虽然', '而且', '或者']
            for start in new_starts:
                if next_s.startswith(start) and len(curr) > 10:
                    # 检查是否有静音间隔标记（用句号/逗号判断）
                    if not curr.endswith(('。', '？', '！', '，', '；')):
                        issues.append({
                            'type': 'coherence',
                            'reason': f'句子连接突兀（衔接词：{start}）',
                            'severity': 'low',
                            'position': i
                        })
        return issues

    def analyze_text(self, text: str) -> Dict:
        """全面分析文本质量"""
        result = {
            'filler_words': self.check_filler_words(text),
            'stutters': self.check_stutters(text),
            'incomplete': self.check_incomplete_sentence(text),
            'sentences': self.split_sentences(text),
        }

        result['coherence'] = self.check_sentence_coherence(result['sentences'])

        return result

    def split_sentences(self, text: str) -> List[str]:
        """按标点分割句子"""
        parts = []
        current = ""
        for char in text:
            current += char
            if char in '。？！；':
                parts.append(current)
                current = ""
        if current.strip():
            parts.append(current)
        return [p for p in parts if p.strip()]


def load_transcript(json_path: str) -> List[Dict]:
    """加载转录数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('segments', data)


def load_deletion_json(json_path: str) -> List[Tuple[float, float]]:
    """加载删除片段列表"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    deletions = []
    for item in data:
        if isinstance(item, dict):
            if 'to_delete' in item:
                for d in item['to_delete']:
                    deletions.append((d['start'], d['end']))
            elif 'start' in item and 'end' in item:
                deletions.append((item['start'], item['end']))

    return deletions


def calculate_kept_segments(
    segments: List[Dict],
    deletions: List[Tuple[float, float]]
) -> List[Dict]:
    """计算保留的片段"""
    if not deletions:
        return segments

    # 按开始时间排序删除片段
    deletions = sorted(deletions, key=lambda x: x[0])

    kept = []
    current_time = 0.0

    for del_start, del_end in deletions:
        # 跳过已删除的时间
        if del_start > current_time:
            kept.append({
                'start': current_time,
                'end': del_start,
                'deleted': False
            })
        current_time = max(current_time, del_end)

    # 添加最后一个保留段
    if current_time < (segments[-1]['end'] if segments else 0):
        kept.append({
            'start': current_time,
            'end': segments[-1]['end'] if segments else current_time,
            'deleted': False
        })

    return kept


def assess_quality(
    original_segments: List[Dict],
    deleted_segments: List[Tuple[float, float]],
    edited_text: str
) -> Dict:
    """
    评估剪辑质量

    Args:
        original_segments: 原始转录段落
        deleted_segments: 删除的片段列表
        edited_text: 编辑后的文本

    Returns:
        质量报告
    """
    reviewer = QualityReviewer()

    # 1. 时长对比
    original_duration = 0
    for seg in original_segments:
        original_duration += seg.get('end', 0) - seg.get('start', 0)

    deleted_duration = sum(end - start for start, end in deleted_segments)
    edited_duration = original_duration - deleted_duration

    # 2. 统计删除
    silence_deletes = sum(1 for d in deleted_segments if d[1] - d[0] >= 1.0)
    filler_deletes = len(deleted_segments) - silence_deletes

    # 3. 文本质量分析
    text_issues = reviewer.analyze_text(edited_text)

    # 4. 流畅度评分（1-10）
    coherence_issues = len(text_issues.get('coherence', []))
    filler_count = sum(f.get('count', 0) for f in text_issues.get('filler_words', []))
    stutter_count = sum(s.get('count', 0) for s in text_issues.get('stutters', []))

    # 计算流畅度得分
    fluency_score = 10
    fluency_score -= min(filler_count * 0.5, 3)  # 语气词扣分
    fluency_score -= min(stutter_count * 1.0, 3)  # 卡顿词扣分
    fluency_score -= min(coherence_issues * 0.5, 2)  # 连贯性扣分

    # 5. 压缩率评估
    compression_ratio = edited_duration / original_duration if original_duration > 0 else 1
    compression_score = 10
    if compression_ratio < 0.5:
        compression_score = 5  # 删除过多
    elif compression_ratio > 0.95:
        compression_score = 7  # 删除不足
    else:
        compression_score = 10 - abs(0.75 - compression_ratio) * 10

    # 6. 综合评分
    overall_score = (fluency_score * 0.5 + compression_score * 0.3 +
                    (10 - len(text_issues.get('incomplete', [])) * 2) * 0.2)

    # 7. 评估结论
    if overall_score >= 9:
        verdict = "优秀 - 剪辑自然流畅"
    elif overall_score >= 7:
        verdict = "良好 - 有小幅改进空间"
    elif overall_score >= 5:
        verdict = "一般 - 建议人工复核"
    else:
        verdict = "较差 - 建议重新剪辑"

    report = {
        'generated_at': datetime.now().isoformat(),

        # 时长统计
        'original_duration': round(original_duration, 1),
        'edited_duration': round(edited_duration, 1),
        'deleted_duration': round(deleted_duration, 1),
        'compression_ratio': round(compression_ratio, 2),

        # 删除统计
        'total_deletions': len(deleted_segments),
        'silence_deletions': silence_deletes,
        'filler_deletions': filler_deletes,

        # 文本质量
        'remaining_fillers': filler_count,
        'remaining_stutters': stutter_count,
        'coherence_issues': coherence_issues,
        'incomplete_sentences': 1 if text_issues.get('incomplete') else 0,

        # 评分
        'fluency_score': round(fluency_score, 1),
        'compression_score': round(compression_score, 1),
        'overall_score': round(overall_score, 1),

        # 结论
        'verdict': verdict,

        # 建议
        'suggestions': []
    }

    # 添加建议
    if filler_count > 3:
        report['suggestions'].append(f"仍存在 {filler_count} 处语气词，建议手动清理")
    if stutter_count > 0:
        report['suggestions'].append(f"存在 {stutter_count} 处卡顿词重复")
    if coherence_issues > 2:
        report['suggestions'].append("句子连贯性有问题，检查是否有字幕错位")
    if compression_ratio < 0.5:
        report['suggestions'].append("删除比例过高（>50%），可能影响内容完整性")
    if text_issues.get('incomplete'):
        report['suggestions'].append("存在残句，可能需要补充上下文")

    return report


def generate_report(report: Dict, output_path: str):
    """生成质量报告"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def print_report(report: Dict):
    """打印报告摘要"""
    print("=" * 50)
    print("剪辑质量评估报告")
    print("=" * 50)
    print(f"综合评分: {report['overall_score']}/10")
    print(f"结论: {report['verdict']}")
    print()
    print("--- 时长统计 ---")
    print(f"原始: {report['original_duration']}s")
    print(f"剪辑后: {report['edited_duration']}s")
    print(f"删除: {report['deleted_duration']}s ({report['compression_ratio']*100:.0f}%)")
    print()
    print("--- 剩余问题 ---")
    print(f"语气词: {report['remaining_fillers']}")
    print(f"卡顿词: {report['remaining_stutters']}")
    print(f"连贯性问题: {report['coherence_issues']}")
    print()
    if report['suggestions']:
        print("--- 建议 ---")
        for s in report['suggestions']:
            print(f"  • {s}")


def main():
    if len(sys.argv) < 4:
        print("用法: python3 quality_review.py <original_whisper.json> <deleted_segments.json> <edited_text.txt> [output.json]")
        print("")
        print("  输入:")
        print("    original_whisper.json  - 原始 Whisper 转录结果")
        print("    deleted_segments.json - 删除片段列表 (from analyze.py)")
        print("    edited_text.txt        - 编辑后的完整文本（纯文本）")
        print("  输出:")
        print("    quality_report.json    - 质量报告")
        sys.exit(1)

    whisper_json = sys.argv[1]
    deleted_json = sys.argv[2]
    edited_text_file = sys.argv[3]
    output_path = sys.argv[4] if len(sys.argv) > 4 else None

    # 加载数据
    segments = load_transcript(whisper_json)
    deletions = load_deletion_json(deleted_json)

    with open(edited_text_file, 'r', encoding='utf-8') as f:
        edited_text = f.read()

    print("评估剪辑质量...")

    # 评估
    report = assess_quality(segments, deletions, edited_text)

    # 输出
    if output_path:
        generate_report(report, output_path)
        print(f"报告已保存: {output_path}")

    print_report(report)


if __name__ == '__main__':
    main()