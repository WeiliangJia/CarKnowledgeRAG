# C8 批量评测运行器

2026-11-17（Australia/Sydney）。运行器读取 C7 的 96 道开发题或 24 道保留测试题。答题函数只接收问题与已有上下文，评分函数结合标准答案、来源及逐题规则判定。输出 JSON 报告，记录题集 SHA-256、逐题回答与判定、总体及各题型通过率和失败原因。[C7 题集说明](C7-9x-evaluation.md)

## 批量运行

在仓库根目录使用 PowerShell 7。把 `my_adapter` 换成实际可导入的 Python 模块，开发时选 `dev`，验收时选 `test`。

```powershell
$env:PYTHONUTF8 = '1'
$python = '.\.venv\Scripts\python.exe'
& $python -m car_knowledge_rag.evaluate --split dev run --answerer my_adapter:answer --judge my_adapter:judge > dev-report.json
& $python -m car_knowledge_rag.evaluate --split test run --answerer my_adapter:answer --judge my_adapter:judge > heldout-report.json
```

- `answer(question, context)` 返回回答文本。单轮题的 `context` 为 `None`。答题函数使用项目收录的 9X 配置表和产品页作为资料范围。
- `judge(case, answer)` 可读取题目的 `expected`、`evidence`、`pass_rule` 等字段，按 C7 规则返回判定。通过时返回 `{"passed": true}`，失败时须提供 `reasons` 数组和写明具体问题的 `detail`。例如 `{"passed": false, "reasons": ["incorrect_value", "missing_citation"], "detail": "只回答了 70 kWh，漏掉原值 55/70 kWh、适用条件和来源。"}`。Python 实现使用 `True` 或 `False`。
- 批量运行遇到单题异常会继续处理其余题。答题异常或非文本输出记为 `answer_error`，评分异常或无效判定记为 `judge_error`。空白回答自动判为 `empty_answer`。

## 汇总人工判定

`prompts` 导出题号、问题及有值时的上下文。收集答复后，按 C7 的预期和规则评阅。将每条评阅保存成一行 JSON，包含 `id`、`answer`、`passed`，失败时补充 `reasons` 和 `detail`。每个题号须恰好出现一次，输入行顺序可以任意。

```powershell
& $python -m car_knowledge_rag.evaluate --split dev prompts > dev-prompts.jsonl
& $python -m car_knowledge_rag.evaluate --split dev score dev-judgments.jsonl > dev-report.json
```

```json
{"id":"Q01","answer":"70 kWh","passed":false,"reasons":["incorrect_value","missing_citation"],"detail":"漏掉官方斜杠原值、适用条件的不确定性和来源。"}
```

| 失败代码 | 计入的情况 |
| --- | --- |
| `incorrect_value` | 数值、单位、属性或配置状态错误 |
| `wrong_version` | 车型或版本错配 |
| `missing_citation` | 引用缺失或不足以支持结论 |
| `missed_clarification` | 遗漏必要的澄清 |
| `wrong_scope` | 测试口径、适用条件或覆盖范围错误 |
| `unsupported_claim` | 回答超出证据、猜测缺值或武断处理冲突 |
| `incomplete_answer` | 漏答要求的项目、筛选对象或条件 |
| `other` | 其他未通过原因，详情记录具体问题 |

## 报告与验收

`results` 按题集顺序输出。`overall` 和 `by_category` 的 `pass_rate` 是通过题数除以该范围内全部题数，含执行错误，取值 0 到 1。`failure_reasons` 按原因分别计数，一题可计入多种原因。`execution_errors` 单独统计运行异常。退出码 0 表示评测流程完成，即使有答错题。退出码 1 表示报告已生成但有执行错误。退出码 2 表示参数、题集或判定文件有误。

验收使用样例答复验证了两套题集的导出、批量运行和人工判定导入，每套均生成八种题型的统计。全量 pytest 通过 89 项和 11 个子测试，1 项既有测试跳过。Ruff 规则和格式检查通过。端到端问答成绩待实际答题和评分组件接入后测量。
