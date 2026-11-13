# B9：9X 关键配置原表核验

本轮只核验 9X 已完成 B4–B8 的版本。用 B2 保存的浏览器可见文本作为独立比对路径，不重新使用 B4 的 DOM 单元格提取逻辑。文本哈希取自 B3 清单；版本顺序、原表标签行、数值行及相关脚注行已对照快照定位。先跑 B8，再逐列比较。没有人工签核，也不验证官网声明对应的实车表现。

在项目根目录运行：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --offline --cache-dir .uv-cache python -m car_knowledge_rag.review_9x data/parsed/zeekr/9x-b4-verified.json data/normalized/zeekr/9x-b7-v1 data/raw/zeekr/20261104T061714920392Z-70f8b89f/10/config/text.txt
```

结果输出 JSON，包含来源、版本、单位、原值、文本行号、脚注位置和结论。退出码 1 表示出现差异，2 表示输入或基准错误；0 不代表全部条件已确认。

实际核对 21 行 × 7 列 = 147 项，覆盖尺寸、座位、动力、电池、四种续航口径、充电、加速及后备厢容积。133 项原表一致，2 项条件明确，12 项原文一致但证据不足以给斜杠值分别绑定条件，0 项差异。五座 Ultra 的后备厢两项按脚注 11 记录 H7/H9 对应值，不合并为单值。未修改 B7 的 124 项待核验清单；用户可按行号复查后再决定如何处理。

本地报告：`data/normalized/zeekr/9x-b7-v1/b9-review.json`（Git 忽略）。Ruff 通过；81 项测试、11 个子测试通过，1 项既有符号链接测试跳过。其他 10 个车型尚未通过 B4–B8，未纳入本轮核验。
