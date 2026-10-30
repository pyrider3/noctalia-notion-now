--!nonstrict
local preferences = require("./preferences.luau")
local rotationKey, rotationStart = "", 0
local cache = noctalia.expandPath("~/.local/state/notion-now/events.json")

local function shorten(text, limit)
    local length = utf8.len(text)
    if length and length > limit then
        return string.sub(text, 1, utf8.offset(text, limit + 1) - 1) .. "…"
    end
    return text
end

function update()
    local raw = noctalia.readFile(cache)
    local data = raw and noctalia.json.decode(raw)
    local prefs = preferences.read()
    local color = "on_surface"
    if type(data) ~= "table" then
        barWidget.render(ui.row({ gap = 6, align = "center" }, { ui.glyph({name = "calendar", size = 16}), ui.label({text = "连接日历"}) }))
        barWidget.setTooltip("Notion Now · 点击查看，右键连接日历")
        return
    end
    local now = noctalia.nowMs() / 1000
    local active, upcoming = {}, nil
    local hasConnected, hasError = false, false
    for _, status in pairs(data.sources or {}) do
        if status.connected then hasConnected = true end
        if status.connected and not status.ok then hasError = true end
    end
    local outdated = now - (data.updated or 0) > 600
    for _, event in ipairs(data.events or {}) do
        if not event.all_day then
            if not event.point and event.start <= now and now < event["end"] then
                table.insert(active, event)
            elseif event.start > now and (not upcoming or event.start < upcoming.start) then
                upcoming = event
            end
        end
    end
    table.sort(active, function(a, b)
        if a["end"] == b["end"] then return a.id < b.id end
        return a["end"] < b["end"]
    end)
    local keys = {prefs.display_mode}
    for _, item in ipairs(active) do table.insert(keys, item.id) end
    local key = table.concat(keys, "|")
    if key ~= rotationKey then rotationKey, rotationStart = key, now end
    local shown = active[1]
    local text, tooltip
    if #active > 0 then
        local event = active[1]
        local parts = {}
        local limit = prefs.max_visible
        for i = 1, math.min(#active, limit) do
            local item = active[i]
            table.insert(parts, shorten(item.title, 16) .. " · " .. tostring(math.max(1, math.ceil((item["end"] - now) / 60))) .. " 分钟")
        end
        text = table.concat(parts, "  /  ")
        if #active > limit then text = text .. " +" .. tostring(#active - limit) end
        if prefs.display_mode == "rotate" then
            local index = math.floor((now - rotationStart) / prefs.rotate_seconds) % #active + 1
            shown = active[index]
            text = shown.title .. " · " .. tostring(math.max(1, math.ceil((shown["end"] - now) / 60))) .. " 分钟"
            if #active > 1 then text = tostring(index) .. "/" .. tostring(#active) .. " · " .. text end
        elseif prefs.display_mode == "scroll" then
            local full = {}
            for _, item in ipairs(active) do
                table.insert(full, item.title .. " · " .. tostring(math.max(1, math.ceil((item["end"] - now) / 60))) .. " 分钟")
            end
            local line = table.concat(full, "    /    ") .. "        "
            local length = utf8.len(line) or #line
            local offset = math.floor((now - rotationStart) * 3) % length
            local doubled = line .. line .. line
            local finish = math.min(offset + 32, utf8.len(doubled))
            text = string.sub(doubled, utf8.offset(doubled, offset + 1), (utf8.offset(doubled, finish + 1) or (#doubled + 1)) - 1)
        end
        tooltip = "正在进行（按日程时间）\n"
        for _, item in ipairs(active) do
            tooltip = tooltip .. item.title .. " · " .. item.calendar .. "\n"
        end
        color = prefs.accent_color and "primary" or "on_surface"
    elseif upcoming then
        text = "下一项 " .. shorten(upcoming.title, 14) .. " · " .. noctalia.formatTime("{:%H:%M}", upcoming.start, data.timezone)
        tooltip = upcoming.title .. "\n" .. upcoming.calendar .. "\n" .. noctalia.formatTime("{:%m月%d日 %H:%M}", upcoming.start, data.timezone)
        color = "on_surface"
    elseif hasConnected then
        text, tooltip = "暂无活动", "今天和明天暂无后续定时活动"
        color = "on_surface"
    else
        text, tooltip = "连接日历", "点击打开日程面板，右键打开本机连接页面"
        color = "on_surface"
    end
    if hasError or outdated then
        text = text .. " !"
        tooltip = tooltip .. "\n同步异常或缓存过期；请在面板查看连接状态"
    end
    if (#active > 0 and ((shown and shown.stale) or (prefs.display_mode == "scroll" and hasError))) or (upcoming and #active == 0 and upcoming.stale) or outdated then
        text = "缓存 · " .. text
    end
    local label = { text = text, color = color, maxLines = 1 }
    if prefs.display_mode ~= "parallel" then label.width = prefs.fixed_width end
    barWidget.render(ui.row({ gap = 6, align = "center" }, {
        ui.glyph({ name = "calendar", size = 16, color = color }), ui.label(label),
    }))
    noctalia.setUpdateInterval(prefs.display_mode == "scroll" and #active > 0 and 250 or 1000)
    barWidget.setTooltip(tooltip .. "\n点击展开 · 右键设置")
end

function onClick()
    noctalia.togglePanel("pyrider3/notion-now:agenda")
end

function onIpc(event)
    if event == "health" then
        update()
        noctalia.writeFile(noctalia.expandPath("~/.local/state/notion-now/widget-health.json"),
            noctalia.json.encode({ ok = true, timestamp = noctalia.nowMs() }))
    end
end

noctalia.setUpdateInterval(15000)
update()
