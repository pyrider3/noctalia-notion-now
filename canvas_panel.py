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
from alarm_store import AlarmStore, next_time, countdown

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
        self.alarm_store = AlarmStore(STATE)
        self.alarm_open = False
        self.alarm_progress = 0.0
        self.alarm_tick = time.monotonic()
        self.alarm_error = ""
        clock = dt.datetime.now() + dt.timedelta(minutes=15)
        self.alarm_hour, self.alarm_minute = clock.hour, clock.minute
        self.alarm_field = None
        self.alarm_buffer = ""
        self.alarm_replace = True
        self.key_serial = 0
        self.alarm_feedback = 0
        self.alarm_content_key = None
        self.alarm_content_changed = 0
        self.load()
        clock = dt.datetime.now(self.tz) + dt.timedelta(minutes=15)
        self.alarm_hour, self.alarm_minute = clock.hour, clock.minute

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
            self.key_serial = event.get('key_serial', 0)
            self.view.up()
            self.pressed = False
        new_press = (event.get('down_serial', 0) > 0 and event['down_serial'] != self.last_down) if serial_mode else down and not self.pressed
        if new_press:
            self.last_down = event.get('down_serial', 0)
            px = float(event.get('down_x', event.get('x', 0))) * WIDTH
            py = float(event.get('down_y', event.get('y', 0))) * HEIGHT
            self.press_xy = (px, py)
            self.travel = 0
            self.drag_chart = not self.alarm_open and 92 <= py <= 296
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
                self.click(float(event.get("up_x", event.get("x", 0)))*WIDTH,
                           float(event.get("up_y", event.get("y", 0)))*HEIGHT)
            self.drag_chart = False
            self.pressed = False
        if not serial_mode:
            self.pressed = down
        wheel = event.get('wheel', 0)
        delta = wheel - self.wheel_total
        self.wheel_total = wheel
        if delta and self.alarm_open:
            self.alarm_field = None
            self.alarm_buffer = ""
            self.alarm_replace = True
            if 158 <= y <= 270:
                if x < 328: self.alarm_hour = (self.alarm_hour + (1 if delta > 0 else -1)) % 24
                else: self.alarm_minute = (self.alarm_minute + (1 if delta > 0 else -1)) % 60
        elif delta and 88 <= y <= 296:
            self.view.zoom(delta, (x - 24) / (WIDTH - 48))
        for key in event.get('keys', []):
            if isinstance(key,dict) and key.get('id',0) > self.key_serial:
                self.key_serial = key['id']
                self.alarm_keyboard(key.get('kind'),key.get('value',''))
        self.last_input = stamp

    def click(self, x, y):
        for left, top, width, height, action in reversed(self.hitboxes):
            if left <= x <= left + width and top <= y <= top + height:
                if action.startswith('alarm:'):
                    self.alarm_action(action[6:])
                elif action == 'now':
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

    def alarm_keyboard(self, kind, value):
        if not self.alarm_open or self.alarm_store.read().get('status') in ('scheduled','ringing'):
            return
        if kind == 'key':
            key=value.lower().replace(' ', '')
            if key in ('tab','shift+tab','iso_left_tab','left','right'):
                if not self.alarm_commit(): return
                self.alarm_field = 'minute' if self.alarm_field == 'hour' else 'hour'
                self.alarm_buffer = ''
                self.alarm_replace = True
            elif key in ('return','enter','kp_enter'):
                self.alarm_action('set')
            elif key in ('ctrl+a','control+a'):
                self.alarm_replace = True
            elif key in ('backspace','delete') and self.alarm_field:
                if self.alarm_replace:self.alarm_buffer = ''
                else:self.alarm_buffer = self.alarm_buffer[:-1]
                self.alarm_replace = False
                self.alarm_error = ''
            return
        if not self.alarm_field:self.alarm_field = 'hour'
        for ch in str(value):
            if ch == ':':
                if self.alarm_commit():
                    self.alarm_field = 'minute'; self.alarm_buffer = ''; self.alarm_replace = True
            elif ch in '0123456789':
                if self.alarm_replace or len(self.alarm_buffer)>=2:self.alarm_buffer = ch
                else:self.alarm_buffer += ch
                self.alarm_replace = False
                self.alarm_commit()

    def alarm_commit(self):
        if not self.alarm_field or self.alarm_replace:return True
        limit=23 if self.alarm_field == 'hour' else 59
        if not self.alarm_buffer or int(self.alarm_buffer)>limit:
            self.alarm_error = '小时需为 00–23' if limit==23 else '分钟需为 00–59'
            return False
        setattr(self,'alarm_'+self.alarm_field,int(self.alarm_buffer))
        self.alarm_error = ''
        return True

    def alarm_action(self, action):
        self.alarm_error = ''
        try:
            if action == 'toggle':
                self.alarm_open = not self.alarm_open
                self.view.up(); self.view.velocity = 0
            elif action == 'close': self.alarm_open = False
            elif action.startswith('quick:'):
                self.alarm_store.schedule(time.time() + int(action.split(':')[1])*60)
                self.alarm_feedback = time.monotonic()
            elif action == 'set':
                if not self.alarm_commit(): return
                self.alarm_store.schedule(next_time(self.alarm_hour, self.alarm_minute, self.tz))
                self.alarm_feedback = time.monotonic()
            elif action == 'cancel': self.alarm_store.cancel()
            elif action == 'snooze': self.alarm_store.snooze(self.alarm_store.read().get('id'))
            elif action in ('edit:hour','edit:minute'):
                if not self.alarm_commit(): return
                self.alarm_field = action.split(':')[1]
                self.alarm_buffer = ''
                self.alarm_replace = True
            elif action == 'sound': self.alarm_store.sound()
            elif action == 'hour+': self.alarm_hour = (self.alarm_hour+1)%24
            elif action == 'hour-': self.alarm_hour = (self.alarm_hour-1)%24
            elif action == 'minute+': self.alarm_minute = (self.alarm_minute+1)%60
            elif action == 'minute-': self.alarm_minute = (self.alarm_minute-1)%60
            if action in ('hour+','hour-','minute+','minute-','close','cancel','toggle') or action.startswith('quick:'):
                self.alarm_field = None
                self.alarm_buffer = ''
                self.alarm_replace = True
        except (OSError, ValueError):
            self.alarm_error = '未能保存，请重试'

    def alarm_animating(self):
        return abs(self.alarm_progress - int(self.alarm_open)) > .001 or time.monotonic()-self.alarm_content_changed < .2

    def paint(self, target):
        began = time.perf_counter()
        c = cairo.Context(target)
        c.scale(SCALE, SCALE)
        c.set_operator(cairo.OPERATOR_SOURCE); c.set_source_rgba(0,0,0,0); c.paint()
        c.set_operator(cairo.OPERATOR_OVER)
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

        rect(0,0,WIDTH,HEIGHT,BG,28)

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
            rect(x,y,width,30,'#383333' if bright else '#242930',15,1 if hovered else .7,stroke='#54443c' if bright else '#333a43')
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
        # Draw the bell as vectors so it shares the existing line weight and palette.
        button('',268,22,36,'alarm:toggle',self.alarm_open)
        c.set_source_rgba(*rgba(ACCENT if self.alarm_open else MUTED)); c.set_line_width(1.4)
        c.move_to(278,43); c.line_to(280,39); c.line_to(280,34)
        c.curve_to(280,27,292,27,292,34); c.line_to(292,39); c.line_to(294,43); c.close_path(); c.stroke()
        c.arc(286,45,2,0,math.pi); c.stroke()
        alarm = self.alarm_store.read()
        if alarm.get('status') in ('scheduled','ringing'):
            rect(295,24,5,5,ACCENT,2.5)
            text(countdown(alarm),155,58,12,ACCENT)
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
            rect(left,y,max(2,end-left-2),h,color,16,.45 if past else .95,stroke='#eac6b1' if chosen else '#7a899b')
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
            rect(pill_x,82,46,18,ACCENT,9)
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
            display_prefs = read(STATE/'preferences.json')
            if active and display_prefs.get('display_mode', 'pinned') == 'pinned':
                pinned = display_prefs.get('pinned_event_id') == e['id']
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
        # One lightweight drawer; timeline layout stays still underneath.
        stamp = time.monotonic()
        delta = min(.05, stamp-self.alarm_tick)
        self.alarm_tick = stamp
        self.alarm_progress += (int(self.alarm_open)-self.alarm_progress)*(1-math.exp(-24*delta))
        if abs(self.alarm_progress-int(self.alarm_open)) < .001:
            self.alarm_progress = float(self.alarm_open)
        if self.alarm_progress > 0:
            progress = self.alarm_progress
            self.hitboxes = [(0,0,WIDTH,HEIGHT,'alarm:close')]
            rect(0,0,WIDTH,HEIGHT,'#080a0d',28,.6*progress)
            c.save(); c.translate(0,-9*(1-progress)); c.push_group()
            rect(146,86,366,348,PANEL,24,stroke=GRID)
            text('小闹钟',166,118,18,bold=True)
            button('×',462,99,30,'alarm:close')
            active = alarm.get('status') in ('scheduled','ringing')
            content_key = (alarm.get('id'),alarm.get('status'))
            if content_key != self.alarm_content_key:
                self.alarm_content_key = content_key
                self.alarm_content_changed = stamp
            ease = min(1,(stamp-self.alarm_content_changed)/.16)
            ease = 1-(1-ease)**3
            c.save(); c.translate(0,4*(1-ease)); c.push_group()
            if active:
                text('时间到了' if alarm.get('status') == 'ringing' else '距离提醒',166,152,11,MUTED)
                text(countdown(alarm),166,197,34,ACCENT,True)
                due = dt.datetime.fromtimestamp(alarm.get('due',now),self.tz)
                text(due.strftime('%m月%d日 %H:%M')+' 提醒',166,222,12,MUTED)
                if alarm.get('status') == 'ringing':
                    button('再提醒 5 分钟',166,245,196,'alarm:snooze',True)
                    button('关闭',374,245,118,'alarm:cancel')
                else:
                    button('取消闹钟',166,245,326,'alarm:cancel')
            else:
                text('指定时间 · 点击数字输入',166,151,11,MUTED)
                for x,label,field in [(166,f'{self.alarm_hour:02d}','hour'),(344,f'{self.alarm_minute:02d}','minute')]:
                    focused = self.alarm_field == field
                    rect(x,164,148,62,BG,18,stroke=ACCENT if focused else GRID)
                    self.hitboxes.append((x,164,148,62,'alarm:edit:'+field))
                    if focused and not self.alarm_replace:label=self.alarm_buffer or '—'
                    if focused and self.alarm_replace:rect(x+42,174,64,44,ACCENT,12,.12)
                    text(label,x+52,207,32,ACCENT,True)
                    if focused and not self.alarm_replace and int(stamp*2)%2==0:
                        line(x+103,178,x+103,211,ACCENT)
                    button('−',x,232,62,'alarm:'+field+'-')
                    button('+',x+86,232,62,'alarm:'+field+'+')
                text(':',324,207,28,MUTED)
                due = dt.datetime.fromtimestamp(next_time(self.alarm_hour,self.alarm_minute,self.tz),self.tz)
                button(('明天 ' if due.date()!=today.date() else '今天 ')+due.strftime('%H:%M')+' 提醒',166,278,326,'alarm:set',True)
            if active: quick_y = 301
            else: quick_y = 327
            text('快捷设定' if not active else '重新设定',166,quick_y-8,11,MUTED)
            for x,minutes in [(166,5),(278,15),(390,30)]:
                button(str(minutes)+' 分钟',x,quick_y,102,'alarm:quick:'+str(minutes))
            line(166,quick_y+44,492,quick_y+44)
            button('提示音 '+('开' if alarm.get('sound',True) else '关'),166,quick_y+54,106,'alarm:sound',alarm.get('sound',True))
            if self.alarm_error:
                text(self.alarm_error,284,quick_y+74,11,ACCENT)
            elif stamp-self.alarm_feedback < 2:
                text('已设好',435,quick_y+74,11,'#8fa99a')
            c.pop_group_to_source(); c.paint_with_alpha(ease); c.restore()
            c.pop_group_to_source(); c.paint_with_alpha(progress); c.restore()
        self.frames+=1

        self.paint_ms=(time.perf_counter()-began)*1000
        save(STATE/'canvas-status.json',dict(alarm_open=self.alarm_open,settings_request=self.settings_request,frames=self.frames,paint_ms=round(self.paint_ms,2),first=round(self.view.first,3),span=round(self.view.span,3),dragging=self.view.dragging,selected=self.selected,updated=now))


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
                if registered and pending and current>=frame_at and (moving or changed or current-canvas.detail_changed < .18 or canvas.alarm_animating() or current-last_paint>=.5):
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
