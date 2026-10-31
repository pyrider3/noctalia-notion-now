local root = arg[1] or '.'
noctalia = { formatTime = function(pattern, timestamp)
 local format = pattern:match('{:(.-)}')
 return os.date('!' .. format, timestamp)
end, runAsync = function() error('unexpected launch') end }
ui = setmetatable({}, {__index = function(_,kind) return function(props,children) return {tag=kind,props=props,children=children} end end})
local timeline = assert(loadfile(root .. '/timeline.luau'))()
local day = 1793404800 -- 2026-10-31 00:00 UTC
local function event(id,start,finish,extra)
 local e = {id=id,title=id,calendar='Test',start=day+start*60,['end']=day+finish*60}
 for k,v in pairs(extra or {}) do e[k]=v end
 return e
end
local data = {events={event('a',540,600),event('b',570,630),event('c',600,660),
 event('cross',-60,30),event('ends-midnight',-120,0),event('tomorrow',1440,1500),
 event('all',0,1440,{all_day=true}),event('point',600,600,{point=true})}}
local model = timeline.build(data,day+585*60,'UTC')
assert(#model.events==4)
assert(#model.lanes==2)
assert(model.events[1].start==0 and model.events[1].finish==30)
assert(model.first==0 and model.last==1320)
assert(model.events[4].lane==model.events[2].lane, 'touching events must reuse the lane')
local selected=nil
local tree=timeline.render(data,day+585*60,'UTC',nil,function(id)selected=id end)
local function visit(node, fn)
 fn(node)
 for _,child in ipairs(node.children or {}) do visit(child,fn) end
end
local found=false
visit(tree,function(n)
 if n.props.key=='b' then n.props.onClick() found=true end
 if n.props.width then assert(n.props.width>=0 and n.props.width<=396) end
end)
assert(found and selected=='b')
local changed=timeline.render(data,day+585*60,'UTC',selected,function()end)
local title=false
visit(changed,function(n) if n.tag=='label' and n.props.text=='b' then title=true end end)
assert(title)
assert(#timeline.build({events={}},day,'UTC').lanes==0)
local multi=timeline.build({events={event('long',-60,1500)}},day+600*60,'UTC')
assert(multi.events[1].start==0 and multi.events[1].finish==1440)
assert(multi.last==1440)
print('Timeline checks passed: overlap lanes, adjacent reuse, midnight, cross-day, empty, filtering, selection and bounds')
local clamped = timeline.viewport({first=-100,span=20})
assert(clamped.first==0 and clamped.span==60)
assert(timeline.viewport({first=1400,span=360}).first==1080)
local zoomed = timeline.zoom({first=0,span=1440},360,600)
assert(zoomed.first==420 and zoomed.span==360)
local zoomed2 = timeline.zoom(zoomed,180,0)
assert(zoomed2.first==510 and zoomed2.span==180)
local sliced = timeline.window(model,{first=585,span=60})
assert(sliced.first==585 and sliced.last==645 and #sliced.events==3)
for _, e in ipairs(sliced.events) do assert(e.start>=585 and e.finish<=645 and e.finish>e.start) end
assert(#timeline.window(model,{first=1200,span=60}).events==0)
local changedView
local controls=timeline.render(data,day+585*60,'UTC',nil,function()end,{first=0,span=1440},function(v)changedView=v end)
visit(controls,function(n) if n.tag=='button' and n.props.text=='+' then n.props.onClick() end end)
assert(changedView.span==720)
controls=timeline.render(data,day+585*60,'UTC',nil,function()end,changedView,function(v)changedView=v end)
visit(controls,function(n) if n.props.key=='timeline-pan' then n.props.onChange('720') end end)
assert(changedView.first==720 and changedView.span==720)
controls=timeline.render(data,day+585*60,'UTC',nil,function()end,changedView,function(v)changedView=v end)
visit(controls,function(n) if n.tag=='button' and n.props.text=='现在' then n.props.onClick() end end)
assert(changedView.span==360 and changedView.first==405)
controls=timeline.render(data,day+585*60,'UTC',nil,function()end,changedView,function(v)changedView=v end)
visit(controls,function(n) if n.tag=='button' and n.props.text=='全天' then n.props.onClick() end end)
assert(changedView.first==0 and changedView.span==1440)
print('Zoom/pan checks passed: clamps, anchor, clipping, empty window, string slider callback, now and full-day reset')
