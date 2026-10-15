# CarKnowledgeRAG

个人车辆知识问答 RAG 调研项目。当前完成 A4（最小 Python 环境）和 A5（统一配置读取与校验）。

## 环境

- Python 3.11
- uv（当前安装于项目内 `.tools/uv`，不修改全局环境）

## Windows PowerShell 运行

在项目根目录执行：

```powershell
& .\.tools\uv\bin\uv.exe sync --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag
```

没有外部配置时，预期输出：

```text
CarKnowledgeRAG: Python environment is ready.
Environment: development
Log level: INFO
```

如果已在其他环境安装 uv，可将上述可执行文件路径替换为 `uv`。
同步依赖会在项目根目录创建 `.venv`；配置读取使用 `pydantic-settings`。
提交 `pyproject.toml`、`.python-version` 和 `uv.lock`，不提交工具、缓存和虚拟环境。

## 当前范围

尚未实现官网采集、数据库、模型调用、前端、鉴权或 AWS 部署。

## A5：配置与学习记录

### A5.1 默认值

`car_knowledge_rag/config.py` 的 `Settings` 继承 `BaseSettings`。
启动入口创建 `Settings()` 时，库读取配置、校验取值，然后业务代码通过属性访问。
`Literal` 表示只接受列出的精确值，不自动纠正拼写或大小写。

| 字段 | 环境变量 | 默认值 | 合法值 |
| --- | --- | --- | --- |
| `app_env` | `APP_ENV` | `development` | `development`、`test`、`production` |
| `log_level` | `LOG_LEVEL` | `INFO` | `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` |

日志级别当前只读取和显示，实际日志系统留到 A6。

### A5.2 环境变量

下面的 PowerShell 操作只影响当前终端及其子进程，不修改永久系统配置。
如果原来已有同名变量，请先记录原值，并在实验后恢复。

```powershell
$env:APP_ENV = "production"
$env:LOG_LEVEL = "DEBUG"
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag
```

预期显示 `Environment: production` 和 `Log level: DEBUG`。
若变量是本次实验新建的，结束后移除：

```powershell
Remove-Item Env:APP_ENV, Env:LOG_LEVEL -ErrorAction SilentlyContinue
```

### A5.3 本地 .env

在项目根目录执行，且仅在尚无 `.env` 时复制示例，避免覆盖已有配置：

```powershell
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item -LiteralPath .env.example -Destination .env
}
```

之后用编辑器修改 `.env`。程序读取**当前工作目录**的 `.env`，编码为 UTF-8；
因此本项目命令应从项目根目录运行。文件不存在时可以正常使用默认值。

普通启动不传入配置构造参数时，优先级为：**环境变量 > .env > 默认值**。
例如 `.env` 中为 `LOG_LEVEL=WARNING`，环境变量为 `LOG_LEVEL=ERROR`，最终采用 `ERROR`。
程序不搜索父目录的 `.env`。其他系统环境变量不受配置类限制；
但 `.env` 专供本应用使用，未知字段会报错，以便发现 `LOG_LEVLE` 之类的拼写错误。

`.env.example` 只有可公开示例；`.env` 已被 Git 忽略。忽略规则不能加密文件，
不要提交真实秘密、输出整个配置对象，或将秘密粘贴到日志中。

### A5.4 非法配置

`APP_ENV=prod`、`LOG_LEVEL=debug` 或空字符串都不合法。
非法的高优先级值会报错，不会退回低优先级的合法值。

启动入口捕获 Pydantic 的 `ValidationError`，向标准错误输出字段与原因，退出码为 `2`；
不回显原始配置值，也不输出成功启动消息。直接在 Python 中调用 `Settings()` 时，
仍会抛出 `ValidationError`，由调用者处理。

### A5.5 验收与复习

使用 Python 标准库 `unittest`，无需提前引入 pytest：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m unittest discover -s tests -v
```

测试使用临时目录和临时进程环境，结束后自动恢复；不读取或改写个人 `.env`。
覆盖默认值、环境变量、UTF-8 文件、示例文件、优先级、非法值、未知字段和启动报错。

理解检查：

1. `.env` 为 `INFO`，环境变量为 `DEBUG`，最终使用什么？
2. 环境变量为非法的 `debug` 时，为什么不能自动退回 `.env` 的 `INFO`？
3. 将 `.env.example` 中的值改掉，会直接改变程序行为吗？

答案：1. `DEBUG`；2. 显式报错才能暴露错误配置；3. 不会，程序读取的是 `.env`。
