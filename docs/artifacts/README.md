# 论文第 6 章本地归档（可选）

本目录用于存放**批跑生成的** CSV、以及复制自 `data/` 的 `experiment_summary_case*.json` 等，供 `enrich_thesis_csv_flaky_score.py`、`thesis_runs_stats.py` 与 `docs/images/gen_thesis_diagrams.py` 使用。

- **仓库内可追溯的小 JSON** 也可放在项目根目录 **`data/experiment_summary_case*.json`**（与 `export_experiment_summary_json.py` 导出一致）。
- 大体积 `thesis_runs*.csv` 默认不提交 Git（见根目录 `.gitignore`）；换机复现实验请将同批文件放回此处或指向 `data/thesis_runs.csv`。
- 当前论文 PNG 统一由 `docs/images/gen_thesis_diagrams.py` 生成到 `docs/images/thesis_diagrams/`。脚本会调用 `scripts/figure_fonts.py` 注册中文字体；若换机后仍出现中文方框，可安装微软雅黑/黑体/Noto Sans CJK，或用环境变量 `THESIS_CJK_FONT` 指向可用的 `.ttf/.ttc/.otf` 字体文件后重跑出图命令。
