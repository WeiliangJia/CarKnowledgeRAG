# D6 OpenAI 文本模型接入

在仓库根目录运行验收命令。模块从 `.env.openai` 读取 Key，同名环境变量优先。单独测试一个阶段时只需对应的 Key。项目使用标准库 HTTPS 连接官方 API。

```powershell
& .\.venv\Scripts\python.exe -m car_knowledge_rag.openai_models both
```

可将 `both` 改成 `embedding` 或 `chunking` 单独验证。验收入口使用合成文字，输出模型、token 数、耗时和请求 ID。Embedding 应返回两个 1,536 维向量，切分样例应返回第 1–2 行、第 3 行两个区间。 [OpenAI Embedding 接口](https://developers.openai.com/api/reference/resources/embeddings/methods/create) · [结构化输出文档](https://developers.openai.com/api/docs/guides/structured-outputs)

| 接口 | 环境变量 | 输入和返回 |
| --- | --- | --- |
| `embed(texts)` | `OPENAI_EMBED_API_KEY` | 字符串或字符串序列。使用 `text-embedding-3-small`，返回按输入顺序排列的 1,536 维向量和调用统计。 |
| `chunk_lines(lines)` | `OPENAI_CHUNK_API_KEY` | 原文逐行字符串。使用 `gpt-6-luna` 返回 1 基闭区间，校验连续覆盖后，从本地输入拼回原文并返回调用统计。 |

`chunk_lines` 的行号对应传入序列中的位置。用在 D4 产品页时，由调用方按位置回查原有的来源行号和元数据。配置表仍可沿用 D4 的行列切分。两条接口遇到不可用响应会抛出 `OpenAIError`，错误信息包含可用的 HTTP 状态、错误代码或请求 ID。

线上验收中，Embedding 返回两个 1,536 维向量，使用 32 个输入 token。Luna 返回第 1–2 行与第 3 行两个区间，使用 191 个输入、34 个输出 token。离线 pytest 通过 100 项和 11 个子测试，1 项既有测试跳过。Ruff 规则与格式检查通过。
