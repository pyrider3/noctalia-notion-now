--!nonstrict
local M = {}
local function minute(epoch, tz)
    local hour = tonumber(noctalia.formatTime("{:%H}", epoch, tz)) or 0
    local min = tonumber(noctalia.formatTime("{:%M}", epoch, tz)) or 0
    return hour * 60 + min
end
function M.build(data, now, tz)
    local today = noctalia.formatTime("{:%Y-%m-%d}", now, tz)
    local model = { lanes = {}, events = {}, first = 360, last = 1320, now = minute(now, tz), overlaps = 0 }
    for _, event in ipairs(data.events or {}) do
        if not event.all_day and not event.point and event["end"] > event.start then
            local startDay = noctalia.formatTime("{:%Y-%m-%d}", event.start, tz)
            local endDay = noctalia.formatTime("{:%Y-%m-%d}", event["end"], tz)
            if startDay <= today and endDay >= today then
                local start = startDay < today and 0 or minute(event.start, tz)
                local finish = endDay > today and 1440 or minute(event["end"], tz)
                if finish > start then
                    table.insert(model.events, {event = event, start = start, finish = finish})
                    model.first = math.min(model.first, start)
                    model.last = math.max(model.last, finish)
                end
            end
        end
    end
    model.first = math.floor(math.min(model.first, model.now) / 60) * 60
    model.last = math.min(1440, math.ceil(math.max(model.last, model.now + 1) / 60) * 60)
    table.sort(model.events, function(a,b)
        if a.start == b.start then
            if a.finish == b.finish then return a.event.id < b.event.id end
            return a.finish < b.finish
        end
        return a.start < b.start
    end)
    local occupiedUntil = -1
    for _, item in ipairs(model.events) do
        local laneIndex = nil
        for index, lane in ipairs(model.lanes) do
            if lane[#lane].finish <= item.start then laneIndex = index break end
        end
        if not laneIndex then table.insert(model.lanes, {}) laneIndex = #model.lanes end
        table.insert(model.lanes[laneIndex], item)
        item.lane = laneIndex
        if item.start < occupiedUntil then model.overlaps = model.overlaps + 1 end
        occupiedUntil = math.max(occupiedUntil, item.finish)
    end
    return model
end
-- View state is separate from the event data: navigation never edits Notion.
function M.viewport(view)
    local span = math.max(60, math.min(1440, tonumber(view and view.span) or 1440))
    local first = math.max(0, math.min(1440 - span, tonumber(view and view.first) or 0))
    return { first = first, span = span }
end
function M.zoom(view, span, nowMinute)
    local old = M.viewport(view)
    local center = old.span == 1440 and nowMinute or old.first + old.span / 2
    return M.viewport({span = span, first = center - span / 2})
end
function M.window(model, view)
    local v = M.viewport(view)
    local result = { first = v.first, last = v.first + v.span, now = model.now, lanes = {}, events = {} }
    for _, lane in ipairs(model.lanes) do
        local visible = {}
        for _, item in ipairs(lane) do
            local first, last = math.max(item.start, result.first), math.min(item.finish, result.last)
            if last > first then
                local clipped = {event = item.event, start = first, finish = last}
                table.insert(visible, clipped)
                table.insert(result.events, clipped)
            end
        end
        if #visible > 0 then table.insert(result.lanes, visible) end
    end
    table.sort(result.events, function(a,b)
        if a.start == b.start then return a.event.id < b.event.id end
        return a.start < b.start
    end)
    return result
end
function M.render(data, now, tz, selectedId, onSelect, view, onViewChange)
    local base = M.build(data, now, tz)
    local viewport = M.viewport(view)
    local model = view and M.window(base, viewport) or base
    local width, height = 352, 20
    local function x(value) return (value - model.first) / (model.last - model.first) * width end
    local children = {
        ui.row({align = "center", gap = 8}, {
            ui.label({text = "今日时间轴", fontSize = 15, fontWeight = "semibold", flexGrow = 1}),
            ui.label({text = "现在 " .. noctalia.formatTime("{:%H:%M}", now, tz), fontSize = 12, color = "on_surface_variant"}),
        }),
    }
    if onViewChange then
        table.insert(children, ui.row({gap = 6, align = "center"}, {
            ui.label({text = "范围 " .. tostring(viewport.span / 60) .. " 小时", fontSize = 12, flexGrow = 1}),
            ui.button({text = "−", controlSize = "sm", variant = "ghost", enabled = viewport.span < 1440,
                onClick = function() onViewChange(M.zoom(viewport, viewport.span * 2, base.now)) end}),
            ui.button({text = "+", controlSize = "sm", variant = "ghost", enabled = viewport.span > 60,
                onClick = function() onViewChange(M.zoom(viewport, viewport.span / 2, base.now)) end}),
            ui.button({text = "全天", controlSize = "sm", variant = "ghost",
                onClick = function() onViewChange({first = 0, span = 1440}) end}),
            ui.button({text = "现在", controlSize = "sm", variant = "secondary",
                onClick = function()
                    local span = math.min(viewport.span, 360)
                    onViewChange(M.viewport({first = base.now - span / 2, span = span}))
                end}),
        }))
    end
    local ticks = {}
    for i = 0, 4 do
        local t = model.first + (model.last - model.first) * i / 4
        local caption = string.format("%02d:%02d", math.floor(t / 60), math.floor(t % 60))
        table.insert(ticks, ui.label({text = caption, fontSize = 11, color = "on_surface_variant",
            textAlign = i == 0 and "left" or (i == 4 and "right" or "center")}))
    end
    table.insert(children, ui.row({gap = 0, width = width, justify = "space_between"}, ticks))
    local marker = math.max(0, math.min(width - 2, x(model.now)))
    if model.now >= model.first and model.now <= model.last then
    table.insert(children, ui.row({gap = 0, width = width, height = 3}, {
        ui.box({width = marker, height = 3, fill = "surface_variant"}),
        ui.box({width = 2, height = 3, fill = "#e9ad52"}),
        ui.box({width = width - marker - 2, height = 3, fill = "surface_variant"}),
    }))
    end
    local selected = nil
    for _, item in ipairs(model.events) do
        if item.event.id == selectedId then selected = item end
    end
    if not selected then
        for _, item in ipairs(model.events) do
            if item.event.start <= now and now < item.event["end"] then selected = item break end
        end
        if not selected then
            for _, item in ipairs(model.events) do if item.event.start > now then selected = item break end end
        end
        selected = selected or model.events[#model.events]
    end
    for index, lane in ipairs(model.lanes) do
        local blocks, cursor = {}, 0
        for _, item in ipairs(lane) do
            local event = item.event
            local left, right = x(item.start), x(item.finish)
            if left > cursor then table.insert(blocks, ui.box({width = left - cursor, height = height, fill = "surface_variant"})) end
            local active = event.start <= now and now < event["end"]
            local fill = active and "primary" or (event["end"] <= now and "on_surface_variant" or "#64748b")
            table.insert(blocks, ui.box({key = event.id, width = right - left, height = height, fill = fill, radius = 3,
                opacity = event.stale and 0.45 or (event["end"] <= now and 0.55 or 1),
                border = selected and selected.event.id == event.id and "on_surface" or fill,
                borderWidth = selected and selected.event.id == event.id and 1 or 0,
                onClick = function() onSelect(event.id) end}))
            cursor = right
        end
        if cursor < width then table.insert(blocks, ui.box({width = width - cursor, height = height, fill = "surface_variant"})) end
        table.insert(children, ui.row({key = "lane-" .. tostring(index), gap = 0, width = width, height = height}, blocks))
    end
    if onViewChange then
        table.insert(children, ui.slider({key = "timeline-pan", min = 0, max = math.max(1, 1440 - viewport.span), step = 1,
            value = viewport.first, width = width, controlSize = "sm", enabled = viewport.span < 1440,
            onChange = function(value)
                onViewChange(M.viewport({first = tonumber(value) or viewport.first, span = viewport.span}))
            end}))
    end
    if selected then
        local event = selected.event
        local timing = noctalia.formatTime("{:%H:%M}", event.start, tz) .. "–" .. noctalia.formatTime("{:%H:%M}", event["end"], tz)
        local url = event.url
        table.insert(children, ui.label({text = event.title, fontSize = 13, fontWeight = "semibold", maxLines = 2}))
        table.insert(children, ui.row({align = "center", gap = 8}, {
            ui.label({text = (event.stale and "缓存 · " or "") .. timing .. " · " .. event.calendar,
                fontSize = 12, maxLines = 2, color = "on_surface_variant", flexGrow = 1}),
            ui.button({glyph = "external-link", variant = "ghost", controlSize = "sm",
                enabled = type(url) == "string" and string.sub(url, 1, 8) == "https://",
                onClick = function() if type(url) == "string" and string.sub(url, 1, 8) == "https://" then noctalia.runAsync({"xdg-open", url}) end end}),
        }))
    else
        table.insert(children, ui.label({text = #base.events > 0 and "这个时段暂无活动" or "今天暂无定时活动", fontSize = 13, color = "on_surface_variant"}))
    end
    if onViewChange then
        table.insert(children, ui.label({text = "＋放大 · −缩小 · 拖动滑条查看其他时段", fontSize = 11, color = "on_surface_variant"}))
    end
    table.insert(children, ui.label({text = #model.lanes > 1 and "多行表示时间重叠 · 空白处为空闲 · 点击色块查看" or "空白处为空闲 · 点击色块查看", fontSize = 11, color = "on_surface_variant"}))
    return ui.column({key = "today-timeline", gap = 6, padding = 10, radius = 12, minHeight = onViewChange and (285 + math.max(0, #model.lanes - 1) * 26) or 0, fill = "surface_variant"}, children)
end
return M
