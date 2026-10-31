import math
import unittest
from canvas_engine import Viewport, layout_events


class Physics(unittest.TestCase):
    def test_drag_moves_immediately_and_inertia_decays(self):
        v=Viewport(600,240)
        v.down(200,1)
        v.move(260,1.03,480)
        self.assertAlmostEqual(v.first,450)
        v.up()
        before=v.first
        for _ in range(60): v.step(1/60)
        self.assertLess(v.first,before)
        self.assertLess(abs(v.velocity),1)

    def test_zoom_preserves_pointer_anchor(self):
        v=Viewport(600,240)
        fraction=.3
        anchor=v.first+fraction*v.span
        v.zoom(-4,fraction)
        for _ in range(120):
            v.step(1/120)
            self.assertAlmostEqual(v.first+fraction*v.span,anchor,places=3)
        self.assertLess(v.span,240)

    def test_edges_and_frame_rate_independence(self):
        outcomes=[]
        for hz in [30,60,120]:
            v=Viewport(600,240);v.locate(900,120)
            for _ in range(hz):v.step(1/hz)
            outcomes.append(v.first)
            v.locate(-999,1440)
            for _ in range(hz*2):v.step(1/hz)
            self.assertGreaterEqual(v.first,0)
            self.assertLessEqual(v.first+v.span,1440.001)
        self.assertLess(max(outcomes)-min(outcomes),.01)

    def test_day_clipping_and_overlap(self):
        data=[dict(id='a',start=-60,end=60),dict(id='b',start=30,end=90),dict(id='c',start=90,end=120),dict(id='point',start=30,end=30,point=True)]
        items=layout_events(data,0,100)
        self.assertEqual(len(items),3)
        self.assertEqual(items[0]['clip_start'],0)
        self.assertEqual(items[2]['clip_end'],100)
        self.assertEqual([e['lane'] for e in items],[0,1,0])



class InputSafety(unittest.TestCase):
    def test_partial_files_do_not_reset_zoom_or_release_drag(self):
        from canvas_panel import Canvas
        c=Canvas()
        c.input(dict(seq=1,pressed=True,x=.5,y=.4,wheel=-2,time=1))
        self.assertTrue(c.view.dragging)
        before=c.wheel_total
        c.input({})
        self.assertTrue(c.view.dragging)
        self.assertEqual(c.wheel_total,before)
        c.input(dict(seq=2,pressed=False,x=.5,y=.4,wheel=-2,time=1.1))
        self.assertFalse(c.view.dragging)
        self.assertEqual(c.view.target_span,240)

    def test_fast_click_preserves_down_up_even_in_one_snapshot(self):
        from canvas_panel import Canvas
        c=Canvas();c.hitboxes=[(0,0,100,50,'settings')]
        c.input(dict(seq=1,session=11,down_serial=0,released_serial=0,pressed=False,x=0,y=0,wheel=0))
        c.input(dict(seq=3,session=11,down_serial=1,released_serial=1,down_x=.05,down_y=.05,down_time=1,pressed=False,x=.05,y=.05,wheel=0,time=1.03))
        self.assertEqual(c.settings_request,1)
        c.input(dict(seq=4,session=11,down_serial=1,released_serial=1,pressed=False,x=.05,y=.05,wheel=0,time=1.04))
        self.assertEqual(c.settings_request,1)

class ButtonAlignment(unittest.TestCase):
    def test_ink_bounds_are_centered_for_all_button_widths(self):
        import cairo
        from canvas_panel import centered_text_position
        c=cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32,200,60))
        c.select_font_face('Noto Sans CJK SC', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        c.set_font_size(12)
        for label,width in [('全天',54),('现在',54),('刷新',72),('设置',58)]:
            x,y=centered_text_position(c,label,10,5,width,30)
            e=c.text_extents(label)
            self.assertAlmostEqual(x+e.x_bearing+e.width/2,10+width/2)
            self.assertAlmostEqual(y+e.y_bearing+e.height/2,20)


if __name__=='__main__':unittest.main()
