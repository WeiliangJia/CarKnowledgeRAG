# CarKnowledgeRAG

个人车辆知识问答 RAG 调研项目。阶段 A 工程基础与 A8 文档整理已完成；车辆 RAG 业务尚未实现。

## 数据来源调查

B1 已完成：[2026-11-04 极氪中国官网清单与报告](docs/B1-sources.md)，
核实 11 个车型入口、35 个基础配置列；[JSON 来源登记表](data/sources/zeekr-2026-11-04.json)。
B2 已完成：[原始资料采集命令与结果](docs/B2-collection.md)。22 个基础 URL 及 2 条 8X 详情已保存至本地 `data/raw/`。
原始资料不提交 Git；尚未解析、规范化或核验为可问答的配置数据集。

B3.1 已完成：[SHA-256 与单文件登记解说](docs/B3.1-file-hash.md)，提供只读的单文件指纹函数。
B3.2 已完成：[回执与批量清单解说及结果](docs/B3.2-manifest.md)，已登记116个文件并报告5组精确重复。
生成清单保存在本地 `data/manifests/`，不提交 Git。
B3.3 已完成：[清单校验命令与验收](docs/B3.3-verification.md)，用旧清单检测文件缺失与内容变化。
B4 已完成：[9X 配置表解析与验收](docs/B4-config-parsing.md)，本地生成结构化 JSON，尚未扩展至其他车型。
B5 当前不适用：[官方 PDF 样本复核](docs/B5-pdf-review.md)，未找到需要补充解析的适用样本。
B6 当前不适用：[配置图片样本复核](docs/B6-ocr-review.md)，现有配置表未发现必须用 OCR 获取的值。
B7 已完成：[9X 首版字段字典、规范化和待核验清单](docs/B7-normalization.md)，生成结果仅保存在本地。
B8 已完成：[9X 数据质量检查](docs/B8-quality-check.md)，规范化记录与 B4 基准一致，124 条仍待核验。

## 架构文档

- [A8.1 架构说明](docs/architecture.md)：当前实现、目标数据流、问答路径与 AWS 部署边界。
- [A8.1 结果报告](docs/A8.1-report.md)：本步产物、检查范围和验收结果。
- [A8.2 技术决策记录](docs/technical-decisions.md)：选择原因、替代方案、代价与验证条件。
- [任务与学习进度](docs/progress.md)：阶段 A 证据、后续路线及 20 个种子问题。
- [学习记录模板](docs/learning-record-template.md)：每步解说、实现、验证与理解记录。
- [参数实验模板](docs/experiment-record-template.md)：每轮假设、参数、指标及回退记录。
- [A8.3/A8.4 与阶段 A 验收报告](docs/A8-report.md)：本次实测结果和后续边界。

架构中的业务与云组件是后续计划，不代表已完成部署。

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
2026-10-22T00:00:00Z INFO car_knowledge_rag Application started environment=development
```

时间为示例，实际使用启动时的 UTC 时间；日志输出到标准错误流。
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

`LOG_LEVEL` 已读取和校验，并由 A6.2 接入日志系统，控制应用日志输出门槛。

### A5.2 环境变量

下面的 PowerShell 操作只影响当前终端及其子进程，不修改永久系统配置。
如果原来已有同名变量，请先记录原值，并在实验后恢复。

```powershell
$env:APP_ENV = "production"
$env:LOG_LEVEL = "DEBUG"
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag
```

预期启动日志包含 `environment=production`。设置 DEBUG 允许输出 DEBUG 及更高级别，
但不会把原本 INFO 的启动事件改成 DEBUG，也不会自动创造额外调试事件。
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

## A6.1：最小日志

`logging_config.py` 使用 Python 标准库，无新增依赖：

- Logger：`logging.getLogger("car_knowledge_rag")`，业务代码用它发出事件。
- Handler：`StreamHandler` 将事件写入标准错误流；此处的 stderr 是输出通道，不代表所有日志都是错误。
- Formatter：将事件排成 UTC 时间、级别、日志器名称和消息。

`UTCFormatter.converter = time.gmtime` 让时间转换使用 UTC，格式末尾的 `Z` 表示 UTC。
`dictConfig` 统一装配组件；`propagate=False` 防止应用日志继续传给根日志器。
启动入口先校验配置，再初始化日志，最后通过 `logger.info` 记录启动事件。
消息使用 `%s` 参数化传值；只记录允许公开的环境名称，不打印整个配置对象。

最初 A6.1 固定 INFO；A6.2 接入配置。当前不写日志文件、不接入 CloudWatch，也不实现请求标识。
异常日志独立示例见 A6.3。
测试验证启动事件、UTC 时间格式和实际 stderr 输出。

理解检查：为什么正常启动的 INFO 日志也会出现在 stderr 中？
答案：Handler 选择输出通道，事件是否严重则由 level 表示，两者是不同概念。

## A6.2：级别与重复初始化

启动入口调用 `configure_logging(settings.log_level)`。
函数把级别交给应用 Logger；合法值已由 `Settings` 校验，底层函数不重复实现另一套校验。
不传参数的直接调用仍默认 INFO。

| LOG_LEVEL | 允许输出 |
| --- | --- |
| DEBUG | DEBUG、INFO、WARNING、ERROR、CRITICAL |
| INFO | INFO、WARNING、ERROR、CRITICAL |
| WARNING | WARNING、ERROR、CRITICAL |
| ERROR | ERROR、CRITICAL |
| CRITICAL | CRITICAL |

级别是门槛，不会改变事件本身的级别。将 `LOG_LEVEL` 设置为 ERROR 后，
程序正常启动也可能没有输出，因为启动事件是 INFO；退出码仍为 0。
修改 `.env` 或环境变量后，需要重新启动，当前没有配置热加载。

重复调用 `dictConfig` 时会替换应用的 Handler，而非不断追加；
`propagate=False` 阻止应用日志再经根 Logger 输出一次。
后续使用 `logging.getLogger("car_knowledge_rag.retrieval")` 等子日志器时，
默认继承应用级别与 Handler，不要为每个业务模块重复安装 Handler。

测试通过独立子进程验证五个级别的过滤，以及同级、调高、调低时重新配置。
重复初始化测试还设置了根 Handler，并使用子 Logger，确认事件只输出一次。
这是启动阶段配置，不在每次请求中重配日志；它不是一套通用第三方日志配置管理器。

理解检查：设置 DEBUG 后，为什么启动消息仍显示 INFO？
答案：DEBUG 允许更详细的事件通过，但这条事件本身由 `logger.info` 发出。

## A6.3：异常日志与整体验收

`logger.error("message")` 默认只记录消息；
在 `except` 内使用 `logger.exception("message")`，会以 ERROR 级别记录消息及当前异常调用栈。
后者等价于此场景下的 `logger.error("message", exc_info=True)`。
调用栈显示错误经过哪些位置，最后一行显示异常类型和消息。
不要在没有当前异常的地方用 `logger.exception`；它不是自动捕捉异常的机制。

单独运行教学示例（不联网、不访问数据库，不改变正常启动路径）：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag.logging_demo
```

预期输出结构如下（UTC 时间、文件路径和行号以实际运行为准）：

```text
<UTC时间> ERROR car_knowledge_rag.logging_demo Demo conversion failed (message only)
<UTC时间> ERROR car_knowledge_rag.logging_demo Demo conversion failed (with traceback)
Traceback (most recent call last):
  ... logging_demo.py ...
    int("demo-not-a-number")
ValueError: ...
<UTC时间> INFO car_knowledge_rag.logging_demo Demo completed; the demonstration error was handled
```

示例为比较 API，刻意将同一次错误记录两次。真实业务通常只在负责处理失败的边界记录一次，
不要每层捕获、记录后再抛出，造成重复日志。预期内的输入错误一般无需完整调用栈；
需要定位原因的异常可记录调用栈，再根据业务规则决定继续、重试或重新抛出。

这个示例明确处理了演示错误，所以退出码为 0。ERROR 日志不会自行结束程序；
重新抛出用 `raise`，进程退出策略由入口负责，而非由日志级别决定。
导入该模块不会执行示例，只有显式运行才会制造演示错误。
示例固定 INFO 以便教学，不读取个人 `.env`；正常应用仍使用 A5 的配置。

### 日志内容边界

- 不记录密钥、令牌、完整配置、认证头或带秘密的 URL。
- `%s` 参数化消息不等于脱敏；`logger.exception` 也不会自动隐藏异常消息和文件路径。
- 处理外部服务错误时先判断异常内容能否记录；不要直接倾倒完整请求和响应。
- 当前是多行纯文本日志，不实现自动脱敏、JSON 日志或云端多行聚合。

### A6 验收

运行上面的 unittest 命令，覆盖：UTC 格式、stderr 通道、配置接线、五种级别、
重复初始化和子 Logger，以及异常调用栈、示例退出行为和导入无副作用。
配置错误仍在日志初始化前由入口报告，不回显原始配置值。

复习题：

1. `logger.exception` 会自动终止程序吗？
2. 为什么不能直接把带令牌的外部 API 异常记录到日志？
3. ERROR 日志后仍出现“示例完成”，是否说明日志失效？

答案：1. 不会；2. 异常消息可能包含秘密，日志不会自动脱敏；
3. 不是，示例已捕获错误并选择继续，日志与控制流程是两件事。

## A7：测试、规范与 GitHub Actions

### A7.1 pytest

`pytest` 和 `ruff` 放在 `pyproject.toml` 的 `dev` 依赖组，版本由 `uv.lock` 锁定。
它们不是业务运行依赖。开发环境用 `uv sync --locked --dev`；
后续纯运行环境可用 `uv sync --locked --no-dev`。
现有 `unittest.TestCase` 无需重写，pytest 可以直接发现并运行。
`testpaths` 限定测试目录，`pythonpath` 让测试能导入当前尚未打包安装的应用。

### A7.2 Ruff

配置目标 Python 3.11、格式化行长 88，并启用：

- `E4/E7/E9`：基础代码错误；
- `F`：未使用导入、未定义名称等问题；
- `I`：导入排序与分组。

检查只针对 `car_knowledge_rag` 和 `tests`，不扫描本地其他目录。
ESLint 用于未来 TypeScript 前端，本步不引入。

在项目根目录执行，与 CI 使用相同检查内容：

```powershell
& .\.tools\uv\bin\uv.exe sync --locked --dev --python-preference only-system --no-python-downloads --cache-dir .uv-cache
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache ruff check car_knowledge_rag tests
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache ruff format --check car_knowledge_rag tests
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m pytest -v
```

`ruff check` 检查代码规则，`ruff format --check` 只检查格式，`pytest` 验证行为。
本地需要修正格式时用 `ruff format car_knowledge_rag tests`，它会改写文件；
之后审阅 diff 并重新运行检查。CI 不自动修复或提交代码。
原有 `python -m unittest discover -s tests -v` 仍可运行。

### A7.3 工作流

`.github/workflows/ci.yml` 在 push、PR 创建或更新以及手动触发时运行。
Linux 临时环境依次拉取代码、安装固定版本 uv、安装 Python 3.11、
执行 `uv sync --locked --dev`，再执行 lint、格式检查和测试。
Action 使用完整提交 SHA 固定，工作流权限仅为 `contents: read`，
不保留 checkout 凭证，不读取项目秘密，不部署资源；超时为 10 分钟。
Python 固定 3.11 系列，补丁版本可能与本地不同。

### A7.4 查看结果与处理失败

推送后在仓库的 Actions 页面打开对应提交的 CI，再进入 `Python quality`：

- `Lint` 失败：按文件、行号和规则编号修正问题；
- `Check formatting` 失败：本地格式化并检查 diff；
- `Test` 失败：查看失败断言、实际值与调用栈；
- 依赖安装失败：先区分锁文件不同步、平台兼容性与网络错误。

修正后重跑本地检查，再提交推送。CI 通过不会自动部署或合并；
未设置分支保护时，CI 失败也不会自动禁止直接推送 main。
本地通过和 GitHub Linux 通过是两份不同证据，首次云端结果以 Actions 实际运行记录为准。

理解检查：Ruff 通过能否证明配置优先级正确？
答案：不能。静态检查和格式检查不代替行为测试。
