# B8：9X 规范化数据校验

从项目根目录运行：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --offline --cache-dir .uv-cache python -m car_knowledge_rag.check_config data/parsed/zeekr/9x-b4-verified.json data/normalized/zeekr/9x-b7-v1
```

命令从 B4 输入按 B7 规则重算预期结果，与字段字典、记录和待核验清单逐项比较。用行列位置识别缺失、意外位置、重复与冲突；字段、数值、单位、状态或脚注不一致时列出有差异的成员。三份文件的来源、输入哈希、列信息、脚注与公告也必须一致。

报告输出 JSON。每个定位到单元格的问题带行号、列号和版本，来源在报告顶层。退出码 0 表示一致，1 表示报告发现问题，2 表示命令参数或 B4 输入不可用。不修改输入，也不删除重复项。

实际验收：277 项字段、1,939 条记录和 124 条待核验项均与基准一致，发现 0 个问题。本地报告为 `data/normalized/zeekr/9x-b7-v1/b8-quality-report.json`，已被 Git 忽略。79 项测试及 11 个子测试通过，1 项既有符号链接测试跳过。

本步检查 B7 产物是否忠实于 B4 和现有规则，不独立证明 B4 或规则本身正确。124 条待核验项仍未确认，关键数字对照原表留给 B9。
