#!/usr/bin/env python3
"""60 Hz native Noctalia shared-memory canvas. No network, no credentials."""
import array
import datetime as dt
import fcntl
import json
import math
import mmap
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import time
from zoneinfo import ZoneInfo
import cairo
from canvas_engine import Viewport, layout_events

STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'notion-now'
WIDTH, HEIGHT, SCALE = 536, 500, 2
BG, PANEL, TEXT, MUTED = '#171a1f', '#1c2026', '#e9e9e6', '#9da5b0'
ACCENT, SLATE, GRID = '#edb69b', '#596b80', '#323943'


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save(path, value):
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, ensure_ascii=False)
    tmp.replace(path)


def rgba(hex_value, alpha=1):
    return tuple(int(hex_value[i:i+2], 16) / 255 for i in (1, 3, 5)) + (alpha,)


def centered_text_position(context, label, x, y, width, height):
    extents = context.text_extents(label)
    return (x + (width - extents.width) / 2 - extents.x_bearing,
            y + (height - extents.height) / 2 - extents.y_bearing)


class Canvas:
    def __init__(self):
        self.data = {}
        self.events = []
        self.day = None
        self.tz = ZoneInfo('Asia/Shanghai')
        self.start = 0
        self.view = None
        self.selected = None
        self.manual_selection = False
        self.pointer_x, self.pointer_y = 0, 0
        self.pressed = False
        self.press_xy = None
        self.travel = 0
        self.drag_chart = False
        self.seen_sequence = -1
        self.wheel_total = 0
        self.settings_request = 0
        self.hitboxes = []
        self.frames = 0
        self.paint_ms = 0
        self.input_session = None
        self.last_down = 0
        self.last_release = 0
        self.last_input = 0
        self.detail_changed = time.monotonic()
        self.load()

    def load(self):
        self.data = read(STATE / 'events.json')
        try:
            self.tz = ZoneInfo(self.data.get('timezone', 'Asia/Shanghai'))
        except (KeyError, ValueError):
            self.tz = ZoneInfo('Asia/Shanghai')
        now = dt.datetime.now(self.tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.start = start.timestamp()
        finish = (start + dt.timedelta(days=1)).timestamp()
        self.events = layout_events(self.data.get('events', []), self.start, finish)
        if self.day != now.date():
            self.day = now.date()
            self.view = Viewport(self.minute(time.time()), 240)
            self.selected = None
            self.manual_selection = False
        self.select_default()

    def minute(self, epoch):
        value = dt.datetime.fromtimestamp(epoch, self.tz)
        return value.hour * 60 + value.minute + value.second / 60

    def select_default(self):
        now = time.time()
        if self.manual_selection and any(e['id'] == self.selected for e in self.events):
            return
        active = sorted((e for e in self.events if e['start'] <= now < e['end']), key=lambda e: (e['end'], e['id']))
        following = [e for e in self.events if e['start'] > now]
        picked = next(iter(active or following or self.events[-1:]), None)
        selected = picked['id'] if picked else None
        if selected != self.selected:
            self.detail_changed = time.monotonic()
        self.selected = selected

    def input(self, event):
        seq = event.get('seq')
        if not isinstance(seq, int) or not isinstance(event.get('pressed'), bool):
            return
        if self.seen_sequence < 0:
            self.wheel_total = event.get('wheel', 0)
        if seq == self.seen_sequence:
            return
        self.seen_sequence = seq
        x, y = float(event.get('x', 0)) * WIDTH, float(event.get('y', 0)) * HEIGHT
        stamp = float(event.get('time', time.time()))
        down = bool(event.get('pressed'))
        self.pointer_x, self.pointer_y = x, y
        serial_mode = 'down_serial' in event
        if serial_mode and event.get('session') != self.input_session:
            self.input_session = event.get('session')
            self.last_down = event.get('down_serial', 0)
            self.last_release = event.get('released_serial', 0)
            self.view.up()
            self.pressed = False
        new_press = (event.get('down_serial', 0) > 0 and event['down_serial'] != self.last_down) if serial_mode else down and not self.pressed
        if new_press:
            self.last_down = event.get('down_serial', 0)
            px = float(event.get('down_x', event.get('x', 0))) * WIDTH
            py = float(event.get('down_y', event.get('y', 0))) * HEIGHT
            self.press_xy = (px, py)
            self.travel = 0
            self.drag_chart = 92 <= py <= 296
            self.pressed = True
            if self.drag_chart:
                self.view.down(px, float(event.get('down_time', stamp)))
        if self.pressed and self.drag_chart:
            self.travel = max(self.travel, abs(x - self.press_xy[0]) + abs(y - self.press_xy[1]))
            if self.travel > 3:
                self.view.move(x, stamp, WIDTH - 48)
        new_release = (event.get('released_serial', 0) > 0 and event['released_serial'] != self.last_release) if serial_mode else not down and self.pressed
        if new_release:
            self.last_release = event.get('released_serial', 0)
            self.view.up()
            if event.get("cancelled"):
                self.view.velocity = 0
            if self.pressed and self.travel <= 4 and not event.get("cancelled"):
                self.view.velocity = 0
                self.click(x, y)
            self.drag_chart = False
            self.pressed = False
        if not serial_mode:
            self.pressed = down
        wheel = event.get('wheel', 0)
        delta = wheel - self.wheel_total
        self.wheel_total = wheel
        if delta and 88 <= y <= 296:
            self.view.zoom(delta, (x - 24) / (WIDTH - 48))
        self.last_input = stamp

    def click(self, x, y):
        for left, top, width, height, action in reversed(self.hitboxes):
            if left <= x <= left + width and top <= y <= top + height:
                if action == 'now':
                    self.manual_selection = False
                    self.select_default()
                    self.view.locate(self.minute(time.time()), 240)
                elif action == 'all':
                    self.view.locate(720, 1440)
                elif action == 'settings':
                    self.settings_request += 1
                elif action == 'refresh':
                    subprocess.Popen(['systemctl', '--user', 'start', 'notion-now-sync.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif action.startswith('event:'):
                    self.selected = action[6:]
                    self.detail_changed = time.monotonic()
                    self.manual_selection = True
                elif action == 'pin':
                    item = next((e for e in self.events if e['id'] == self.selected), {})
                    if item.get('start', 1e20) <= time.time() < item.get('end', 0):
                        prefs = read(STATE/'preferences.json')
                        prefs['pinned_event_id'] = '' if prefs.get('pinned_event_id') == self.selected else self.selected
                        save(STATE/'preferences.json', prefs)
                elif action == 'open':
                    item = next((e for e in self.events if e['id'] == self.selected), {})
                    url = item.get('url', '')
                    if url.startswith('https://'):
                        subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return

    def paint(self, target):
        began = time.perf_counter()
        c = cairo.Context(target)
        c.scale(SCALE, SCALE)
        c.set_source_rgba(*rgba(BG)); c.paint()
        self.hitboxes = []

        def rect(x, y, w, h, fill, radius=0, alpha=1, stroke=None):
            if w <= 0 or h <= 0:
                return
            r = min(radius, h/2, w/2)
            c.new_sub_path()
            for cx, cy, a in [(x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)]:
                c.arc(cx,cy,r,a,a+math.pi/2)
            c.close_path()
            c.set_source_rgba(*rgba(fill, alpha)); c.fill_preserve()
            if stroke:
                c.set_source_rgba(*rgba(stroke)); c.set_line_width(1); c.stroke()
            else:
                c.new_path()

        def text(value, x, y, size=13, color=TEXT, bold=False, limit=None):
            c.select_font_face('Noto Sans CJK SC', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
            c.set_font_size(size)
            value = str(value)
            if limit:
                while len(value) > 1 and c.text_extents(value).width > limit:
                    value = value[:-2] + '…'
            c.set_source_rgba(*rgba(color)); c.move_to(x, y); c.show_text(value)

        def line(x1,y1,x2,y2,color=GRID,alpha=1,width=1):
            c.set_source_rgba(*rgba(color, alpha)); c.set_line_width(width)
            c.move_to(x1,y1); c.line_to(x2,y2); c.stroke()

        def button(label, x, y, width, action, bright=False):
            hovered = x <= self.pointer_x <= x+width and y <= self.pointer_y <= y+30
            rect(x,y,width,30,'#383333' if bright else '#242930',8,1 if hovered else .7,stroke='#54443c' if bright else '#333a43')
            c.select_font_face('Noto Sans CJK SC', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            c.set_font_size(12)
            tx, ty = centered_text_position(c, label, x, y, width, 30)
            text(label,tx,ty,12,ACCENT if bright else MUTED)
            self.hitboxes.append((x,y,width,30,action))

        now = time.time()
        self.select_default()
        today = dt.datetime.fromtimestamp(now,self.tz)
        text('日历，此刻',24,34,21,bold=True)
        text(today.strftime('%m月%d日') + '  ' + '周' + '一二三四五六日'[today.weekday()],24,58,12,MUTED)
        button('全天',314,22,54,'all')
        button('现在',376,22,54,'now',True)
        button('刷新',438,22,72,'refresh')
        line(24,78,WIDTH-24,78)
        x0, right, chart_top, chart_bottom = 24, WIDTH-24, 130, 292
        chart_width = right-x0
        def px(m): return x0+(m-self.view.first)/self.view.span*chart_width
        step = 240 if self.view.span > 720 else 120 if self.view.span > 360 else 60 if self.view.span > 210 else 30 if self.view.span > 90 else 15
        minor = step/6
        first_tick = math.ceil(self.view.first/minor)*minor
        tick = first_tick
        while tick <= self.view.first+self.view.span+.001:
            x=px(tick)
            major = abs(tick/step-round(tick/step)) < .001
            line(x,chart_top-12 if major else chart_top-6,x,chart_bottom,GRID,.8 if major else .24)
            if major:
                caption=f'{int(tick)//60:02d}:{int(tick)%60:02d}'
                text(caption,max(24,min(right-34,x-15)),chart_top-18,11,MUTED)
            tick += minor
        visible = [e for e in self.events if e['clip_end']>self.start+self.view.first*60 and e['clip_start']<self.start+(self.view.first+self.view.span)*60]
        lanes = sorted(set(e['lane'] for e in visible))
        lane_map = {lane:i for i,lane in enumerate(lanes)}
        lane_h = min(64, 150/max(2,len(lanes)))
        c.save(); c.rectangle(x0,chart_top,chart_width,chart_bottom-chart_top); c.clip()
        for e in visible:
            start = (e['clip_start']-self.start)/60
            finish = (e['clip_end']-self.start)/60
            left, end = max(x0,px(start)),min(right,px(finish))
            y = chart_top+8+lane_map[e['lane']]*lane_h
            h = max(12,lane_h-8)
            chosen = e['id']==self.selected
            active = e['start']<=now<e['end']
            past = e['end']<=now
            color = ACCENT if chosen and active else SLATE
            rect(left,y,max(2,end-left-2),h,color,6,.45 if past else .95,stroke='#eac6b1' if chosen else '#7a899b')
            self.hitboxes.append((left,y,max(2,end-left),h,'event:'+e['id']))
            if end-left>42 and h>=32:
                text(e['title'],left+9,y+22,13,'#242323' if chosen and active else TEXT,True,end-left-18)
                if h>=48:
                    timing=dt.datetime.fromtimestamp(e['start'],self.tz).strftime('%H:%M')+'–'+dt.datetime.fromtimestamp(e['end'],self.tz).strftime('%H:%M')
                    text(timing,left+9,y+42,10,'#4b403a' if chosen and active else '#c5cbd4',limit=end-left-18)
        current_x = px(self.minute(now))
        if x0<=current_x<=right:
            line(current_x,chart_top-6,current_x,chart_bottom,ACCENT,1,1.3)
            rect(current_x-3,chart_top-9,6,6,ACCENT,3)
        c.restore()
        if x0<=current_x<=right:
            pill_x=max(x0,min(right-46,current_x-23))
            rect(pill_x,82,46,18,ACCENT,5)
            text(today.strftime('%H:%M'),pill_x+7,95,11,'#272323',True)
        line(24,308,right,308)
        e=next((e for e in self.events if e['id']==self.selected),None)
        detail_ease = min(1, (time.monotonic() - self.detail_changed) / .16)
        detail_ease = 1 - (1-detail_ease)**3
        c.save(); c.translate(0, 3*(1-detail_ease)); c.push_group()
        if e:
            active=e['start']<=now<e['end']
            state='正在进行' if active else '下一项日程' if e['start']>now else '已结束'
            text(state,24,335,11,ACCENT if active else MUTED)
            if active:
                pinned = read(STATE/'preferences.json').get('pinned_event_id') == e['id']
                button('取消固定' if pinned else '固定到顶栏', WIDTH-210, 315, 148, 'pin', pinned)
            text(e['title'],24,367,21,bold=True,limit=WIDTH-100)
            self.hitboxes.append((WIDTH-62,338,38,38,'open'))
            text('↗',WIDTH-53,366,24,MUTED)
            timing=dt.datetime.fromtimestamp(e['start'],self.tz).strftime('%H:%M')+'–'+dt.datetime.fromtimestamp(e['end'],self.tz).strftime('%H:%M')
            remaining=math.ceil((e['end']-now)/60) if active else math.ceil((e['start']-now)/60)
            hint=f'剩余 {remaining} 分钟' if active else f'还有 {remaining} 分钟开始' if e['start']>now else '此项日程已结束'
            text(timing+'  ·  '+hint,24,393,13,MUTED)
            fraction=max(0,min(1,(now-e['start'])/(e['end']-e['start'])))
            rect(24,413,WIDTH-48,4,GRID,2)
            prefs=read(STATE/'preferences.json')
            warning=prefs.get('end_warning',True) not in (False,'false') and 0<e['end']-now<=float(prefs.get('end_warning_minutes',5))*60
            rect(24,413,(WIDTH-48)*fraction,4,'#e9ad52' if warning else ACCENT,2)
        else:
            text('今天暂无定时活动',24,365,21,bold=True)
            text('拖动浏览时间 · 滚轮缩放',24,395,13,MUTED)
        c.pop_group_to_source(); c.paint_with_alpha(.85 + .15*detail_ease); c.restore()
        line(24,440,right,440)
        next_event=next((item for item in self.events if item['start']>now),None)
        footer='下一项  '+dt.datetime.fromtimestamp(next_event['start'],self.tz).strftime('%H:%M')+' · '+next_event['title'] if next_event else '今天暂无后续安排'
        text(footer,24,470,12,MUTED,limit=WIDTH-100)
        button('设置',WIDTH-82,451,58,'settings')
        status=self.data.get('sources',{}).get('notion',{})
        text('● '+('已同步' if status.get('ok') else '同步异常 · 使用缓存'),24,491,10,'#8fa99a' if status.get('ok') else ACCENT)
        self.frames+=1
        self.paint_ms=(time.perf_counter()-began)*1000
        save(STATE/'canvas-status.json',dict(settings_request=self.settings_request,frames=self.frames,paint_ms=round(self.paint_ms,2),first=round(self.view.first,3),span=round(self.view.span,3),dragging=self.view.dragging,selected=self.selected,updated=now))


def main():
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=open(STATE/'canvas.lock','w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: return
    path=STATE/'canvas.sock'
    path.unlink(missing_ok=True)
    server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    server.bind(str(path)); os.chmod(path,0o600); server.listen(1)
    canvas=Canvas()
    while True:
        conn,_=server.accept()
        fd=os.memfd_create('notion-now-canvas',os.MFD_ALLOW_SEALING)
        os.ftruncate(fd,WIDTH*SCALE*HEIGHT*SCALE*4)
        fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_SHRINK)
        pixels=mmap.mmap(fd,WIDTH*SCALE*HEIGHT*SCALE*4)
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,WIDTH*SCALE,HEIGHT*SCALE)
        pending=False;registered=False
        last=time.monotonic(); frame_at=last; loaded=last
        old_input=None;last_paint=0
        try:
            while True:
                ready,_,_=select.select([conn],[],[],1/120)
                if ready:
                    msg=conn.recv(128)
                    if not msg: break
                    kind,value=struct.unpack('<II',msg[:8])
                    if kind==1:
                        if value!=1:break
                        conn.sendmsg([struct.pack('<IIII',1,0,WIDTH*SCALE,HEIGHT*SCALE)],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[fd]))])
                        registered=True
                    elif kind==2:pending=True
                current=time.monotonic()
                if current-loaded>1:
                    canvas.load();loaded=current
                inp=read(STATE/'canvas-input.json')
                changed=isinstance(inp.get('seq'),int) and isinstance(inp.get('pressed'),bool) and inp['seq']!=old_input
                if changed:
                    canvas.input(inp);old_input=inp.get('seq')
                moving=canvas.view.step(current-last)
                last=current
                if registered and pending and current>=frame_at and (moving or changed or current-canvas.detail_changed < .18 or current-last_paint>=.5):
                    canvas.paint(surface);surface.flush()
                    # Cairo's native little-endian ARGB is BGRA; the protocol is RGBA.
                    src=memoryview(surface.get_data()).cast('B')
                    out=bytearray(src)
                    out[0::4]=src[2::4];out[2::4]=src[0::4]
                    pixels.seek(0);pixels.write(out)
                    conn.send(struct.pack('<II',2,0));pending=False
                    frame_at=current+1/60;last_paint=current
        except (OSError,ValueError,struct.error):
            pass
        finally:
            canvas.view.up();conn.close();pixels.close();os.close(fd)


if __name__=='__main__':main()
