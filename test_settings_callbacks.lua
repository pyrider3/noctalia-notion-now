local root = arg[1]
local stored = {accent_color = 'false', notify_switch = 'false'}
local now = 1000
local cache = {updated = now, sources = {notion = {ok = true, message = '已同步'}}, events = {
 {id = 'one', provider = 'notion', title = '活动', calendar = '规划', start = 900, ['end'] = 1100}}}
local tree, widgetTree
noctalia = {
 expandPath = function(p) return p end,
 readFile = function(p) return p:find('preferences') and 'prefs' or 'cache' end,
 writeFile = function(p, v) stored = v end,
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
 if node.tag == 'row' and node.children and node.children[1].props.text == label then return node.children[2] end
 for _,child in ipairs(node.children or {}) do local found = toggle(child,label) if found then return found end end
end
for _,label in ipairs({'当前活动使用主题强调色','日程切换提示'}) do
 local control = toggle(tree,label)
 assert(control.props.checked == false)
 control.props.onChange('true')
 control = toggle(tree,label)
 assert(control.props.checked == true)
 control.props.onChange('false')
 assert(toggle(tree,label).props.checked == false)
end
assert(stored.accent_color == false and stored.notify_switch == false)
dofile(root .. '/widget.luau')
assert(widgetTree.children[2].props.color == 'on_surface')
print('Real callback string regression passed: toggles persist booleans, reload stays off, widget uses ordinary color')
