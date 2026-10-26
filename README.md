# CarKnowledgeRAG

个人车辆知识问答 RAG 调研项目。当前完成 A4、A5 和 A6（控制台日志、级别与异常日志示例）。

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
