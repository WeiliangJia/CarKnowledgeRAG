# D10 极氪 9X 带引用问答

2026 年 11 月 26 日（Australia/Sydney）。本步接通 9X 单题问答和分阶段计量，使用已经入库的 D8 语料与 D9 检索规则。[D8 建索引](D8-9x-qdrant-index.md) · [D9 检索基线](D9-9x-retrieval-baseline.md)

## 运行

启动本机 Qdrant 并保留 D4 片段文件。命令从 `.env.openai` 或同名环境变量读取 `OPENAI_EMBED_API_KEY` 和 `OPENAI_ANSWER_API_KEY`。

```powershell
& .\.venv\Scripts\python.exe -m car_knowledge_rag.answer_9x '极氪 9X 六座 Ultra 的 CLTC 纯电续航是多少？'
& .\.venv\Scripts\python.exe -m car_knowledge_rag.answer_9x '纯电续航是多少？' --context '极氪 9X 六座 Ultra'
```

命令在调用 OpenAI 前核对本地片段和 Qdrant 集合。它用问题嵌入执行 Top-10 精确检索。问题明示单一五座或六座 Ultra 时沿用版本过滤。出现配置状态符号时，会补充同一快照的配置图例，方便核对标配、选装和无该配置。回答请求只发送问题、已有上下文和本次证据文本。

输出为 UTF-8 JSON。`answer` 给出可读答案，`claims` 逐条附上官网 URL、片段 ID、配置表行列或产品页行号及原文摘录。程序按本地文本核对摘录，并检查回答中的数字是否出现在所引片段中。无效引用会使该次命令失败。状态有 `answered`、`needs_clarification` 和 `insufficient_evidence`。证据只够回答一部分时，输出已证实的内容和资料不足提示。

## 用量和耗时

| 字段 | 统计范围 |
| --- | --- |
| `api_usage.question_embedding` | 本题使用的 `text-embedding-3-small` 请求数、token、耗时及请求 ID |
| `api_usage.answer_generation` | 回答专用 Key 的 `gpt-6-luna` 请求数、输入和输出 token、耗时及请求 ID |
| `api_usage.chunking` | 本题辅助切分请求数为 0。离线辅助切分另见 [D7 试验](D7-9x-openai-pilot.md) |
| `api_usage.document_embedding` | 本题文档嵌入请求数为 0。离线建索引用量另见 [D8 入库](D8-9x-qdrant-index.md) |
| `timing_ms.qdrant_search` | 本题 Qdrant 查询耗时 |
| `timing_ms.total` | 从接收问题到完成答案和引用校验的耗时。索引启动校验在计时前执行 |

## 线上验收

| 样例 | 观察结果 | 问题嵌入 token | 生成输入 / 输出 token | 嵌入 / 检索 / 生成 / 总耗时（ms） |
| --- | --- | ---: | ---: | --- |
| 六座 Ultra 的 CLTC 纯电续航 | 保留 `288/380 km`，说明各值条件未明，引用 S1 第 20 行第 2 列 | 36 | 1,339 / 107 | 2,363.8 / 23.4 / 3,376.7 / 5,767.6 |
| 闭式双腔空气悬架的最大调节行程 | 回答 110 mm，引用 S2 产品页原文 | 39 | 1,389 / 72 | 461.0 / 5.4 / 1,586.9 / 2,056.6 |
| 未注明座位的 Ultra 纯电续航 | 提示确认五座或六座 | 23 | 1,573 / 19 | 311.3 / 15.7 / 1,547.2 / 1,877.2 |
| 车载冰箱压缩机的供应商和零件编号 | 引用现有冰箱配置并说明证据不足 | 36 | 1,168 / 89 | 373.8 / 3.1 / 1,528.8 / 1,908.9 |

四题共使用 4 次问题嵌入（134 输入 token）和 4 次回答生成（5,469 输入、287 输出 token）。逐题报告保存在本地 `data/corpus/9x-d10-*.json`。本次验证单题链路及引用检查，整体答案正确率和引用语义支持度留给后续问答评测。

本地 pytest 通过 120 项和 11 个子测试，1 项因环境无法创建符号链接而跳过。Ruff 规则和格式检查通过。
