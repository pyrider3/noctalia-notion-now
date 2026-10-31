--!nonstrict
local preferences = require("./preferences.luau")
local state = noctalia.expandPath("~/.local/state/notion-now/")
local input = {session = noctalia.nowMs(), wheel = 0, hovered = false}
local lastWidth, lastColor, lastTooltip = nil, nil, nil
local lastSkin, lastStart = 0, 0
local color = "on_surface"
local function sendInput()
    noctalia.writeFile(state .. "bar-input.json", noctalia.json.encode(input))
end
local function start()
    noctalia.runAsync({"python3", noctalia.pluginDir() .. "/bar_canvas.py"})
    lastStart = noctalia.nowMs()
end
function barHover(value)
    input.hovered = value == "true" or value == true
    sendInput()
end
function onHover(value)
    barHover(value)
end
function onScroll(axis, steps, startsGesture)
    input.wheel = input.wheel + (tonumber(steps) or 0)
    sendInput()
end
function update()
    local now = noctalia.nowMs()
    if now - lastSkin > 1000 then
        local prefs = preferences.read()
        local foreground = noctalia.getColor("on_surface") or "#e9e9e6"
        local accent = noctalia.getColor("primary") or "#edb69b"
        noctalia.writeFile(state .. "bar-skin.json", noctalia.json.encode({text = foreground, accent = accent}))
        color = prefs.accent_color and "primary" or "on_surface"
        lastSkin = now
    end
    local raw = noctalia.readFile(state .. "bar-status.json")
    local status = raw and noctalia.json.decode(raw) or {}
    if type(status) ~= "table" then status = {} end
    if now - (status.updated or 0) * 1000 > 3000 and now - lastStart > 5000 then start() end
    local width = math.max(64, math.min(430, tonumber(status.width) or 100))
    if width ~= lastWidth or color ~= lastColor then
        barWidget.render(ui.row({key = "primary-activity", gap = 6, align = "center"}, {
            ui.glyph({name = "calendar", size = 16, color = color}),
            ui.pixelStream({key = "bar-canvas", path = state .. "bar.sock", width = width, height = 28}),
        }))
        lastWidth, lastColor = width, color
    end
    local tooltip = (status.tooltip or "正在连接 Notion 日程") .. "\n滚轮切换活动 · 点击查看时间轴 · 右键设置"
    if tooltip ~= lastTooltip then barWidget.setTooltip(tooltip) lastTooltip = tooltip end
end
function onClick()
    noctalia.togglePanel("pyrider3/notion-now:agenda")
end
function onIpc(event)
    if event == "health" then
        update()
        noctalia.writeFile(state .. "widget-health.json", noctalia.json.encode({ok = true, timestamp = noctalia.nowMs()}))
    end
end
sendInput()
start()
noctalia.setUpdateInterval(16)
update()
