local root = arg[1]
local now = 1791367200
local prefs = {accent_color=false, notify_switch=true, display_mode='pinned'}
local data = {updated=now,sources={notion={ok=true,message='已同步'}},events={}}
local writes, notifications, tree = {}, {}, nil
noctalia = {
 expandPath=function(p)return p end,
 readFile=function(p) if p:find('preferences') then return 'prefs' end if p:find('bar%-status') then return 'bar' end return 'cache' end,
 writeFile=function(p,v)writes[p]=v return true end,
 json={decode=function(raw)if raw=='prefs' then return prefs end if raw=='bar' then return {updated=now,width=120,tooltip='活动'} end return data end,encode=function(v)return v end},
 nowMs=function()return now*1000 end,
 formatTime=function()return '2026-10-31' end,
 getColor=function()return '#eeeeee' end,
 setUpdateInterval=function()end,
 pluginDir=function()return root end,
 runAsync=function()end,
 notify=function(title,body)table.insert(notifications,{title,body})end,
}
local modules={}
require=function(path)if not modules[path] then modules[path]=assert(loadfile(root..'/'..path))() end return modules[path] end
ui=setmetatable({}, {__index=function(_,tag)return function(props,children)return {tag=tag,props=props,children=children}end end})
barWidget={render=function(v)tree=v end,setTooltip=function()end}
panel={render=function(v)tree=v end}
dofile(root..'/widget.luau')
assert(tree.children[2].tag=='pixelStream')
assert(tree.children[2].props.width==120)
onScroll('vertical',1,true)
assert(writes['~/.local/state/notion-now/bar-input.json'].wheel==1)
barHover('true')
assert(writes['~/.local/state/notion-now/bar-input.json'].hovered==true)
barHover('false')
assert(writes['~/.local/state/notion-now/bar-input.json'].hovered==false)
dofile(root..'/panel.luau')
onOpen()
assert(tree.children[1].tag=='pixelStream')
canvasDown(tostring(480/536),tostring(466/500))
canvasUp(tostring(480/536),tostring(466/500))
assert(tree.props.key=='preferences-v2')
print('Native bar width, hover/scroll input, canvas handoff and immediate settings entry passed')
data={updated=now,sources={notion={ok=true}},events={
 {id='old',provider='notion',title='上一项',start=now-60,['end']=now+5},
 {id='new',provider='notion',title='下一项',start=now+5,['end']=now+60},
}}
dofile(root..'/service.luau')
assert(#notifications==0)
now=now+5 update()
assert(#notifications==1)
assert(notifications[1][2]:find('已结束：上一项',1,true))
assert(notifications[1][2]:find('开始：下一项',1,true))
update() assert(#notifications==1)
prefs.notify_switch=false
now=now+55 update() assert(#notifications==1)
print('Merged switch notifications and disable behavior passed')
