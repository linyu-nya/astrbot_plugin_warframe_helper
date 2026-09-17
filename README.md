# Warframe Helper 插件

面向 AstrBot 的 Warframe（国际服）信息查询与交易助手。

本仓库由 [linyu-nya](https://github.com/linyu-nya/astrbot_plugin_warframe_helper) 独立维护，后续开发与插件更新使用本仓库的 `master` 分支。
基于 [moemoli 的原始项目](https://github.com/moemoli/astrbot_plugin_warframe_helper) 开发，保留原项目许可证与作者署名。

## 开发与打包

```bash
python -m pip install -r requirements.txt -r requirements-test.txt
python -m pytest -q
python scripts/package_plugin.py --theme release
```

打包脚本在仓库同级目录生成 ZIP，安装入口文件位于压缩包根目录。
虚拟环境、测试和开发文档不会进入安装包。

## 指令一览（部分支持平台参数）

### 世界状态

- `/警报`：当前警报
- `/裂缝`、`/普通裂缝`、`/钢铁裂缝`、`/九重天裂缝`
- `/奸商`
- `/仲裁`
- `/突击`
- `/电波`
- `/入侵`
- `/集团`
- `/平原`、`/夜灵平原`、`/魔胎之境`、`/地球昼夜`
- `/双衍王境`（别名：`双衍王镜`）
- `/轮回奖励`
- `/执行官猎杀`
- `/科研 [深层|时光]`：查询深层科研和时光科研，不参与自动推送
- `/钢铁奖励`

> 世界状态类指令支持平台参数（如 `pc / ps4 / xb1 / swi / cn`），例如：`/裂缝 cn`、`/突击 国服`。

国际服世界状态优先读取官方 CDN；官方响应不可用或结构无效时，自动回退到配置项 `warframestat_api_bases` 中的聚合接口。

裂缝默认按“古纪、前纪、中纪、后纪、安魂、全能”排列，同一纪元内按剩余时间升序排列。
如需恢复仅按剩余时间排序，可在插件配置中关闭“裂缝按纪元排序”。该配置同时作用于
图片回复和文字回退回复。

### 国服数据回退（参考 hole-wf-api 思路）

当 WeGame 直连接口出现 `-13/-16` 时，插件会按顺序尝试：

1. 签名 URL 直连
2. Playwright 浏览器抓取页面中的 `/ajax_get_worldState` 响应
3. 你配置的第三方备用 URL / Base URL（可对接自建 hole-wf-api）
4. 最后回退到国际服 PC worldstate，避免指令硬失败

以上回退链路已内置默认行为。

### 仲裁数据源（按 hole-wf-api 补齐）

`/仲裁` 现在采用多源策略：

1. 优先 `warframestat` 的 `/arbitration` JSON
2. 回退 `browse.wf/arbys.txt`（时间戳 + 节点）并自动映射节点名

### 订阅提醒

- `/订阅 <条件> [次数|永久]`
	- 裂缝示例：`/订阅 钢月`（钢铁 月球 全能 生存）
	- 平原示例：`/订阅 夜灵平原 黑夜 3`
- `/退订 <条件>`、`/退订 全部`
- `/订阅列表`

### 群自动推送

- `/推送开启 [平台]`：AstrBot 管理员在当前群开启自动推送
- `/推送关闭`：关闭当前群自动推送
- `/推送状态`：查看当前群状态

自动推送使用纯文字，范围固定为：

- 钢铁之路、塞德娜、中断任务的全能裂缝，并显示剩余时间
- Lotus 的礼物和特殊活动，并显示剩余时间
- Warframe 官方更新新闻及网页链接
- 每日突击和每周执刑官，并显示剩余时间
- 奸商到访后的新库存，并显示离开前剩余时间

首次开启只记录当前内容作为基线，不会把已有内容集中补发。后续重启会读取持久化去重状态，
并补发停机期间出现且当前仍能从接口获取的新内容。科研、双衍王境和入侵仅提供查询，不自动推送。

轮询间隔可在插件配置的“世界状态自动推送”中设置，默认 60 秒，最小 30 秒。

### 百科查询（灰机 Wiki）

- `/wk <关键词>`：查询 Warframe 灰机 Wiki
- 查询会先使用本地别名映射；命中后打开对应的 Wiki 精确页面，否则返回 Wiki 搜索页
- Wiki 查询不依赖 `warframe.market` 校验，因此也可以映射非交易词条

当 Wiki API 精确命中时返回词条页；未找到词条或 API 不可用时都会降级到搜索页，并区分“未找到”和“暂时无法确认”两种情况。

### 交易（warframe.market）

- `/wfmap <别名> <全称>`：管理员新增或覆盖本地别名映射
- `/wfmapdel <别名>`：管理员删除本地别名映射
- `/wfmapq <全称>`：公开反查本地别名
- `/wm ...`：物品订单
- `/wmr ...`、`/wr ...`：紫卡（Riven）拍卖；`/wk` 是百科查询，不是紫卡别名
- `/wfp ...`：价格相关查询

映射仅维护本地别名与全称的关系，不依赖 `warframe.market` 校验，因此可以映射非交易词条。

### QQ官方机器人 Markdown 以及按钮配置

> 你需要预先申请 ```消息模板功能```

- 按钮配置
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "prev",
          "render_data": {
            "label": "⬅️上一页",
            "visited_label": "⬅️上一页",
            "style": 1
          },
          "action": {
            "type": 1,
            "permission": {
              "type": 2
            },
            "data": "wfp:prev",
            "reply": false,
            "enter": true,
            "unsupport_tips": "你的客户端版本不支持消息按钮"
          }
        },
        {
          "id": "next",
          "render_data": {
            "label": "➡️下一页",
            "visited_label": "➡️下一页",
            "style": 1
          },
          "action": {
            "type": 1,
            "permission": {
              "type": 2
            },
            "data": "wfp:next",
            "reply": false,
            "enter": true,
            "unsupport_tips": "你的客户端版本不支持消息按钮"
          }
        }
      ]
    }
  ]
}
```

- Markdown配置

```markdown
# {{.title}}
​
![result #{{.image_w}}px #{{.image_h}}px]({{.image}})
**指令**：{{.kind}}  
{{.page}}
{{.hint}}

```

## 自定义图片底图

插件配置菜单中的“自定义渲染底图”可以为图片回复设置本地图片或 HTTP(S) 图片 URL。
该功能默认关闭，不会改变现有模板；本版本不提供文件上传按钮。

底图按以下顺序选择：

1. 裂缝、价格或世界状态分类底图
2. 全局默认底图
3. 当前 HTML 模板的原始背景

分类范围如下：

- 裂缝：普通裂缝、钢铁裂缝、九重天裂缝
- 价格：`/wm`、`/wmr`、`/wfp`
- 世界状态：周期、活动、赏金及通用世界状态卡
- 其他图片回复：仅使用全局默认底图

### 底图来源

支持 PNG、JPEG 和 WebP，单张最大 15 MiB，解码后最大 4000 万像素。远程图片会在
插件启动时下载并保存到内存，查询时不会重复请求。修改配置后需要保存并重载插件。

```text
# Windows 绝对路径
D:\Pictures\warframe-background.webp

# Docker 容器内路径，必须确保宿主机目录已挂载到容器
/AstrBot/data/warframe/background.png

# 相对于插件目录
assets/background/custom.jpg

# 远程图片
https://example.com/warframe/background.webp
```

Docker 部署填写的是容器内路径，不是宿主机路径。例如将宿主机目录挂载为
`/AstrBot/data/warframe` 后，再填写该容器路径下的图片。

### 外观参数

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| 启用自定义底图 | 关闭 | 总开关；关闭时不读取或下载底图 |
| 全局/裂缝/价格/世界状态底图 | 空 | 分类为空或失败时回退全局底图 |
| 底图填充方式 | `cover` | 支持 `cover`、`contain`、`width`、`repeat-y` |
| 底图位置 | `center center` | 例如 `center top`、`50% 20%` |
| 启用底图遮罩 | 开启 | 可独立关闭 |
| 遮罩颜色/不透明度 | `#0f172a` / `42` | 不透明度范围 0-100 |
| 面板颜色/不透明度 | `#0f172a` / `58` | 不透明度越低，透出的底图越多 |
| 启用毛玻璃效果 | 开启 | 可独立关闭，不影响底图与透明面板 |
| 毛玻璃模糊程度 | `6px` | 范围 0-30px |
| 文字明暗模式 | `light` | 深色底图用 `light`，浅色底图可用 `dark` |

填充方式不会改变图片宽高比：`cover` 铺满并允许裁切，`contain` 完整显示但可能留白，
`width` 按画布宽度显示一次，`repeat-y` 按宽度纵向重复，适合超长列表或无缝纹理。

如果路径不存在、下载失败、格式不支持或图片超限，插件会记录 warning，并自动回退到
上一级底图或原模板背景，不会让查询指令失败。

## Playwright 浏览器安装

插件使用 Playwright 进行截图渲染。首次部署请先安装浏览器依赖与浏览器内核：

```bash
playwright install-deps
playwright install
```

若只需要 Chromium，也可以指定：

```bash
playwright install-deps chromium
playwright install chromium
```

> 说明：在 Windows/macOS 上，`playwright install-deps` 可能提示不支持，可忽略；`playwright install` 仍需执行。
