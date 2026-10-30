local root = arg[1]
local modules = {}
require = function(path)
 if not modules[path] then modules[path] = assert(loadfile(root .. '/' .. path))() end
 return modules[path]
end
local prefs = {max_visible = 1, notify_switch = true}
local notifications = {}
local data = {}
local text = ''
local now = 1791367200
local rendered = nil
noctalia = {
  expandPath = function(p) return p end,
  readFile = function(path) return path:find('preferences') and 'prefs' or '{}' end,
  writeFile = function(_) end,
  notify = function(title, body) table.insert(notifications, {title, body}) end,
  json = { decode = function(raw) return raw == 'prefs' and prefs or data end, encode = function(_) return '{}' end },
  nowMs = function() return now * 1000 end,
  formatTime = function(pattern, epoch, tz)
    if pattern == '{:%Y-%m-%d}' then return '2026-10-07' end
    return '18:00'
  end,
  setUpdateInterval = function(_) end,
  pluginDir = function() return root end,
  runAsync = function(_) end,
}
barWidget = {
  render = function(tree)
    rendered = tree
    text = tree.children[2].props.text
  end,
  setGlyph = function(_) end,
  setText = function(t) text = t end,
  setTooltip = function(_) end,
  setColor = function(_) end,
}
ui = setmetatable({}, {__index = function(_, tag)
  return function(props, children) return {tag = tag, props = props, children = children} end
end})
panel = {render = function(tree) rendered = tree end}

data = {updated = now, sources = {}, events = {}}
dofile(root .. '/widget.luau')
assert(text == '连接日历', text)
data.sources = {google = {connected = true, ok = true, message = '已同步'}}
data.events = {
  {id = 'one', provider = 'google', title = '专注处理项目事项并整理会议记录以及计划', calendar = '工作', start = now - 60, ['end'] = now + 600, all_day = false, point = false},
  {id = 'two', provider = 'notion', title = '另一个活动', calendar = '任务', start = now - 20, ['end'] = now + 1200, all_day = false, point = false},
  {id = 'all', provider = 'google', title = '全天事项', calendar = '生活', start = now - 3600, ['end'] = now + 3600, all_day = true, point = false},
}
update()
assert(text:find('10 分钟', 1, true), text)
assert(text:find('+1', 1, true), text)
assert(utf8.len(text), 'invalid UTF-8 title truncation')
prefs.max_visible = 2
update()
assert(text:find('另一个活动', 1, true), text)
assert(not text:find('+1', 1, true), text)
prefs.display_mode = 'rotate'
prefs.fixed_width = 260
prefs.rotate_seconds = 5
update()
assert(rendered.children[2].props.width == 260)
now = now + 5
update()
assert(text:find('另一个活动', 1, true), text)
assert(rendered.children[2].props.width == 260)
prefs.display_mode = 'scroll'
update()
local scrollText = text
now = now + 1
update()
assert(text ~= scrollText)
assert(utf8.len(text))
assert(rendered.children[2].props.width == 260)
prefs.accent_color = false
update()
assert(rendered.children[2].props.color == 'on_surface')
prefs.display_mode = 'parallel'
prefs.max_visible = 1
data.events[1].stale = true
data.sources.google.ok = false
update()
assert(text:find('缓存', 1, true), text)
assert(text:find('!', 1, true), text)

dofile(root .. '/panel.luau')
assert(rendered.tag == 'column')
local function flattened(node)
  local parts = {node.props and node.props.text or ''}
  for _, child in ipairs(node.children or {}) do table.insert(parts, flattened(child)) end
  return table.concat(parts, '\n')
end
local labels = flattened(rendered)
assert(labels:find('正在进行', 1, true), labels)
assert(labels:find('全天事项', 1, true), labels)
assert(labels:find('缓存', 1, true), labels)
data.events = {{id = 'point', provider = 'notion', title = '只有开始时间', calendar = '任务',
  start = now + 60, ['end'] = now + 60, all_day = false, point = true}}
update()
labels = flattened(rendered)
assert(labels:find('未设置结束时间', 1, true), labels)
assert(not labels:find('正在进行', 1, true), labels)
print('UI behavior checks passed: active, overlap, UTF-8, stale, all-day, point events')

-- Known simultaneous end/start boundaries notify once; edits, stale cache,
-- initial load, disabling, and resume after a long gap never replay reminders.
data = {updated = now, sources = {notion = {ok = true}}, events = {
 {id = 'old', provider = 'notion', title = '上一项', start = now - 60, ['end'] = now + 5},
 {id = 'new', provider = 'notion', title = '下一项', start = now + 5, ['end'] = now + 60},
}}
dofile(root .. '/service.luau')
assert(#notifications == 0)
now = now + 5
update()
assert(#notifications == 1)
assert(notifications[1][2]:find('已结束：上一项', 1, true))
assert(notifications[1][2]:find('开始：下一项', 1, true))
update()
assert(#notifications == 1)
prefs.notify_switch = false
now = now + 55
update()
assert(#notifications == 1)
prefs.notify_switch = true
now = now + 120
update()
assert(#notifications == 1)
print('Switch notification checks passed')
