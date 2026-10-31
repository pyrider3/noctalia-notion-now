local root = arg[1]
local failWrite = false
local stored = {accent_color = 'false', notify_switch = 'false'}
local now = 1000
local cache = {updated = now, sources = {notion = {ok = true, message = '已同步'}}, events = {
 {id = 'one', provider = 'notion', title = '活动', calendar = '规划', start = 900, ['end'] = 1100}}}
local tree, widgetTree
noctalia = {
 expandPath = function(p) return p end,
 readFile = function(p) return p:find('preferences') and 'prefs' or 'cache' end,
 writeFile = function(p, v) if p:find("preferences") then if failWrite then return false end stored = v return true end end,
 json = {decode = function(v) return v == 'prefs' and stored or cache end, encode = function(v) return v end},
 nowMs = function() return now * 1000 end,
 pluginDir = function() return root end,
 formatTime = function() return '00:00' end,
 setUpdateInterval = function() end,
 runAsync = function() end,
}
ui = setmetatable({}, {__index = function(_,tag) return function(props,children) return {tag=tag,props=props,children=children} end end})
panel = {render = function(v) tree = v end}
barWidget = {render = function(v) widgetTree = v end, setTooltip = function() end}
local modules = {}
require = function(path)
 if not modules[path] then modules[path] = assert(loadfile(root .. '/' .. path))() end
 return modules[path]
end
local prefs = require('./preferences.luau')
assert(prefs.read().accent_color == false and prefs.read().notify_switch == false)
dofile(root .. '/panel.luau')
onIpc('settings')
local function toggle(node,label)
 if node.tag == 'row' and node.children and node.children[2] and node.children[2].tag == 'toggle' then
  local first = node.children[1]
  if first.props.text == label or (first.children and first.children[1].props.text == label) then return node.children[2] end
 end
 for _,child in ipairs(node.children or {}) do local found = toggle(child,label) if found then return found end end
end
for _,label in ipairs({'主题强调色','日程切换通知'}) do
 if label == '日程切换通知' then
  local function activateTab(node)
   if node.tag == 'button' and node.props.text == '提醒' then node.props.onClick() return true end
   for _,child in ipairs(node.children or {}) do if activateTab(child) then return true end end
  end
  assert(activateTab(tree))
 end
 local control = toggle(tree,label)
 assert(control.props.checked == false)
 control.props.onChange('true')
 control = toggle(tree,label)
 assert(control.props.checked == true)
 control.props.onChange('false')
 assert(toggle(tree,label).props.checked == false)
end
assert(stored.accent_color == false and stored.notify_switch == false)
dofile(root .. '/panel.luau')
onIpc('settings')
local function findButton(node, text)
 if node.tag == 'button' and node.props.text == text then return node end
 for _,child in ipairs(node.children or {}) do local found = findButton(child,text) if found then return found end end
end
findButton(tree,'顶栏').props.onClick()
failWrite = true
toggle(tree,'主题强调色').props.onChange('true')
assert(stored.accent_color == false)
local function hasText(node,text)
 if node.props and node.props.text == text then return true end
 for _,child in ipairs(node.children or {}) do if hasText(child,text) then return true end end
 return false
end
assert(hasText(tree,'保存失败，请重试'))
failWrite = false
toggle(tree,'主题强调色').props.onChange('true')
assert(stored.accent_color == true)
assert(hasText(tree,'●  已自动保存'))
toggle(tree,'主题强调色').props.onChange('false')
print('Settings save/retry checks passed: failure stays off, retry persists, saved feedback')
