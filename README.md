# Notion Now

适用于 Noctalia v5.4.0 或更新版本（插件 API 43）的顶栏插件，读取 Notion 数据库。

## 已安装的功能

- 顶栏显示一项主日程、剩余分钟和额外活动数量 +N；默认选择最早结束的活动，并保持选择稳定。时间轴详情可将正在进行的活动固定到顶栏。
- 插件面板内置设置，右键直接打开设置；支持开关、预览日程切换通知。
- 显示模式：主日程或自动轮播（2–15 秒）。顶栏滚轮切换重叠活动，手动切换暂停轮播 30 秒，悬停暂停轮播。标题短暂淡入淡出并轻移，胶囊随内容平滑伸缩；标题长度可设 8–28 字。
- 当前活动默认使用主题强调色，可在插件设置中关闭，恢复普通文字颜色。
- 单例后台服务每 5 秒检查日程边界；同时开始和结束合并通知。初次启动、长时间休眠恢复、缓存过期或同步新增记录不补发旧提示。
- 没有当前活动时显示下一项，查询范围为今天和明天。
- 点击展开今日时间轴；右键打开插件设置。面板内也有连接和刷新按钮。
- 每两分钟拉取数据，顶栏本地每半秒检查活动状态；动画期间目标 60 Hz。
- 全天活动与没有结束时间的 Notion 任务不绘入时间轴，也不会被当作正在进行的活动。
- 同步失败保留已有缓存，明确标记缓存和异常。
- 密钥及日程缓存仅存于本机，目录权限 700、文件权限 600。

## 安装

```sh
python3 install.py
```

安装器适用于 Linux、systemd 用户服务和上述 Noctalia 版本。画布需要 Python 的 cairo 模块（Arch Linux 包名 `python-cairo`）与支持中文的字体。

活动进度条默认开启，按当前活动已经过的时间比例显示；进度跟随当前显示的主日程。可在插件设置中关闭，悬停查看对应活动和百分比。

进度条支持临近结束变色，默认剩余 5 分钟时变为橙色，可调整为 1–30 分钟或关闭；只改变进度条颜色，不弹出额外通知。缓存过期或活动同步失败时不显示临近结束颜色。

今日迷你时间轴在日程面板顶部显示：橙色游标表示现在，时间重叠的活动分行；点击色块查看名称、时间和原页面入口。全天事项与无结束时间的任务不绘入时间轴，跨日活动在当天范围内裁切显示。面板仅保留时间轴与选中活动详情，不再显示下方日程列表；时间轴位于可滚动区域，不改变顶栏宽度。

时间轴现使用原生像素画布：在刻度和活动区按住左键直接拖动，松开带轻微惯性；滚轮以鼠标下的时间点为锚连续缩放（45 分钟至 24 小时）。「现在」平滑回到当前前后两小时，「全天」平滑展示完整一天。点击色块选中日程，详情短暂淡入；右下角进入原生设置。所有操作只调整本机显示，不修改 Notion。

## 第一次连接

点击插件面板的「设置」或右键顶栏组件，即可调整显示模式、标题长度和切换提示。
首次连接和重新授权：在插件设置中点击「连接 / 重新授权」，或打开 <http://127.0.0.1:18743>。

### Notion

1. 在 <https://www.notion.so/profile/integrations> 创建内部集成，仅启用读取内容能力。
2. 在要显示的数据库中通过「连接」添加集成，给该集成读取权限。
3. 将集成密钥填入本机连接页面，可指定数据库链接；留空时查找已共享的数据源。
4. 数据库有多个日期字段时，填写 `数据库链接 | 日期字段名称`，选择 Notion Calendar 使用的字段。
5. 保存后刷新连接页面确认「已同步」。有开始、结束时间的日期范围才能成为当前活动。

## 本机位置

- 插件：`~/.config/noctalia/plugins/notion-now/`
- 密钥和配置：`~/.config/notion-now/config.json`
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
lua test_timeline.lua .
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

Python 日历及画布逻辑的 21 项测试通过；Noctalia 插件 lint 无警告；顶栏和面板的 IPC health 检查通过；定时器和连接页面运行正常。

本插件读取数据源，不读取 Notion Calendar 的显示/隐藏配置或数据库视图过滤器。请在插件中指定需要的 Notion 数据库。
Notion 通过起始日期上界查询并在本地检查时间区间，覆盖提前开始的跨日活动；历史数据特别多的数据库同步会更慢。
不同来源的同名活动会分别显示；没有共同标识的活动不擅自合并。

官方资料：
- <https://docs.noctalia.dev/noctalia/plugins/development/>
- <https://developers.notion.com/reference/query-a-data-source>

已修复设置开关回调的字符串布尔值转换；强调色与切换提示均可正确关闭并保存。

画布通过同用户私有 Unix socket 与 Noctalia 共享内存传输，RGBA 像素不会经过 Luau JSON；活动时目标 60 Hz，静止时降低更新频率，面板关闭后停止出帧。`canvas_panel.py` 不读取凭证，也不访问网络。

设置页按「顶栏 / 提醒 / 连接」分组，数值使用加减按钮，修改后自动保存。主画布设置按钮直接进入原生设置，不依赖后台状态轮询；写入失败会显示提示并保持原配置。

顶栏由 `bar_canvas.py` 绘制，通过私有 Unix socket `bar.sock` 传输；宽度采用保留速度的临界阻尼动画，支持多个显示端。该进程仅读取本机缓存和显示偏好，不访问网络。
