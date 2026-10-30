--!nonstrict
local preferences = require("./preferences.luau")
local settingsView = false
local cache = noctalia.expandPath("~/.local/state/notion-now/events.json")
local script = noctalia.pluginDir() .. "/calendar_bridge.py"
local busy = false

function connect()
    settingsView = not settingsView
    update()
end
function authorize()
    noctalia.runAsync({ "python3", script, "setup" })
end
function testNotification()
    noctalia.notify("日程切换 · 示例", "已结束：上一项日程\n开始：下一项日程")
end

function refresh()
    if busy then return end
    busy = true
    update()
    noctalia.runAsync({ "systemctl", "--user", "start", "notion-now-sync.service" }, function(result)
        busy = false
        update()
    end, 60000)
end

function update()
    local raw = noctalia.readFile(cache)
    local data = (raw and noctalia.json.decode(raw)) or {}
    if type(data) ~= "table" then data = {} end
    local now = noctalia.nowMs() / 1000
    local tz = data.timezone or "Asia/Shanghai"
    local children = {
        ui.row({ gap = 10, align = "center" }, {
            ui.glyph({ name = "calendar", size = 24, color = "primary" }),
            ui.label({ text = "日历，此刻", fontSize = 22, fontWeight = "bold", flexGrow = 1 }),
            ui.button({ glyph = "refresh", text = busy and "同步中" or "刷新", variant = "ghost", onClick = "refresh", enabled = not busy }),
        }),
        ui.label({ text = noctalia.formatTime("{:%m月%d日 %H:%M}", now, tz), color = "on_surface_variant", fontSize = 13 }),
        ui.separator(),
    }
    for _, provider in ipairs({ "google", "notion" }) do
        local status = (data.sources or {})[provider] or { message = "尚未连接", ok = false }
        local name = provider == "google" and "Google 日历" or "Notion 数据库"
        table.insert(children, ui.label({ text = name .. " · " .. status.message, fontSize = 12,
            color = status.ok and "primary" or "on_surface_variant", maxLines = 2 }))
    end
    if now - (data.updated or now) > 600 then
        table.insert(children, ui.label({ text = "缓存已过期，请刷新；下方为上次保存的日程", color = "error", fontSize = 12 }))
    end
    if settingsView then
        local prefs = preferences.read()
        local choices = {}
        for i = 1, 5 do
            local count = i
            table.insert(choices, ui.button({ text = tostring(count), selected = prefs.max_visible == count,
                variant = prefs.max_visible == count and "primary" or "secondary",
                onClick = function() prefs.max_visible = count preferences.save(prefs) update() end }))
        end
        table.insert(children, ui.label({ text = "插件设置", fontSize = 18, fontWeight = "bold" }))
        local modes = {}
        for _, mode in ipairs({ {"parallel", "并排"}, {"rotate", "定时切换"}, {"scroll", "滚动"} }) do
            local value = mode[1]
            table.insert(modes, ui.button({ text = mode[2], variant = prefs.display_mode == value and "primary" or "secondary",
                onClick = function() prefs.display_mode = value preferences.save(prefs) update() end }))
        end
        table.insert(children, ui.row({ gap = 8 }, modes))
        if prefs.display_mode == "parallel" then
            table.insert(children, ui.label({ text = "同时显示项数", fontSize = 13 }))
            table.insert(children, ui.row({ gap = 8 }, choices))
        else
            table.insert(children, ui.label({ text = "固定文字宽度 · " .. tostring(prefs.fixed_width) .. " px", fontSize = 13 }))
            table.insert(children, ui.slider({ min = 140, max = 420, step = 20, value = prefs.fixed_width,
                onChange = function(value) prefs.fixed_width = tonumber(value) or prefs.fixed_width preferences.save(prefs) update() end }))
            if prefs.display_mode == "rotate" then
                table.insert(children, ui.label({ text = "每 " .. tostring(prefs.rotate_seconds) .. " 秒切换", fontSize = 13 }))
                table.insert(children, ui.slider({ min = 2, max = 15, step = 1, value = prefs.rotate_seconds,
                    onChange = function(value) prefs.rotate_seconds = tonumber(value) or prefs.rotate_seconds preferences.save(prefs) update() end }))
            end
        end
        table.insert(children, ui.row({gap = 10, align = "center"}, {
            ui.label({text = "当前活动使用主题强调色", flexGrow = 1, fontSize = 13}),
            ui.toggle({checked = prefs.accent_color, onChange = function(value)
                prefs.accent_color = preferences.boolean(value) preferences.save(prefs) update()
            end}),
        }))
        table.insert(children, ui.row({ gap = 10, align = "center" }, {
            ui.label({ text = "日程切换提示", flexGrow = 1 }),
            ui.toggle({ checked = prefs.notify_switch, onChange = function(value)
                prefs.notify_switch = preferences.boolean(value) preferences.save(prefs) update()
            end }),
        }))
        table.insert(children, ui.button({ text = "预览切换提示", variant = "secondary", onClick = "testNotification" }))
        table.insert(children, ui.separator())
        table.insert(children, ui.label({ text = "账号连接", fontSize = 16, fontWeight = "semibold" }))
        table.insert(children, ui.label({ text = "账号已连接时无需打开网页。首次授权、授权过期或更换数据源时，打开连接页面。Google 授权由官方网页完成。", maxLines = 4, fontSize = 12, color = "on_surface_variant" }))
        table.insert(children, ui.button({ text = "连接 / 重新授权", onClick = "authorize", variant = "secondary" }))
        table.insert(children, ui.spacer({ flexGrow = 1 }))
        table.insert(children, ui.button({ text = "返回日程", onClick = "connect", variant = "primary" }))
        panel.render(ui.column({ padding = 18, height = 580 }, { ui.scroll({ flexGrow = 1, gap = 12 }, children) }))
        return
    end
    local today = noctalia.formatTime("{:%Y-%m-%d}", now, tz)
    local cards = {}
    local todayCount = 0
    for _, event in ipairs(data.events or {}) do
        local current = not event.all_day and not event.point and event.start <= now and now < event["end"]
        local isToday = noctalia.formatTime("{:%Y-%m-%d}", event.start, tz) == today
            or (event.start < now and event["end"] > now)
        if isToday or current then
            todayCount = todayCount + 1
            local timing = "全天"
            if not event.all_day then
                timing = noctalia.formatTime("{:%H:%M}", event.start, tz)
                if event.point then
                    timing = timing .. " · 未设置结束时间"
                else
                    timing = timing .. "–" .. noctalia.formatTime("{:%H:%M}", event["end"], tz)
                end
            end
            if current then
                timing = "正在进行 · " .. timing .. " · 剩余 " .. tostring(math.ceil((event["end"] - now) / 60)) .. " 分钟"
            elseif not event.all_day and event["end"] <= now then
                timing = "已结束 · " .. timing
            end
            if event.stale then timing = "缓存 · " .. timing end
            local url = event.url
            local rows = {
                ui.label({ text = event.title, fontSize = 15, fontWeight = "semibold", maxLines = 2,
                    color = current and "primary" or "on_surface" }),
                ui.label({ text = timing, fontSize = 12, color = "on_surface_variant", maxLines = 2 }),
                ui.row({ align = "center", gap = 8 }, {
                    ui.label({ text = (event.provider == "google" and "Google · " or "Notion · ") .. event.calendar,
                        fontSize = 11, color = "on_surface_variant", flexGrow = 1, maxLines = 1 }),
                    ui.button({ glyph = "external-link", variant = "ghost", enabled = type(url) == "string" and string.sub(url, 1, 8) == "https://",
                        onClick = function()
                            if type(url) == "string" and string.sub(url, 1, 8) == "https://" then
                                noctalia.runAsync({ "xdg-open", url })
                            end
                        end }),
                }),
            }
            table.insert(cards, ui.column({ key = event.id, gap = 6, padding = 12, fill = "surface_variant", radius = 12 }, rows))
        end
    end
    if todayCount == 0 then
        table.insert(cards, ui.column({ paddingV = 30, gap = 10, align = "center" }, {
            ui.glyph({ name = "calendar", size = 36, color = "on_surface_variant" }),
            ui.label({ text = "暂无今天的日程", fontSize = 16 }),
            ui.label({ text = "连接日历后，你现在的安排会显示在顶栏。", fontSize = 12, maxLines = 2, color = "on_surface_variant" }),
        }))
    end
    table.insert(children, ui.scroll({ flexGrow = 1, gap = 10 }, cards))
    table.insert(children, ui.separator())
    table.insert(children, ui.row({ gap = 10, align = "center" }, {
        ui.label({ text = data.updated and ("同步 " .. noctalia.formatTime("{:%H:%M}", data.updated, tz)) or "等待首次同步",
            fontSize = 11, color = "on_surface_variant", flexGrow = 1 }),
        ui.button({ text = "设置", glyph = "settings", variant = "secondary", onClick = "connect" }),
    }))
    panel.render(ui.column({ gap = 10, padding = 18, height = 580 }, children))
end

function onOpen() update() end
function onIpc(event)
    if event == "health" then
        update()
        noctalia.writeFile(noctalia.expandPath("~/.local/state/notion-now/panel-health.json"),
            noctalia.json.encode({ ok = true, timestamp = noctalia.nowMs() }))
    elseif event == "settings" then
        settingsView = true
        update()
        noctalia.runAsync({ "noctalia", "msg", "panel-open", "pyrider3/notion-now:agenda" })
    elseif event == "refresh" then
        refresh()
    end
end
noctalia.setUpdateInterval(15000)
update()
