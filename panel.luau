--!nonstrict
local preferences = require("./preferences.luau")
local settingsView = false
local settings = require("./settings.luau")
local settingsTab = "bar"
local settingsSaved = false
local cache = noctalia.expandPath("~/.local/state/notion-now/events.json")
local script = noctalia.pluginDir() .. "/calendar_bridge.py"
local busy = false
local opened = false
local canvasRendered = false
local canvasState = noctalia.expandPath("~/.local/state/notion-now/")
local input = {seq = 0, session = noctalia.nowMs(), down_serial = 0, released_serial = 0, pressed = false, x = 0, y = 0, wheel = 0, time = 0}
local function startCanvas()
    noctalia.runAsync({"python3", noctalia.pluginDir() .. "/canvas_panel.py"})
end
local function sendInput()
    input.seq = input.seq + 1
    input.time = noctalia.nowMs() / 1000
    noctalia.writeFile(canvasState .. "canvas-input.json", noctalia.json.encode(input))
end
function canvasMove(x, y)
    input.x, input.y = tonumber(x) or 0, tonumber(y) or 0
    sendInput()
end
function canvasDown(x, y)
    input.cancelled = false
    input.down_serial = input.down_serial + 1
    input.down_x, input.down_y = tonumber(x) or 0, tonumber(y) or 0
    input.down_time = noctalia.nowMs() / 1000
    input.pressed = true
    canvasMove(x, y)
end
function canvasUp(x, y)
    input.cancelled = false
    input.released_serial = input.down_serial
    input.pressed = false
    canvasMove(x, y)
    local px, py = input.x * 536, input.y * 500
    local distance = math.abs(input.x - (input.down_x or input.x)) * 536 + math.abs(input.y - (input.down_y or input.y)) * 500
    if distance <= 5 and px >= 454 and px <= 512 and py >= 451 and py <= 481 then
        settingsView = true
        settingsTab = "bar"
        canvasRendered = false
        update()
    end
end
function canvasCancel()
    input.cancelled = true
    input.released_serial = input.down_serial
    input.pressed = false
    sendInput()
end
function canvasScroll(dx, dy)
    input.wheel = input.wheel + (tonumber(dy) or 0)
    sendInput()
end


function connect()
    settingsView = not settingsView
    canvasRendered = false
    if not settingsView then startCanvas() end
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
    if not settingsView then
        if opened and not canvasRendered then
            panel.render(ui.column({key = "canvas-root", padding = 0, width = 536, height = 500, fill = "#171a1f", radius = 16}, {
                ui.pixelStream({key = "calendar-canvas", path = canvasState .. "canvas.sock", width = 536, height = 500,
                    radius = 16, onPointerDown = "canvasDown", onPointerMove = "canvasMove", onPointerUp = "canvasUp",
                    onPointerCancel = "canvasCancel", onScroll = "canvasScroll"}),
            }))
            canvasRendered = true
        end
        return
    end
    local raw = noctalia.readFile(cache)
    local data = raw and noctalia.json.decode(raw) or {}
    if type(data) ~= "table" then data = {} end
    local status = (data.sources or {}).notion or {}
    panel.render(settings.render(preferences.read(), settingsTab, status, settingsSaved, {
        save = function(value)
            local ok = preferences.save(value)
            settingsSaved = ok == false and "failed" or true
            update()
        end,
        tab = function(value) settingsTab = value update() end,
        back = connect,
        authorize = authorize,
        refresh = refresh,
        preview = testNotification,
    }))

end

function onOpen()
    opened = true
    canvasRendered = false
    input.pressed = false
    sendInput()
    if not settingsView then startCanvas() end
    update()
end
function onClose()
    opened = false
    canvasCancel()
    canvasRendered = false
    panel.render(ui.column({}))
end
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
