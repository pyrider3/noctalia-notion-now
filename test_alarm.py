import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from alarm_store import AlarmStore, countdown, next_time

class AlarmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = AlarmStore(self.tmp.name)

    def test_persist_claim_once_and_restart(self):
        alarm = self.store.schedule(200, now=100)
        other = AlarmStore(self.tmp.name)
        self.assertEqual(other.read(), alarm)
        self.assertIsNone(other.claim(199))
        self.assertEqual(other.claim(250)['status'], 'ringing')
        self.assertIsNone(self.store.claim(251))
        self.assertEqual(other.read()['status'], 'ringing')
        self.assertEqual((Path(self.tmp.name)/'alarm.json').stat().st_mode & 0o777, 0o600)

    def test_snooze_dismiss_and_old_notification_race(self):
        first = self.store.schedule(200, now=100)
        self.store.claim(200)
        self.store.snooze(first['id'], now=210)
        later = self.store.read()
        self.assertEqual(later['due'], 510)
        self.assertNotEqual(later['id'],first['id'])
        self.store.cancel(first['id'])
        self.assertEqual(self.store.read()['status'], 'scheduled')
        self.store.cancel(later['id'])
        self.assertIsNone(self.store.claim(999))

    def test_save_failure_preserves_previous_alarm_and_sound(self):
        self.store.sound()
        first = self.store.schedule(200, now=100)
        self.assertFalse(first['sound'])
        with patch('alarm_store.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.store.schedule(300, now=100)
        self.assertEqual(self.store.read(),first)
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')),[])

    def test_future_time_crosses_midnight(self):
        tz=ZoneInfo('Asia/Shanghai')
        now=dt.datetime(2026,10,31,23,59,tzinfo=tz).timestamp()
        self.assertEqual(dt.datetime.fromtimestamp(next_time(0,5,tz,now),tz).day,1)
        self.assertEqual(countdown(dict(status='scheduled',due=now+61),now),'01:01')
        self.assertEqual(countdown(dict(status='ringing'),now),'时间到了')
        for due in [now,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): self.store.schedule(due, now)

    def test_release_coordinates_survive_subsequent_pointer_motion(self):
        from canvas_panel import Canvas
        c=Canvas(); c.alarm_store=self.store
        c.hitboxes=[(0,0,536,500,'alarm:close'),(166,245,326,30,'alarm:cancel')]
        c.alarm_open=True
        self.store.schedule(200,now=100)
        c.input(dict(seq=1,session=2,down_serial=0,released_serial=0,pressed=False,x=0,y=0,wheel=0))
        c.input(dict(seq=3,session=2,down_serial=1,released_serial=1,pressed=False,
            down_x=.62,down_y=.52,up_x=.62,up_y=.52,x=.9,y=.95,wheel=0))
        self.assertEqual(self.store.read()['status'],'dismissed')
        self.assertTrue(c.alarm_open)

    def test_canvas_quick_cancel_and_snooze(self):
        import cairo
        from canvas_panel import Canvas, WIDTH, HEIGHT, SCALE
        c=Canvas(); c.alarm_store=self.store
        c.alarm_action('toggle')
        self.assertTrue(c.alarm_open)
        c.alarm_action('quick:5')
        alarm=self.store.read()
        self.store.claim(alarm['due'])
        c.alarm_action('snooze')
        self.assertEqual(self.store.read()['status'],'scheduled')
        c.alarm_action('cancel')
        self.assertEqual(self.store.read()['status'],'dismissed')
        c.alarm_progress=1
        with patch('canvas_panel.save'):
            c.paint(cairo.ImageSurface(cairo.FORMAT_ARGB32,WIDTH*SCALE,HEIGHT*SCALE))
        self.assertTrue(all(box[-1].startswith('alarm:') for box in c.hitboxes))

class AlarmKeyboardTests(unittest.TestCase):
    def test_type_tab_validation_backspace_and_enter(self):
        from canvas_panel import Canvas
        with tempfile.TemporaryDirectory() as root:
            c=Canvas();c.alarm_store=AlarmStore(root);c.alarm_open=True
            c.alarm_action('edit:hour')
            c.alarm_keyboard('text','09')
            self.assertEqual(c.alarm_hour,9)
            c.alarm_keyboard('key','Tab')
            self.assertEqual(c.alarm_field,'minute')
            c.alarm_keyboard('text','99')
            c.alarm_keyboard('key','Return')
            self.assertNotEqual(c.alarm_store.read().get('status'),'scheduled')
            self.assertIn('00–59',c.alarm_error)
            c.alarm_keyboard('key','Ctrl+A')
            c.alarm_keyboard('text','31')
            c.alarm_keyboard('key','Backspace')
            c.alarm_keyboard('text','5')
            c.alarm_keyboard('key','Return')
            v=c.alarm_store.read()
            self.assertEqual(v['status'],'scheduled')
            self.assertEqual(dt.datetime.fromtimestamp(v['due'],c.tz).strftime('%H:%M'),'09:35')

    def test_key_queue_preserves_fast_typing_without_replay(self):
        from canvas_panel import Canvas
        with tempfile.TemporaryDirectory() as root:
            c=Canvas();c.alarm_store=AlarmStore(root);c.alarm_open=True
            c.alarm_action('edit:hour')
            base=dict(session=8,down_serial=0,released_serial=0,pressed=False,x=0,y=0,wheel=0)
            c.input(dict(base,seq=1,key_serial=0,keys=[]))
            keys=[dict(id=1,kind='text',value='1'),dict(id=2,kind='text',value='8'),dict(id=3,kind='key',value='Tab'),dict(id=4,kind='text',value='4'),dict(id=5,kind='text',value='5')]
            c.input(dict(base,seq=6,key_serial=5,keys=keys))
            self.assertEqual((c.alarm_hour,c.alarm_minute),(18,45))
            c.alarm_minute=50
            c.input(dict(base,seq=7,key_serial=5,keys=keys))
            self.assertEqual(c.alarm_minute,50)

if __name__=='__main__': unittest.main()
