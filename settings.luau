--!nonstrict
local M = {}
local BG, TEXT, MUTED = "#171a1f", "#e9e9e6", "#9da5b0"
local function label(text, size, color, weight)
    return ui.label({text = text, fontSize = size or 14, color = color or TEXT, fontWeight = weight or "normal", maxLines = 2})
end
function M.render(prefs, tab, status, saved, callbacks)
    local function change(key, value)
        prefs[key] = value
        callbacks.save(prefs)
    end
    local function toggle(title, hint, key)
        return ui.row({gap = 16, align = "center", paddingV = 5}, {
            ui.column({flexGrow = 1, gap = 5}, hint and {label(title, 14), label(hint, 12, MUTED)} or {label(title, 14)}),
            ui.toggle({checked = prefs[key], onChange = function(value) change(key, value == true or value == "true") end}),
        })
    end
    local function stepper(title, key, low, high, step, suffix)
        return ui.row({gap = 8, align = "center", paddingV = 4}, {
            ui.label({text = title, color = TEXT, fontSize = 14, flexGrow = 1}),
            ui.button({text = "−", variant = "ghost", controlSize = "sm", width = 40, enabled = prefs[key] > low,
                onClick = function() change(key, math.max(low, prefs[key] - step)) end}),
            ui.label({text = tostring(prefs[key]) .. suffix, color = TEXT, fontSize = 13, width = 76, textAlign = "center"}),
            ui.button({text = "+", variant = "ghost", controlSize = "sm", width = 40, enabled = prefs[key] < high,
                onClick = function() change(key, math.min(high, prefs[key] + step)) end}),
        })
    end
    local tabs = {}
    for _, item in ipairs({{"bar", "顶栏"}, {"reminders", "提醒"}, {"connection", "连接"}}) do
        local id = item[1]
        table.insert(tabs, ui.button({text = item[2], flexGrow = 1, controlSize = "sm", selected = tab == id,
            variant = tab == id and "secondary" or "ghost", onClick = function() callbacks.tab(id) end}))
    end
    local content = {}
    if tab == "bar" then
        table.insert(content, label("活动如何显示", 16, TEXT, "semibold"))
        table.insert(content, label("同时显示几项由你设置，超出的活动显示 +N。", 12, MUTED))
        local modes = {}
        for _, item in ipairs({{"pinned", "主日程"}, {"parallel", "同时显示"}, {"rotate", "自动轮播"}}) do
            local id = item[1]
            table.insert(modes, ui.button({text = item[2], flexGrow = 1, controlSize = "sm", selected = prefs.display_mode == id,
                variant = prefs.display_mode == id and "primary" or "ghost", onClick = function() change("display_mode", id) end}))
        end
        table.insert(content, ui.row({gap = 8, paddingV = 6}, modes))
        if prefs.display_mode == "parallel" then
            table.insert(content, stepper("同时显示数量", "max_visible", 1, 5, 1, " 项"))
        end
        table.insert(content, stepper("标题最多显示", "title_limit", 8, 28, 1, " 字"))
        table.insert(content, label("胶囊随内容平滑伸缩，悬停暂停轮播。", 12, MUTED))
        if prefs.display_mode == "rotate" then
            table.insert(content, stepper("轮播间隔", "rotate_seconds", 2, 15, 1, " 秒"))
        end
        table.insert(content, ui.separator())
        table.insert(content, toggle("主题强调色", nil, "accent_color"))
        table.insert(content, toggle("活动进度条", nil, "show_progress"))
    elseif tab == "reminders" then
        table.insert(content, label("在合适的时候提醒", 16, TEXT, "semibold"))
        table.insert(content, label("保持轻提示，不打断正在做的事。", 12, MUTED))
        table.insert(content, toggle("临近结束变色", "剩余时间不足时，进度条变为橙色", "end_warning"))
        if prefs.end_warning then table.insert(content, stepper("提前多久", "end_warning_minutes", 1, 30, 1, " 分钟")) end
        table.insert(content, ui.separator())
        table.insert(content, toggle("日程切换通知", "活动开始或结束时，发送一条通知", "notify_switch"))
        table.insert(content, ui.button({text = "预览切换通知", glyph = "bell", variant = "secondary", controlSize = "sm", onClick = callbacks.preview}))
    else
        table.insert(content, label("Notion 数据库", 16, TEXT, "semibold"))
        table.insert(content, label(status.ok and "●  已连接 · 自动同步中" or "●  " .. (status.message or "尚未连接"), 13, status.ok and "#9bb9a7" or "#edb69b"))
        table.insert(content, ui.separator())
        table.insert(content, label("每两分钟读取一次最新日程。", 14))
        table.insert(content, label("连接已有数据库，或调整要读取的数据源。密钥保存在本机。", 13, MUTED))
        table.insert(content, ui.button({text = "管理 Notion 连接", glyph = "external-link", variant = "secondary", onClick = callbacks.authorize}))
        table.insert(content, ui.button({text = "立即同步", glyph = "refresh", variant = "ghost", onClick = callbacks.refresh}))
    end
    return ui.column({key = "preferences-v2", width = 536, height = 500, padding = 24, gap = 14, fill = BG, radius = 28}, {
        ui.row({gap = 12, align = "center"}, {
            ui.column({gap = 4, flexGrow = 1}, {label("偏好设置", 22, TEXT, "bold"), label("日历，此刻", 12, MUTED)}),
            ui.button({text = "返回日程", glyph = "arrow-left", controlSize = "sm", variant = "ghost", onClick = callbacks.back}),
        }),
        ui.row({gap = 6, fill = "#20252c", radius = 16, padding = 4}, tabs),
        ui.scroll({key = "settings-" .. tab, flexGrow = 1, gap = 5}, content),
        ui.separator(),
        label(saved == "failed" and "保存失败，请重试" or (saved and "●  已自动保存" or "修改后自动保存"), 12, saved == "failed" and "#e9ad52" or MUTED),
    })
end
return M
