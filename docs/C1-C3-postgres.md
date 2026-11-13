# C1–C3：本地 PostgreSQL、迁移和 9X 导入

## C1：启动

在项目根目录，用 PowerShell 7 运行。密码只在当前终端设置；不要加入项目的应用 `.env`。

```powershell
$env:POSTGRES_PASSWORD = Read-Host '本地开发数据库密码' -MaskInput
docker compose up -d --wait
$encodedPassword = [uri]::EscapeDataString($env:POSTGRES_PASSWORD)
$env:DATABASE_URL = "postgresql+psycopg://car_rag:${encodedPassword}@127.0.0.1:55432/car_knowledge"
```

Compose 只绑定本机 55432 端口，数据保存在独立命名卷中。`docker compose stop` 保留数据。
已有卷不会因修改环境变量而自动更换密码。此配置用于本地开发，不是生产部署。

## C2：迁移

```powershell
& .\.tools\uv\bin\uv.exe run --locked --cache-dir .uv-cache python -m alembic upgrade head
```

Alembic 建立四张表：快照保存来源与脚注；版本以快照和列号标识；字段以快照和行号标识；
配置事实关联同一快照的行与列。五座与六座的同名版本不会互相覆盖。
数值、原文、状态、限定文字、B7 待核验原因与 B9 结论分别保存。

## C3：导入

```powershell
& .\.tools\uv\bin\uv.exe run --locked --cache-dir .uv-cache python -m car_knowledge_rag.import_config data/parsed/zeekr/9x-b4-verified.json data/normalized/zeekr/9x-b7-v1 data/raw/zeekr/20261104T061714920392Z-70f8b89f/10/config/text.txt
```

导入先执行 B8 检查，并用固定官方快照重跑 B9。发现差异时拒绝导入，证据不足不算差异。
写入在单个事务内完成；快照以 B4 输入哈希标识。同一快照和导入内容再次执行会跳过；
同一快照对应不同导入内容时拒绝覆盖。该命令不是修复手工改动数据库的工具。

`55/70` 保留原文，单值数值列为空。B9 有证据的条件保存在核验详情中，没有解除原 B7 待核验标记。
本轮只导入 9X，查询接口及评测留给后续步骤。

## 本次验收

- Compose 配置检查通过；Docker Desktop 因 `dockerInference` 端点启动失败，未实测容器启动。
- 使用 Ubuntu WSL 下的独立 PostgreSQL 16.15 实例（本机 55433）实测 Alembic 迁移和两次导入。
  第一次写入，第二次跳过，仍有 1 个快照、7 个版本、277 个字段和 1,939 条配置。
- 124 条待核验原因完整保留。核验状态：133 项一致、2 项条件明确、12 项证据不足、1,792 项未核验。
- 两个同名 Ultra 版本分别存在；两条 `55/70` 均未写入确定性数值。
