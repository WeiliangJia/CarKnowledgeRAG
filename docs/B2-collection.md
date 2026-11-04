# B2 原始资料获取：用法、解说与结果报告

执行日期：2026-11-04（Australia/Sydney）；获取回执使用 UTC 时间。
工作基线：`5f9254d2f4bb5f809a5e4477b289b9b217656718`，B1/B2 改动当前未提交。
输入：[B1 来源登记表](../data/sources/zeekr-2026-11-04.json)。

## 实现内容

新增 `car_knowledge_rag/collect.py`，运行依赖增加 Playwright 1.64.1 并更新锁文件。
使用独立无登录浏览器上下文，不读取日常浏览器资料，不提交预约或订单表单。
串行访问公开资料，页面间短暂停顿；没有验证码绕过、登录、隐藏接口探测或付费模型调用。

本次使用本机已有 Edge 的无头通道。默认 Chromium 通道需要另行安装浏览器，
不把“已安装 Playwright Python 包”误当成“已安装它的浏览器”。

### 运行

从项目根目录执行，以下命令会访问官网并创建新的原始资料目录：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag.collect --channel msedge --timeout-ms 30000
```

只获取单个车型（例如 9X 的官方 ID 为 10）：

```powershell
& .\.tools\uv\bin\uv.exe run --locked --python-preference only-system --no-python-downloads --cache-dir .uv-cache python -m car_knowledge_rag.collect --channel msedge --model-id 10 --timeout-ms 30000
```

`--source` 指定登记表，`--output-root` 指定存储根目录，`--model-id` 可重复指定。
`--timeout-ms` 是单次导航/加载等待上限，并非整个任务时限，默认 60000。
`--channel` 支持 chromium、msedge、chrome，需相应浏览器存在。
如果选用默认 Chromium，先执行 `uv run python -m playwright install chromium`；
这是下载浏览器的命令，本次未执行。

普通运行按输入目录执行，不自动重新调查官网导航。若版本变化需先复核 B1。
采集 CLI 暂用 INFO 日志和命令行参数，不扩充 A5 的 `.env` 字段；不是配置热加载服务。

## 保存结构与各文件作用

```text
data/raw/zeekr/<UTC时间-随机后缀>/
  source-catalog.json
  run.json
  <modelInfoId>/
    product/
      response.html
      rendered.html
      text.txt
      receipt.json
    config/
      ...
    detail-1/     # 从中转页实际发现时才产生
      ...
```

- `response.html`：服务器最初返回的 HTML，可能只是需要 JavaScript 的外壳。
- `rendered.html`：通过加载检查后的 DOM HTML，保存配置表和脚注结构。
- `text.txt`：浏览器读取的正文文字，便于快速检查，不当作规范化参数表。
- `receipt.json`：来源、最终 URL、获取时间、HTTP 状态、成功/失败及已保存文件。
- `source-catalog.json`：本次输入目录副本；`run.json` 是获取结果回执汇总。

每次新建目录，不覆盖旧快照；JSON 回执使用独占写入。
失败时保留已获得的初始响应和失败回执，不保存伪成功的空正文。
有失败、未尝试页面或浏览器级中断时退出码为 1，全部成功为 0。
磁盘等非浏览器异常不伪装成网页加载失败；运行被强制终止时可能没有完整 run.json，需检查残留目录。
文件哈希、内容去重、正式版本清单与存档完整性校验留到 B3。

原始资料位于 Git 忽略的 `data/raw/`，仅保存在本地，目前没有云备份。
这些文件不是资源自包含的离线网站：未下载全部图片、视频、CSS、交互选项或 iframe 内容，
也未承诺捕获滚动/点击后才生成的所有说明。后续解析发现缺口需另行记录补采。

## 关键代码与加载规则

1. 输入登记表由 Pydantic 检查，ID 限制为数字，来源限制为官方 HTTPS 中国站和匹配的批次标识。
2. `page.goto` 导航并取得初始响应；`page.content()` 与 `body.inner_text()` 保存加载后的结构和文字。
3. 配置页等待 `.model-item .title`、参数名称和脚注出现，再对照 B1 的列名与数量。
   保留重复列数量；只忽略名称空白差异，不把未知版本自动当作已核实。
4. 车型说明页等待正文；若是具有“了解更多”按钮的中转页，标记为 landing，
   沿实际公开按钮确认详情 URL 后获取，登记 `discovered_from_url`，不推测 URL 参数。
5. 接收网页异常后记录类型，避免把浏览器的完整错误消息直接倾倒到日志。

这是页面可用性检查，不是配置字段质量验收。B4/B7/B9 才处理表格语义、规范化和数值核验。

## 本次执行结果

| 运行目录后缀（完整目录名） | 页面尝试 | 失败 | 用途 |
| --- | --- | --- | --- |
| `20261104T061613126822Z-c48b2966` | 2 | 0 | 9X 首个样本 |
| `20261104T061714920392Z-70f8b89f` | 22 | 1 | 全量基础入口；8X 说明页因中转结构超时 |
| `20261104T062015905908Z-2c816c92` | 4 | 0 | 修正后获取 8X 中转、两条详情及配置表 |

合并成功来源后，22 个 B1 基础 URL 全部有成功快照，加上两条 8X 详情，共 24 个不同 URL。
不是“一个全量运行全部成功”：全量运行仍保留 1 次失败，后续独立运行补齐。
首次样本和全量有重复，合计 28 次尝试、27 次成功、1 次失败；没有执行 B3 去重。

8X 中转页正文只有约 50 字，初版“大于1000字”的加载条件将它判作超时。
通过浏览器检查实际公开按钮，确认了：

- [曜影详情](https://www.zeekrlife.com/zh-cn/zeekr8x?modelInfoId=11&modelYearCode=GMY_Z012_01&versionGroupId=2)
- [普通8X详情](https://www.zeekrlife.com/zh-cn/zeekr8x?modelInfoId=11&modelYearCode=GMY_Z012_01&versionGroupId=1)

修正为明确识别中转结构并跟进详情，没有把通用等待阈值随意降低，也没有覆盖失败记录。
这项 B1 未展开的说明页结构已在 B2 补充发现，原 B1 登记表保持不变。

## 验收与限制

- 本次检查：全部 22 个基础 URL 与两条新增详情均有成功快照；成功记录的四个文件均存在且非空。
- 本地总计 116 个快照/回执文件，5,646,352 字节，包含重复和失败资料；后续运行会增加数量。
- 离线测试：29 项测试、11 个子测试通过，覆盖来源限制、列变化、超时、存档、不覆盖和浏览器启动失败。
- Ruff 代码及格式检查通过；自动测试使用模拟页面，不依赖网络或浏览器二进制，CI 无需访问官网。
- 真实官网运行与离线测试是两种证据，测试成功不保证未来官网结构不变。

仅新增采集能力和原始资料，不包含 HTTPX 附件下载、OCR、配置解析、哈希、索引或模型调用。
未推送 GitHub，未运行新 CI，不进入 B3。

理解检查：为什么 `response.html` 保存成功，仍可能需要将页面标为失败？
答案：服务器成功响应不代表动态表格已加载，必须检查渲染后的版本、参数行和脚注。
