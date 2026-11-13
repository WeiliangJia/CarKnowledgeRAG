# C4–C5 配置查询

2026-11-13（Australia/Sydney），按「实现 C4 C5」开展。代码基线为 `0b164cb`，实际投入时间未计量。

C4 定位快照内的配置字段和版本。C5 按同一字段对齐不同版本，并遍历所选快照的全部版本做条件筛选。Python 查询函数通过 SQLAlchemy 绑定参数，从 C1–C3 的 PostgreSQL 表读取数据。结果包含快照 ID、官方 URL、采集时间、行列位置、字段原名、原值、单位、配置状态、脚注及核验信息。

## PowerShell 命令

先按 [C1–C3](C1-C3-postgres.md) 设置 `DATABASE_URL`，并使用导入命令输出的 `snapshot=` 值。下列快照 ID 来自本次验证的 9X 官方快照。命令返回 UTF-8 JSON。

```powershell
$env:PYTHONUTF8 = '1'
$snapshot = 'fa6836814b1b3d49400616ebb3f0cfb2b4c112f0fa7c5178dbffcd40e8823f37'
$python = '.\.venv\Scripts\python.exe'
& $python -m car_knowledge_rag.query_config --snapshot $snapshot catalog
& $python -m car_knowledge_rag.query_config --snapshot $snapshot lookup --version Ultra版 --field 电池容量
& $python -m car_knowledge_rag.query_config --snapshot $snapshot lookup --version Ultra版 --group 9X六座版 --field 电池容量
& $python -m car_knowledge_rag.query_config --snapshot $snapshot compare --column 5 --column 2 --field 乘坐人数 --field 车身宽度 --field GMY_9X_01:row-20
& $python -m car_knowledge_rag.query_config --snapshot $snapshot filter --number 乘坐人数 eq 5 人 --number GMY_9X_01:row-20 ge 350 km
& $python -m car_knowledge_rag.query_config --snapshot $snapshot filter --status 闭式双腔空气悬架 standard
```

- `catalog` 列出版本列号和字段 ID。字段可用 ID、精确规范名或精确原名。`续航里程` 对应多个口径，可用 `GMY_9X_01:row-20` 指定 CLTC 纯电续航。
- `lookup` 可用列号，或用精确版本名和可选分组。名称匹配多项时，退出码为 2，JSON 含 `ambiguous` 和候选。找不到时返回 `not_found`。
- `compare` 按命令中指定的列与字段顺序返回。每行 `facts` 与 `versions` 一一对应，缺失记录为 `null`。
- `filter` 使用 AND 组合条件。数值操作符为 `eq`、`lt`、`le`、`gt`、`ge`，单位必须与字段定义一致。配置状态可指定 `standard`、`optional` 或 `unavailable`。
- 缺失或带待核验原因、限定文字、证据不足标记的事实会使相应条件无法判定。任一条件确定不满足时，整个版本归入 `no_match`。其余版本按全部条件成立或仍有未知分别归入 `match`、`undetermined`。

## Python 接口

在已有的 SQLAlchemy 连接上构造 `ConfigQuery(connection, snapshot_id)`，调用 `lookup(field, version, group=...)`、`compare(columns, fields)` 或 `filter(conditions)`。`version` 可传整数列号或版本名。筛选条件使用 `NumericCondition(field, operator, value, unit)` 或 `StatusCondition(field, value)`。Python 返回值保留数据库的 `Decimal` 和时间类型。命令行将 `Decimal` 序列化为十进制字符串，便于原样回显。名称歧义和无匹配通过 `SelectionError.result` 提供结构化信息。

## 验收结果

通过 C1–C3 的 WSL PostgreSQL 16.15 实例执行上面的命令，目录返回 7 个版本与 277 个字段，查询、比较和筛选断言均通过。Ruff 检查通过，pytest 86 项通过、1 项既有符号链接测试跳过、11 个子测试通过。Docker Compose 路径待验证。

- `Ultra版` 返回第 2、5 列候选。指定六座后，电池容量原值为 `55/70`，单位 `kWh`，单值数值为空，核验状态为证据不足。
- 比较五座和六座 Ultra 时，座位数依次为 5、6。CLTC 纯电续航保留脚注 1，可回查官方测试说明。
- 筛选五座且 CLTC 纯电续航至少 350 km 时，五座 Hyper 和曜黑满足，四个六座版本不满足，五座 Ultra 因 `288/380 km` 的适用条件证据不足而无法判定。
- 7 个版本均匹配闭式双腔空气悬架标配的筛选条件。
- 理解练习可以把筛选门槛改成 356 km，再预测两款明确为 355 km 的五座版本会进入哪个结果。用户理解尚未确认。
