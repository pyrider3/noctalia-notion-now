"""Continuous viewport physics, independent of rendering and desktop IO."""
import math


class Viewport:
    def __init__(self, center=600, span=240):
        self.span = self.target_span = float(span)
        self.first = self.target_first = self.bound(center - span / 2, span)
        self.velocity = 0.0
        self.dragging = False
        self.pointer = None
        self.anchor = None

    @staticmethod
    def bound(first, span):
        return max(0.0, min(1440.0 - span, first))

    def zoom(self, steps, fraction):
        fraction = max(0.0, min(1.0, fraction))
        anchor = self.first + fraction * self.span
        self.target_span = max(45.0, min(1440.0, self.target_span * math.exp(steps * .15)))
        self.target_first = self.bound(anchor - fraction * self.target_span, self.target_span)
        self.anchor = (anchor, fraction)
        self.velocity = 0

    def locate(self, center, span=None):
        self.target_span = max(45.0, min(1440.0, span or self.span))
        self.target_first = self.bound(center - self.target_span / 2, self.target_span)
        self.velocity = 0
        self.anchor = None

    def down(self, x, stamp):
        self.dragging = True
        self.pointer = (x, stamp)
        self.target_first, self.target_span = self.first, self.span
        self.velocity = 0
        self.anchor = None

    def move(self, x, stamp, width):
        if not self.dragging:
            return
        old_x, old_stamp = self.pointer
        delta = -(x - old_x) * self.span / width
        self.first = self.bound(self.first + delta, self.span)
        self.target_first = self.first
        dt = max(.004, min(.1, stamp - old_stamp))
        self.velocity = .35 * self.velocity + .65 * delta / dt
        self.pointer = (x, stamp)

    def up(self):
        self.dragging = False

    def step(self, dt):
        dt = max(0, min(.05, dt))
        if self.dragging:
            return False
        before = (self.first, self.span)
        ease = 1 - math.exp(-18 * dt)
        self.span += (self.target_span - self.span) * ease
        if self.anchor:
            anchor, fraction = self.anchor
            self.first = self.bound(anchor - fraction * self.span, self.span)
            if abs(self.span - self.target_span) < .015:
                self.span = self.target_span
                self.first = self.bound(anchor - fraction * self.span, self.span)
                self.anchor = None
        elif abs(self.velocity) > .15:
            proposed = self.first + self.velocity * dt
            self.first = self.bound(proposed, self.span)
            if self.first != proposed:
                self.velocity = 0
            else:
                self.velocity *= math.exp(-8 * dt)
            self.target_first = self.first
        else:
            self.velocity = 0
            self.first = self.bound(self.first + (self.target_first - self.first) * ease, self.span)
        return abs(before[0] - self.first) + abs(before[1] - self.span) > .0001


def layout_events(events, start, finish):
    """Clip by actual epoch day bounds; greedily allocate overlap lanes."""
    result, lane_ends = [], []
    for e in sorted(events, key=lambda e: (e['start'], e['end'], e['id'])):
        if e.get('all_day') or e.get('point') or e['end'] <= e['start']:
            continue
        left, right = max(start, e['start']), min(finish, e['end'])
        if right <= left:
            continue
        lane = next((i for i, end in enumerate(lane_ends) if end <= left), len(lane_ends))
        if lane == len(lane_ends):
            lane_ends.append(right)
        else:
            lane_ends[lane] = right
        result.append(dict(e, lane=lane, clip_start=left, clip_end=right))
    return result
