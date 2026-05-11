#!/usr/bin/env python3
"""
会话持久化模块 - 保存/恢复编辑进度

功能：
1. 将当前项目状态保存到 project.md
2. 记录已确认的删除片段
3. 记录用户修改历史
4. 支持增量更新

输出：project.md（Markdown 格式，便于 Human 阅读）
"""

import json
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# 配置
PROJECT_FILE = "project.md"
METADATA_FILE = "project_meta.json"  # 隐藏的元数据文件


class ProjectManager:
    """项目管理器"""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.project_root / METADATA_FILE
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if self.meta_path.exists():
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'version': '1.0',
            'segments_confirmed': [],
            'segments_rejected': [],
            'deletions_confirmed': [],
            'edits_history': [],
            'review_completed': False
        }

    def _save_metadata(self):
        """保存元数据"""
        self.metadata['updated_at'] = datetime.now().isoformat()
        with open(self.meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

    def init_project(self, video_path: str, whisper_json: str = None):
        """初始化新项目"""
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'version': '1.0',
            'video_path': str(video_path),
            'whisper_json': whisper_json,
            'segments_confirmed': [],
            'segments_rejected': [],
            'deletions_confirmed': [],
            'edits_history': [{
                'action': 'init',
                'timestamp': datetime.now().isoformat(),
                'description': '项目初始化'
            }],
            'review_completed': False
        }
        self._save_metadata()
        self._generate_project_md()

    def _generate_project_md(self):
        """生成 project.md"""
        video_name = Path(self.metadata.get('video_path', 'unknown')).name
        created = self.metadata.get('created_at', '')[:10]

        md = f"""# 口播剪辑项目

## 基本信息

- **视频文件**: {video_name}
- **创建日期**: {created}
- **状态**: {self.get_status_label()}

## 转录统计

| 指标 | 值 |
|------|-----|
| 原始段数 | {len(self.metadata.get('segments_confirmed', []))} |
| 已删除 | {len(self.metadata.get('deletions_confirmed', []))} |
| 已确认保留 | {len(self.metadata.get('segments_confirmed', [])) - len(self.metadata.get('deletions_confirmed', []))} |

## 删除片段（已确认）

"""

        deletions = self.metadata.get('deletions_confirmed', [])
        if deletions:
            md += "| 序号 | 开始 | 结束 | 时长 | 类型 |\n"
            md += "|------|------|------|------|------|\n"
            for i, d in enumerate(deletions, 1):
                start = d.get('start', 0)
                end = d.get('end', 0)
                duration = end - start
                d_type = d.get('type', 'unknown')
                md += f"| {i} | {start:.2f}s | {end:.2f}s | {duration:.1f}s | {d_type} |\n"
        else:
            md += "_暂无确认的删除_\n"

        md += """
## 编辑历史

"""
        for entry in self.metadata.get('edits_history', []):
            time = entry.get('timestamp', '')[:16]
            action = entry.get('action', '')
            desc = entry.get('description', '')
            md += f"- **{time}** [{action}]: {desc}\n"

        md += f"""
## 审核状态

- 审核完成: {'✅ 是' if self.metadata.get('review_completed') else '❌ 否'}
- 质量评分: {self.metadata.get('quality_score', '未评分')}

---
_此文件由口播剪辑工具自动生成_
"""

        project_md = self.project_root / PROJECT_FILE
        with open(project_md, 'w', encoding='utf-8') as f:
            f.write(md)

        return project_md

    def confirm_deletion(self, start: float, end: float, delete_type: str = 'manual'):
        """确认删除一个片段"""
        deletion = {
            'start': start,
            'end': end,
            'type': delete_type,
            'timestamp': datetime.now().isoformat()
        }
        self.metadata['deletions_confirmed'].append(deletion)
        self._add_history('delete', f'确认删除 {start:.2f}s - {end:.2f}s ({delete_type})')
        self._save_metadata()
        self._generate_project_md()

    def reject_deletion(self, problem_id: str, reason: str = None):
        """拒绝删除（保留此片段）"""
        self.metadata['segments_rejected'].append({
            'id': problem_id,
            'reason': reason,
            'timestamp': datetime.now().isoformat()
        })
        self._add_history('reject', f'拒绝删除 {problem_id}: {reason or "用户选择保留"}')
        self._save_metadata()
        self._generate_project_md()

    def mark_review_complete(self, quality_score: float = None):
        """标记审核完成"""
        self.metadata['review_completed'] = True
        if quality_score:
            self.metadata['quality_score'] = quality_score
        self._add_history('review_complete', f'审核完成，质量评分: {quality_score or "N/A"}')
        self._save_metadata()
        self._generate_project_md()

    def get_confirmed_deletions(self) -> List[Dict]:
        """获取已确认的删除列表"""
        return self.metadata.get('deletions_confirmed', [])

    def _add_history(self, action: str, description: str):
        """添加编辑历史"""
        self.metadata['edits_history'].append({
            'action': action,
            'timestamp': datetime.now().isoformat(),
            'description': description
        })

    def get_status_label(self) -> str:
        """获取状态标签"""
        if self.metadata.get('review_completed'):
            return "✅ 已完成"
        deletions = len(self.metadata.get('deletions_confirmed', []))
        rejected = len(self.metadata.get('segments_rejected', []))
        if deletions > 0:
            return f"🔄 审核中 ({deletions} 已删)"
        if rejected > 0:
            return f"🔄 审核中 ({rejected} 已保留)"
        return "📋 待审核"

    def load_from_project(self) -> bool:
        """从已存在的 project.md 加载"""
        if not self.meta_path.exists():
            return False
        return True

    def export_final_segments(self, original_segments: List[Dict]) -> List[Dict]:
        """导出最终保留的片段（用于剪辑）"""
        deletions = self.metadata.get('deletions_confirmed', [])

        if not deletions:
            return original_segments

        # 转换为时间区间
        del_ranges = [(d['start'], d['end']) for d in deletions]
        del_ranges.sort(key=lambda x: x[0])

        kept_segments = []
        current_time = 0.0

        for start, end in del_ranges:
            if start > current_time:
                kept_segments.append({
                    'start': current_time,
                    'end': start
                })
            current_time = max(current_time, end)

        # 添加最后一个保留段
        if original_segments:
            last_end = original_segments[-1].get('end', 0)
            if current_time < last_end:
                kept_segments.append({
                    'start': current_time,
                    'end': last_end
                })

        return kept_segments


def create_project(project_dir: str, video_path: str, whisper_json: str = None) -> ProjectManager:
    """创建新项目"""
    pm = ProjectManager(project_dir)
    pm.init_project(video_path, whisper_json)
    return pm


def load_project(project_dir: str) -> Optional[ProjectManager]:
    """加载已有项目"""
    pm = ProjectManager(project_dir)
    if pm.load_from_project():
        return pm
    return None


def main():
    if len(sys.argv) < 3:
        print("用法:")
        print("  创建项目: python3 project.py create <项目目录> <视频路径>")
        print("  确认删除: python3 project.py delete <项目目录> <start> <end> [type]")
        print("  标记完成: python3 project.py complete <项目目录> [quality_score]")
        print("  导出: python3 project.py export <项目目录>")
        sys.exit(1)

    command = sys.argv[1]
    project_dir = sys.argv[2]

    if command == 'create':
        video_path = sys.argv[3] if len(sys.argv) > 3 else ''
        pm = create_project(project_dir, video_path)
        print(f"项目已创建: {project_dir}")
        print(f"视频: {video_path}")

    elif command == 'delete':
        start = float(sys.argv[3])
        end = float(sys.argv[4])
        delete_type = sys.argv[5] if len(sys.argv) > 5 else 'manual'
        pm = load_project(project_dir)
        if pm:
            pm.confirm_deletion(start, end, delete_type)
            print(f"已确认删除: {start}s - {end}s")
        else:
            print("错误: 项目不存在")

    elif command == 'complete':
        score = float(sys.argv[3]) if len(sys.argv) > 3 else None
        pm = load_project(project_dir)
        if pm:
            pm.mark_review_complete(score)
            print("审核完成")
        else:
            print("错误: 项目不存在")

    elif command == 'export':
        pm = load_project(project_dir)
        if pm:
            print(json.dumps(pm.get_confirmed_deletions(), indent=2))
        else:
            print("错误: 项目不存在")

    else:
        print(f"未知命令: {command}")


if __name__ == '__main__':
    main()