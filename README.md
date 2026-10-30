# Notion Now

适用于 Noctalia v5.2.1（插件 API 24）的顶栏插件，同时读取 Google Calendar 和 Notion 数据库。

## 已安装的功能

- 顶栏显示当前活动和剩余分钟，可在插件设置中选择同时显示 1–5 项（默认 2 项），超出显示 +N。
- 插件面板内置设置，右键直接打开设置；支持开关、预览日程切换通知。
- 显示模式：并排、固定宽度定时切换、固定宽度滚动。轮播遍历全部当前活动，不受并排项数限制；宽度可选 140–420 px，切换间隔 2–15 秒。滚动以文字步进方式移动，每秒约 3 字。
- 当前活动默认使用主题强调色，可在插件设置中关闭，恢复普通文字颜色。
- 单例后台服务每 5 秒检查日程边界；同时开始和结束合并通知。初次启动、长时间休眠恢复、缓存过期或同步新增记录不补发旧提示。
- 没有当前活动时显示下一项，查询范围为今天和明天。
- 点击展开今天的活动；右键打开插件设置。面板内也有连接和刷新按钮。
- 每两分钟拉取数据，顶栏每秒重新计算当前活动（滚动模式每 250 毫秒更新）。
- 展开 Google 重复活动，排除取消和本人拒绝的活动。
- 全天活动只显示在面板中；没有结束时间的 Notion 任务只显示为时间点。
- 同步失败保留已有缓存，明确标记缓存和异常。
- 密钥及日程缓存仅存于本机，目录权限 700、文件权限 600。

## 安装

```sh
python3 install.py
```

安装器适用于 Linux、systemd 用户服务和上述 Noctalia 版本。

## 第一次连接

点击插件面板的「设置」或右键顶栏组件，即可调整显示数量和切换提示。
首次连接和重新授权：在插件设置中点击「连接 / 重新授权」，或打开 <http://127.0.0.1:18743>。

### Notion

1. 在 <https://www.notion.so/profile/integrations> 创建内部集成，仅启用读取内容能力。
2. 在要显示的数据库中通过「连接」添加集成，给该集成读取权限。
3. 将集成密钥填入本机连接页面，可指定数据库链接；留空时查找已共享的数据源。
4. 数据库有多个日期字段时，填写 `数据库链接 | 日期字段名称`，选择 Notion Calendar 使用的字段。
5. 保存后刷新连接页面确认「已同步」。有开始、结束时间的日期范围才能成为当前活动。

### Google

1. 在自己的 Google Cloud 项目中启用 Google Calendar API。
2. 配置 OAuth 同意屏幕，创建「桌面应用」OAuth 客户端。
3. 如果应用在测试状态，把自己的账号加入测试用户。
4. 将下载的客户端 JSON 粘贴到本机连接页面，点击授权按钮。
5. 在 Google 完成只读授权；回到本机后刷新确认同步状态。

权限只包括 `calendar.events.readonly` 和 `calendar.calendarlist.readonly`。未申请写入能力。
Google 测试模式的刷新授权可能七天后失效，届时重新连接，或按 Google 要求将自己的应用切换到生产状态。

## 本机位置

- 插件：`~/.config/noctalia/plugins/notion-now/`
- 密钥和配置：`~/.config/notion-now/config.json`、`google-token.json`
- 日程缓存：`~/.local/state/notion-now/events.json`
- 两分钟定时器：`notion-now-sync.timer`
- 本机设置页面服务：`notion-now-setup.service`（仅监听 127.0.0.1:18743）
- 原 Noctalia 配置备份：`~/.local/state/noctalia/settings.toml.bak-notion-now-*`

## 维护

```sh
python3 install.py
python3 -m unittest discover -s . -p 'test_*.py'
lua test_calendar_ui.lua .
lua test_settings_callbacks.lua .
noctalia plugins lint .
systemctl --user start notion-now-sync.service
noctalia msg plugin pyrider3/notion-now:now all health
noctalia msg plugin pyrider3/notion-now:agenda all health
```

首次安装和重复安装会保留其他 Noctalia 设置。安装器使用当前用户的主目录；安装前应确保已有 Noctalia 配置和 Python 3.11 或更新版本。

暂停插件：`noctalia msg plugins disable pyrider3/notion-now`。
暂停后台同步：`systemctl --user disable --now notion-now-sync.timer`。
关闭设置页面：`systemctl --user stop notion-now-setup.service`。

## 当前验证与限制

Python 日历逻辑的 10 项测试通过；Noctalia 插件 lint 无警告；顶栏和面板的 IPC health 检查通过；定时器和连接页面运行正常。

本插件读取数据源，不读取 Notion Calendar 的显示/隐藏配置或数据库视图过滤器。请在插件中指定需要的 Google 日历 ID 和 Notion 数据库。
Notion 通过起始日期上界查询并在本地检查时间区间，覆盖提前开始的跨日活动；历史数据特别多的数据库同步会更慢。
不同来源的同名活动会分别显示；没有共同标识的活动不擅自合并。

官方资料：
- <https://docs.noctalia.dev/noctalia/plugins/development/>
- <https://developers.notion.com/reference/query-a-data-source>
- <https://developers.google.com/workspace/calendar/api/v3/reference/events/list>
- <https://developers.google.com/identity/protocols/oauth2/native-app>

已修复设置开关回调的字符串布尔值转换；强调色与切换提示均可正确关闭并保存。
