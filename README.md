# CarKnowledgeRAG

个人车辆知识问答 RAG 调研项目。当前仅完成 A4：最小 Python 环境与运行入口。

## 环境

- Python 3.11
- uv（当前安装于项目内 `.tools/uv`，不修改全局环境）

## Windows PowerShell 运行

在项目根目录执行：

```powershell
& .\.tools\uv\bin\uv.exe sync --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag
```

预期输出：

```text
CarKnowledgeRAG: Python environment is ready.
```

如果已在其他环境安装 uv，可将上述可执行文件路径替换为 `uv`。
同步依赖会在项目根目录创建 `.venv`；当前没有第三方运行依赖。
提交 `pyproject.toml`、`.python-version` 和 `uv.lock`，不提交工具、缓存和虚拟环境。

## 当前范围

尚未实现官网采集、数据库、模型调用、前端、鉴权或 AWS 部署。
