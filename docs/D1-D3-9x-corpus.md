# D1–D3 极氪 9X 语料准备

以 C6、C7 引用的 2026 年 11 月 4 日官网快照为基准。从仓库根目录运行以下命令，将语料包写入一个新文件。

```powershell
& .\.venv\Scripts\python.exe -m car_knowledge_rag.prepare_corpus --output data/corpus/9x-d1-d3.json
```

`data/corpus/` 中的结果保存在本地。重新导出时请指定新文件。命令从现有 B3 清单、B4 解析结果、B7 规范化文件和原始快照读取数据。

| 步骤 | 语料包字段 | 内容 |
| --- | --- | --- |
| D1 快照清单 | `model`、`capture`、`inputs`、`sources` | 固定到同一批成功采集的 S1 配置页和 S2 产品页。记录官网地址、采集时间、回执、HTML 和可见文本的哈希。页面文件路径相对于 `data/raw/zeekr`，其余输入路径相对于 `data`。 |
| D2 产品正文 | `product.blocks`、`product.notices` | 用 Beautiful Soup 定位产品正文和章节，将 DOM 内容逐块与原始文本对齐，保留原始行号。过滤导航、选配按钮、预约表单及页脚，保留正文中的限制说明和页面级交付声明。 |
| D3 配置证据 | `configuration.fields`、`configuration.records`、`configuration.notices` | 重解析 S1 与 B4 对照，复用 PostgreSQL 导入前的 B8、B9 校验。按原配置单元格导出证据，附版本、字段 ID、原值、单位、脚注、待核验原因和核验结果。表格图例与公告放在同一配置快照下。 |

S1 用 `snapshot_id`、`row_index`、`column_index` 对应 PostgreSQL 的配置记录，也可通过 `field_id` 回查字段。S2 正文使用原始 `text.txt` 的 1 基行号，与 C7 的定位方式一致。产品页提取器使用这份固定 9X 快照的 DOM 结构。接入不同版式的采集页时，需先核对对应选择器和行号。[配置入库](C1-C3-postgres.md) · [评测来源定位](C7-9x-evaluation.md)

六座 Ultra 的 CLTC 纯电续航记录保留 `288/380` 和 `km`，附脚注 1 和证据不足标记。五座 Ultra 后备厢容积的 H7、H9 对应值保存在核验详情和可读证据中。D4 将在这些带来源定位的正文块和配置证据上建立检索片段。

实测导出 51 个正文块、243 行产品正文、1 条产品页声明和 1,939 条配置记录。C7 两套题集中的产品页区间均可回查，配置记录与 PostgreSQL 入库准备结果一致。重复导出得到相同字节。修改输入副本中的产品页文本后，命令拒绝生成语料包。pytest 通过 91 项、跳过 1 项，11 个子测试通过。Ruff 规则和格式检查通过。
