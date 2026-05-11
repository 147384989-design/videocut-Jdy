# 口播剪辑工具 (videocut)

离线可用的口播视频智能剪辑工具，基于 Whisper + FFmpeg，无需 API Key。

## 功能

| 功能 | 说明 |
|------|------|
| 离线转录 | Whisper base 模型，中文支持 |
| 静音检测 | FFmpeg silencedetect，自动标记长静音 |
| 口误检测 | 语气词、卡顿词、句内重复、残句检测 |
| Phrase 打包 | 将短句合并为完整语义单元 |
| 时间线可视化 | HTML 波形图，辅助审核 |
| 网页审核 | localhost:8899，可视化点击确认 |
| 质量评估 | 剪辑后验证流畅度和压缩率 |
| 字幕生成 | SRT/ASS 格式，支持烧录 |
| 高清导出 | 2-pass 编码 |

## 快速开始

```bash
# 在 WSL 中运行
# 1. 转录 + 审核 + 剪辑（一站式）
/剪口播 /mnt/f/视频/口播.mp4

# 2. 仅转录（检查效果）
/剪口播:转录 视频.mp4

# 3. 生成时间线（可视化浏览）
/剪口播:时间线 视频.mp4

# 4. 质量评估（剪辑后）
/剪口播:评估 output/2026-05-11_口播
```

## 工作流程

```
视频 → 转录(Whisper) → 打包(phrase) → 分析(口误检测)
                                        ↓
                                   时间线可视化
                                        ↓
                                   网页审核
                                        ↓
                                   确认删除
                                        ↓
                                   FFmpeg剪辑
                                        ↓
                                   质量评估 → 完成
```

## 目录结构

```
videocut/
├── SKILL.md                    # Claude Code skills 入口
├── config/settings.json        # 配置文件
├── scripts/
│   ├── transcribe.sh           # 转录入口
│   ├── analyze.py              # AI 分析
│   ├── pack_phrases.py         # Phrase 打包
│   ├── timeline_view.py        # 时间线可视化
│   ├── quality_review.py       # 质量评估
│   ├── project.py              # 项目管理
│   ├── review_server.js        # 审核服务器
│   ├── cut_video.sh            # 剪辑脚本
│   ├── generate_subtitle.py   # 字幕生成
│   ├── burn_subtitle.sh        # 字幕烧录
│   └── hd_export.sh            # 高清导出
├── 用户习惯/                   # 检测规则
│   ├── 语气词检测规则.md
│   ├── 卡顿词规则.md
│   ├── 句内重复检测规则.md
│   └── 残句检测规则.md
└── output/                     # 输出目录
```

## 自动程度

| 类型 | 处理方式 |
|------|---------|
| 静音 >1s | 全自动删除 |
| 静音 0.5-1s | 需确认 |
| 语气词 ≥3次 | 全自动删除 |
| 语气词 2次 | 需确认 |
| 句内重复 | 需确认 |
| 残句 | 全自动删除 |

## 审核网页使用

1. 打开 http://localhost:8899
2. 播放视频，确认问题位置
3. 点击勾选要删除的项目
4. 点击「执行剪辑」
5. 等待完成后查看 `output.mp4`

## 系统要求

- FFmpeg
- Whisper (`pip install openai-whisper`)
- Node.js (审核服务器)
- Python 3.8+

## License

MIT