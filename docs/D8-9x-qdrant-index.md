# D8 极氪 9X 向量索引

D8 使用 D4 的规则切分和现有 Embedding Key。OpenAI 的 `text-embedding-3-small` 为片段生成 1,536 维向量。Qdrant 使用余弦相似度，每条向量的点 ID 沿用 D4 的 UUID。片段正文、车型和批次、配置版本、来源、原文位置、脚注与核验状态随点保存，车型和版本字段可用于 D9 过滤。[D4 片段格式](D4-9x-chunking.md) · [Qdrant 点写入](https://api.qdrant.tech/api-reference/points/upsert-points)

## 启动 Qdrant

本机采用已校验的 Qdrant 1.20.2 原生 Windows 版。将官方 Windows 压缩包解压到 `.tools/qdrant/1.20.2/`，然后在仓库根目录启动。配置仅监听 `127.0.0.1:6333`，数据和快照保存在本地语料目录。[Qdrant 官方发布包](https://github.com/qdrant/qdrant/releases/tag/v1.20.2)

```powershell
$qdrant = (Resolve-Path '.tools/qdrant/1.20.2/qdrant.exe').Path
$config = (Resolve-Path 'qdrant.local.yaml').Path
$directory = New-Item -ItemType Directory -Path 'data/corpus/qdrant-local' -Force
Push-Location $directory.FullName
try { & $qdrant --config-path $config } finally { Pop-Location }
```

## 建索引与续跑

在另一个位于仓库根目录的 PowerShell 中执行。先指定 `--limit 56` 可试跑文件前 56 条，随后去掉 `--limit` 补齐整个语料。

```powershell
& .\.venv\Scripts\python.exe -m car_knowledge_rag.index_9x data/corpus/9x-d4-chunks.json
```

集合名包含片段文件哈希，集合元数据记录完整文件哈希、模型、维度和预期点数。每次先核对已有 ID 和来源载荷，再分批嵌入缺失片段。写入使用插入模式并等待完成。重复运行时，已确认存在的点会复用。命令输出前后精确点数、剩余点数、嵌入请求数和 token 用量。

## 实测验收

集合 `zeekr_9x_d4_openai_small_1536_57b70b170aeb0e04` 首批写入 56 条，续跑补齐 1,935 条，共 1,991 个独立点。两次入库合计使用 22 次嵌入请求和 194,939 个输入 token。

重启后，精确点数仍为 1,991。再次执行同一条全量入库命令，逐点校验 ID 和来源载荷，新增 0 条，OpenAI 请求数与 token 用量均为 0。抽查第 20 行的五座和六座 Ultra，分别对应第 5、2 列，各有一个 1,536 维向量，并保留原值 `288/380`、出处及证据不足标记。

全量 pytest 通过 104 项和 11 个子测试，1 项既有测试跳过。Ruff 规则和格式检查通过。D9 将用这个索引评估 Top-K 召回质量。
