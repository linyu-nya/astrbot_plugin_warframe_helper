# 灰机 Wiki 统一查询设计

## 目标

将现有资料查询统一为 `/wk <关键词>`，回复灰机 Warframe Wiki 的词条链接或搜索页链接。`wk` 不再作为紫卡查询别名；紫卡查询只保留 `/wmr` 与 `/wr`。旧的 `/武器`、`/战甲`、`/MOD`、`/掉落`、`/遗物` 命令及其英文别名全部移除。

## 命令行为

- `/wk <关键词>` 和无前缀形式 `wk <关键词>` 执行 Wiki 查询。
- 空关键词返回用法提示：`用法：/wk <关键词>`。
- `wfmap` 保持现有管理与诊断用途；`wk` 复用同一份简称/外号映射数据完成关键词重定向。
- 精确命中时返回：`以下是“原关键词”的 Wiki 页面：`，下一行附最终词条 URL。
- 未命中时返回：`没有查到“原关键词”，以下是 Wiki 搜索页：`，下一行附搜索 URL。
- Wiki 回复使用纯文本，保证 QQ 中的链接可以点击或复制。

## 查询流程

1. 对用户关键词做去首尾空白处理；空内容直接返回用法。
2. 从 `WarframeTermMapper` 的基础别名与用户别名中解析规范名称。Wiki 查询不依赖物品必须可交易，因此映射层需要提供只解析别名、不要求命中 warframe.market 商品的公开方法。
3. 请求灰机标准 MediaWiki Action API：

   `https://warframe.huijiwiki.com/api.php?action=query&prop=info&inprop=url&titles=<关键词>&redirects=1&format=json&formatversion=2`

4. `query.pages` 中存在有效页面时，使用页面对象的 `fullurl`。`redirects=1` 让 MediaWiki 解析重定向，避免自行猜测最终标题和 URL 编码。
5. 页面带有 `missing` 或 `invalid` 时视为未命中。
6. API 超时、403、Cloudflare 验证页、非 JSON 或结构异常时，不把请求抛给用户，也不声称精确命中，而是降级到搜索页。

## URL 生成

搜索页固定使用灰机当前可用的 MediaWiki 搜索入口，并通过标准查询参数编码：

`https://warframe.huijiwiki.com/index.php?title=特殊:搜索&profile=default&search=<规范关键词>&sort=just_match`

由 `urllib.parse.urlencode` 负责中文和特殊字符编码，禁止手工拼接百分号编码。精确命中的页面 URL 优先采用 API 返回的 `fullurl`；若响应确认页面存在但缺少 `fullurl`，才使用 URL 编码后的标题构造 `/wiki/<标题>`。

## 组件边界

- `clients/huiji_wiki_client.py`：封装灰机 API 请求、响应解析、页面 URL 与搜索 URL 生成。网络异常转换为明确的“不可用”结果。
- `services/wiki_commands.py`：解析命令参数、调用别名重定向与 Wiki 客户端、生成最终纯文本。
- `mappers/term_mapping.py`：新增公开的别名规范化方法，供 `wfmap` 与 `wk` 共用，不暴露内部字典。
- `main.py`：注册 `/wk`，从紫卡别名中移除 `wk`，删除旧资料命令注册与实现，更新无前缀路由和帮助卡片。
- `services/market/wmr.py`、`README.md`：移除将 `wk` 描述为紫卡别名的文案，更新命令说明。

## 错误处理

- 灰机当前可能返回 Cloudflare 挑战页，即使状态码或请求本身可达，也必须先验证 `Content-Type` 与 JSON 结构。
- API 不可用时仍返回搜索页，因此 `wk` 在网络受限环境中保持可用。
- 别名未命中不是错误，直接使用用户原关键词查询。
- 别名命中但 Wiki 没有对应精确词条时，搜索页使用重定向后的规范关键词，以提高搜索质量；回复中的引号仍展示用户原关键词。

## 测试

- Wiki 客户端：精确命中、重定向命中、缺页、403、超时、HTML 挑战页、URL 编码。
- 别名解析：外号命中、用户自定义映射、未知词保持原样、映射不依赖市场商品缓存。
- 命令服务：空参数、精确页面回复、未命中搜索页、API 不可用降级。
- 命令接线：`wk` 指向 Wiki；`wmr`/`wr` 指向紫卡；旧资料命令和别名不再注册；帮助文本不再展示旧命令。
- 完成后运行全量测试，确认市场、世界状态、无前缀路由和图片渲染不受影响。

## 文档依据

- 灰机官方说明其生产可用 API endpoint 为 `/api.php`，并兼容 MediaWiki 标准 `/w/api.php`。
- MediaWiki `prop=info&inprop=url` 提供页面 `fullurl`；`redirects=1` 解析重定向。
- MediaWiki `action=opensearch` 适合标题联想，但不能可靠表达“用户关键词恰好命中”，因此本功能不使用它作为精确命中判定。
