# B1 极氪中国官网来源清单与结果报告

核查日期：2026-11-04（报告时区 Australia/Sydney；资料市场为中国大陆）。
入口：[极氪中国官网车型导航](https://www.zeekrlife.com/zh-cn/home)。
本次重新逐一访问官网导航、车型页和“参数配置”，不是复用 A3 结果。

## 结果与计数口径

- 官网导航：11 个独立车型入口，全部已核对。
- 参数配置：11 个页面均正常加载表头和参数行，共 35 个基础配置列。
- 资料形式：动态 HTML 车型说明页 + 动态 HTML 配置对照表。
- 本次无未核实的导航车型或未打开的参数表；但完整参数、脚注及选装关系尚未采集核验。
- 35 不包含全部电池、座位、车漆与选装组合，不等于订单 SKU 数量。
- “最新”仅指本次核查日期的公开展示，不证明每个版本实时可下单。

机器可读清单：[zeekr-2026-11-04.json](../data/sources/zeekr-2026-11-04.json)。
这是人工核对的来源登记表，不是完整网页快照或可直接用于问答的参数数据集。
`columns` 按配置表列顺序记录；`group` 为表头分组，null 表示本清单没有登记单独分组。
列名保留观察到的空格，不在本步做版本名规范化。

## 全部入口与配置版本

所有条目状态均为“车型入口与配置表头已核实”，格式均为动态 HTML。
每个条目的“车型页”用于后续收集官方功能说明，“配置表”用于精确配置与脚注。

| 车型页 | 基础配置列（按官网顺序） | 列数 | 参数入口 |
| --- | --- | --- | --- |
| [极氪 9X](https://www.zeekrlife.com/zh-cn/zeekr9x?modelInfoId=10&modelYearCode=GMY_9X_01) | 六座：Max版、Ultra版、Hyper版、曜黑版；五座：Ultra版、Hyper版、曜黑版 | 7 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=10&modelYearCode=GMY_9X_01) |
| [极氪 8X](https://www.zeekrlife.com/zh-cn/zeekr8x?modelInfoId=11&modelYearCode=GMY_Z012_01) | Max、Ultra、Ultra+、曜影 | 4 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=11&modelYearCode=GMY_Z012_01) |
| [焕新极氪 7X](https://www.zeekrlife.com/zh-cn/zeekr7x?modelInfoId=8&modelYearCode=GMY_7X_02) | 75度后驱Max版、103度后驱Max版、103度四驱Ultra版 | 3 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=8&modelYearCode=GMY_7X_02) |
| [焕新极氪 X](https://www.zeekrlife.com/zh-cn/zeekrx?modelInfoId=3&modelYearCode=GMY_X_04) | Max五座版、Max四座版、Ultra五座版 | 3 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=3&modelYearCode=GMY_X_04) |
| [焕新极氪 007GT](https://www.zeekrlife.com/zh-cn/zeekr007GT?modelInfoId=9&modelYearCode=GMY_007_GT__02) | 75度后驱 Max版、103度后驱 Max版、103度四驱 Ultra版 | 3 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=9&modelYearCode=GMY_007_GT__02) |
| [焕新极氪 001](https://www.zeekrlife.com/zh-cn/zeekr001?modelInfoId=1&modelYearCode=GMY_001_05) | 95度四驱 Max版、103度后驱 Max版、103度四驱 Ultra版、103度四驱 Ultra+版 | 4 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=1&modelYearCode=GMY_001_05) |
| [极氪 001 FR](https://www.zeekrlife.com/zh-cn/zeekr001FR?modelInfoId=4&modelYearCode=GMY_FR_02) | ZEEKR 001 FR | 1 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=4&modelYearCode=GMY_FR_02) |
| [焕新极氪 007](https://www.zeekrlife.com/zh-cn/zeekr007?modelInfoId=5&modelYearCode=GMY_007__03) | 75度后驱 Max版、103度后驱 Max版、103度四驱 Ultra版 | 3 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=5&modelYearCode=GMY_007__03) |
| [焕新极氪 009](https://www.zeekrlife.com/zh-cn/zeekr009?modelInfoId=2&modelYearCode=GMY_009_06) | 七座 Ultra版、七座 Ultra+齐家版、六座 Ultra+行政版 | 3 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=2&modelYearCode=GMY_009_06) |
| [极氪 009 光辉系列](https://www.zeekrlife.com/zh-cn/zeekr009grand?modelInfoId=6&modelYearCode=GMY_009_04) | 极氪009 光辉、极氪009 光辉典藏版 | 2 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=6&modelYearCode=GMY_009_04) |
| [极氪 MIX](https://www.zeekrlife.com/zh-cn/zeekrmix?modelInfoId=7&modelYearCode=GMY_MIX_01) | 智驾版、长续航智驾版 | 2 | [配置表](https://www.zeekrlife.com/zh-cn/config?modelInfoId=7&modelYearCode=GMY_MIX_01) |
| 合计 | 11 个官网车型入口 | 35 | 11 个公开在线参数表 |

## 官方标识与条件

`modelInfoId`、`modelYearCode` 由实际导航 URL 记录，完整保存在 JSON 中。
`GMY_007_GT__02`、`GMY_007__03` 等包含双下划线，不能擅自修正；批次代码不能直接当自然年款。
001 FR 和 009 光辉系列按官网独立入口收录，不擅自归并后遗漏。

已观察到需要后续处理的例子：

- 9X：六座四列、五座三列，Ultra 等名称在分组间重复；部分列存在不同电池条件。
- 8X：Max/Ultra/Ultra+ 的座位行显示 5/6 人、电池行显示 55/70；
  曜影列为 5 人、70。不能把所有条件自由组合后声称官网都可订购。
- X、009：座位布局直接写在列名中，不可清洗掉。
- 007 与 007GT：版本名称相似，但参数不能跨车型复用。

这些只用于识别采集难点，不是本步完成的参数核验报告。

## 调查方式、缺口与后续输入

普通静态读取只得到 JavaScript 提示，因此本次通过浏览器读取公开页面。
页面初始可能只有“标配/选配/无该配置”，需要等版本列和参数行加载后才能确认内容。
未登录、未提交预约/订单表单、未获取私有接口、未使用第三方数据补齐。

本次没有确认独立 PDF 或图片下载入口，也没有穷尽官网所有资源；
“没有确认下载文件”不等于官网没有配置资料，更不等于必须做 OCR。
当前 11 个在线表足以作为后续原始资料获取的主入口；若 B2 发现新的公开附件，再登记来源。

对照 A3 历史调查：导航入口、官方批次代码及基础版本列清单未发现变化。
本次没有逐字段对比完整参数与脚注，不能据此宣称配置内容完全未变。

验收：官网导航 11 项均有车型页、配置页及已核实的表头；
JSON 结构、唯一入口、分组内列名、11/35 计数、URL 标识和文档链接已检查。
不重跑未改动的业务测试。本步没有增加依赖、采集脚本、完整页面存档、哈希或索引。

下一步仅可在用户允许后执行 B2：获取原始资料。B1 完成不构成 B2 授权；未推送 GitHub。
