# 可配置渲染底图设计

## 背景

插件目前通过 `assets/template/<name>/` 下的 HTML 模板生成图片，并允许通过
`render_template_name` 切换整套模板。该机制适合模板开发者，但普通用户如果只想
替换底图，仍需复制并修改多份 HTML。

本功能在保留整套模板切换能力的前提下，为内置模板增加一层可选的渲染主题配置。
用户可在 AstrBot 插件配置菜单中填写本地图片路径或 HTTP(S) URL，并为不同信息
类别设置单独底图。

## 目标

- 默认关闭；关闭时图片输出与当前版本一致。
- 支持一张全局默认底图。
- 支持裂缝、价格和世界状态三类底图覆盖。
- 分类底图为空或加载失败时回退到全局底图。
- 全局底图为空或加载失败时回退到原有模板背景。
- 支持本地路径和 HTTP(S) URL，不提供配置面板文件上传接口。
- 毛玻璃可独立开关，模糊程度可配置。
- 遮罩、面板、背景适配等视觉参数均可在配置菜单调整。
- 不破坏 `render_template_name` 和会话级模板选择。

## 非目标

- 不新增独立 WebUI 或文件上传 API。
- 不提供在线图片编辑、裁剪或压缩工具。
- 不保证第三方自定义模板自动应用主题；第三方模板可主动接入主题上下文。
- 不执行 SVG、HTML 或其他可能包含脚本的资源。

## 配置模型

在 `_conf_schema.json` 中新增 `render_background` 对象：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | 自定义底图总开关 |
| `default_source` | string | `""` | 全局底图，本地路径或 HTTP(S) URL |
| `fissure_source` | string | `""` | 裂缝类覆盖底图 |
| `market_source` | string | `""` | `/wm`、`/wmr`、`/wfp` 覆盖底图 |
| `worldstate_source` | string | `""` | 周期、活动、赏金和通用世界状态覆盖底图 |
| `background_fit` | string | `"cover"` | `cover`、`contain`、`width` 或 `repeat-y` |
| `background_position` | string | `"center center"` | CSS 背景位置，如 `center top`、`50% 20%` |
| `overlay_enabled` | bool | `true` | 是否在底图上增加统一颜色遮罩 |
| `overlay_color` | string | `"#0f172a"` | 遮罩颜色，仅接受 `#RGB` 或 `#RRGGBB` |
| `overlay_opacity` | int | `42` | 遮罩不透明度，范围 0-100 |
| `panel_color` | string | `"#0f172a"` | 内容面板颜色，仅接受十六进制颜色 |
| `panel_opacity` | int | `58` | 内容面板不透明度，范围 0-100 |
| `glass_enabled` | bool | `true` | 毛玻璃效果开关 |
| `blur_px` | int | `6` | 毛玻璃模糊半径，范围 0-30px |
| `text_mode` | string | `"light"` | `light` 或 `dark`，控制主题文字配色 |

数值配置在运行时统一钳制到安全范围；非法颜色或枚举值回退到默认值。所有来自
用户配置的 CSS 值均经过白名单解析，不直接拼接任意 CSS。

## 分类和回退

渲染作用域由当前指令及模板文件共同确定：

- `fissure`：`crack.html`，包括普通、钢铁和九重天裂缝。
- `market`：`wm.html`、`wmr.html`、`wfp.html`。
- `worldstate`：`status_list.html`、`cycle_status.html`、`event.html`、`赏金.html`。
- `default`：其他内置模板，仅使用全局底图。

资源选择顺序为“分类底图 -> 全局底图 -> 原模板背景”。分类资源下载或校验失败时，
不能阻断全局资源加载。

## 图片资源处理

新增背景资源管理器，在插件 `initialize()` 阶段加载配置中的底图：

1. 以 `http://` 或 `https://` 开头时，通过插件现有 HTTP 工具下载。
2. 其他值视为本地路径；绝对路径直接读取，相对路径相对于插件根目录解析。
3. 单个资源最大 15 MiB；远程响应按块读取并在超限时立即停止，不先完整缓冲。
4. 使用 Pillow 校验实际格式和解码尺寸，仅接受 PNG、JPEG 和 WebP，且不超过 4000 万像素。
5. 校验成功后转成 data URI 保存在内存中，渲染时不再访问网络或磁盘。
6. 插件重载时重新读取资源，因此配置修改在保存并重载插件后生效。

远程 URL 不直接交给 Playwright 加载，以免查询时受到网络波动、跨域和加载时序影响。
日志只记录来源类型和失败原因，不输出 data URI。

## 模板集成

新增不可变的 `RenderTheme` 数据对象。背景资源管理器初始化完成后，将各作用域主题
交给模板加载层。`load_html_template()` 根据当前指令选择主题，并向 Jinja 上下文增加：

```text
render_theme.enabled
render_theme.css
render_theme.scope
```

`render_theme.css` 由受控配置生成，负责：

- body 底图、位置、适配和重复方式；
- 可选的全局遮罩；
- 面板半透明背景；
- 可选的 `backdrop-filter` 和 `-webkit-backdrop-filter`；
- light/dark 两套文字、边框和标签颜色。

内置模板在 `<head>` 中加入 `{{ render_theme.css | safe }}`。关闭功能时 CSS 为空，确保
当前输出不变。第三方模板不被自动修改；模板作者加入同一行即可接入主题。

## 背景适配模式

- `cover`：保持比例并铺满画布，允许裁切，适合人物插画，作为默认值。
- `contain`：完整显示图片，可能留出空白区域。
- `width`：宽度铺满、高度自适应，不重复，适合纵向长图。
- `repeat-y`：宽度铺满并纵向重复，适合无缝纹理或超长列表。

所有模式都不改变图片宽高比。

## 错误处理

- 总开关关闭：不读取任何自定义资源。
- 单项路径不存在、下载失败、格式错误或超限：记录一次 warning，并继续处理其他资源。
- 分类资源失败：回退全局资源。
- 全局资源失败：使用原模板背景。
- 主题 CSS 生成异常：返回空 CSS，不影响图片查询。

## 测试策略

- 配置解析：默认值、范围钳制、非法颜色、非法枚举和开关行为。
- 本地资源：相对路径、绝对路径、合法格式、伪造扩展名、超限和不存在文件。
- 远程资源：成功、超时、非法内容及分类资源失败后的全局回退。
- 作用域解析：裂缝、价格、世界状态和默认模板分类。
- CSS 生成：毛玻璃开关、模糊值、遮罩和面板透明度、背景适配模式、明暗文字模式。
- 模板回归：关闭功能时不出现主题 CSS；开启后内置模板均能正常渲染主题上下文。

## 兼容性和文档

- 配置新增字段由 AstrBot 自动补默认值，旧配置无需迁移。
- README 增加本地路径、Docker 容器路径和 URL 示例。
- README 明确远程图片在插件启动时下载，配置更新后需要重载插件。
- CHANGELOG 记录新增可配置底图及主题参数。
