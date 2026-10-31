import unittest
from bar_model import Selection, WidthMotion, active_events


def event(ident,title='工作',end=200):
    return dict(id=ident,title=title,start=0,end=end)


class BarBehavior(unittest.TestCase):
    def test_default_is_stable_and_manual_wheel_then_end_fallback(self):
        data={'events':[event('a',end=200),event('b',end=300),event('all',end=400)|{'all_day':True}]}
        s=Selection()
        chosen,active,running=s.choose(data,{},100)
        self.assertEqual(chosen['id'],'a');self.assertEqual(len(active),2)
        self.assertEqual(s.choose(data,{},110,steps=1)[0]['id'],'b')
        self.assertEqual(s.choose(data,{},150)[0]['id'],'b')
        self.assertEqual(s.choose(data,{},301)[0],None)

    def test_pin_takes_priority_and_new_pin_resets_manual_override(self):
        s=Selection();data={'events':[event('a'),event('b')]}
        self.assertEqual(s.choose(data,{'pinned_event_id':'b'},100)[0]['id'],'b')
        self.assertEqual(s.choose(data,{'pinned_event_id':'b'},101,steps=1)[0]['id'],'a')
        self.assertEqual(s.choose(data,{'pinned_event_id':'a'},102)[0]['id'],'a')
        self.assertEqual(s.choose(data,{'pinned_event_id':'b'},103)[0]['id'],'b')

    def test_hover_pauses_rotation_and_manual_pause_is_thirty_seconds(self):
        s=Selection();data={'events':[event('a',end=500),event('b',end=500)]};prefs={'display_mode':'rotate','rotate_seconds':5}
        s.choose(data,prefs,100)
        self.assertEqual(s.choose(data,prefs,110,hovered=True)[0]['id'],'a')
        self.assertEqual(s.choose(data,prefs,112)[0]['id'],'a')
        self.assertEqual(s.choose(data,prefs,116)[0]['id'],'b')
        self.assertEqual(s.choose(data,prefs,117,steps=1)[0]['id'],'a')
        self.assertEqual(s.choose(data,prefs,140)[0]['id'],'a')
        self.assertEqual(s.choose(data,prefs,148)[0]['id'],'b')

    def test_width_motion_preserves_velocity_and_converges_without_jump(self):
        values=[]
        for hz in [30,60,120]:
            m=WidthMotion(100);m.target=300
            previous=m.width
            for _ in range(hz):
                m.step(1/hz)
                self.assertGreaterEqual(m.width,previous)
                self.assertLessEqual(m.width,300)
                previous=m.width
            values.append(m.width)
            velocity=m.velocity;m.target=150
            self.assertEqual(m.velocity,velocity)
            m.step(.005);self.assertLess(abs(m.width-300),5)
            for _ in range(hz*2):m.step(1/hz)
            self.assertAlmostEqual(m.width,150,places=1)
        self.assertLess(max(values)-min(values),.01)


if __name__=='__main__':unittest.main()

class BarCanvasBehavior(unittest.TestCase):
    def test_badge_warning_and_future_are_separate(self):
        from bar_canvas import Bar
        b=Bar();b.data={'updated':100,'sources':{'notion':{'ok':True,'connected':True}},'events':[event('a',end=200),event('b',end=300)]}
        b.skin={};b.prefs={'accent_color':False}
        item=b.content(100)
        self.assertEqual(item['badge'],'+1')
        self.assertNotIn('/',item['title'])
        self.assertTrue(item['warning'])
        b.prefs['end_warning']=False
        self.assertFalse(b.content(100)['warning'])
        b.prefs['show_progress']=False
        self.assertFalse(b.content(100)['show_progress'])
        b.data['events']=[dict(id='future',title='下一场',start=400,end=500)]
        item=b.content(100)
        self.assertFalse(item['show_progress'])
        self.assertEqual(item['badge'],'')
        self.assertTrue(item['title'].startswith('下一项 '))
