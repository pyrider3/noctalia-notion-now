import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import calendar_bridge as b

TZ = ZoneInfo('Asia/Shanghai')


class Calendars(unittest.TestCase):
    def notion(self, start, end=None):
        return {'id': 'page', 'url': 'https://notion.so/page', 'properties': {
            'Name': {'type': 'title', 'title': [{'plain_text': '跨时区活动'}]},
            'Date': {'date': {'start': start, 'end': end}}}}

    def test_timezone_and_end_boundary(self):
        event = b.normalize_notion(self.notion('2026-10-07T02:00:00Z', '2026-10-07T03:00:00Z'), 'Date', '工作', TZ)
        active, _ = b.select_events([event], b.parse_time('2026-10-07T10:30:00+08:00', TZ))
        self.assertEqual(len(active), 1)
        self.assertEqual(b.select_events([event], event['end'])[0], [])
        self.assertEqual(b.select_events([event], event['start'])[0], [event])

    def test_all_day_inclusive_notion(self):
        event = b.normalize_notion(self.notion('2026-10-07', '2026-10-08'), 'Date', '工作', TZ)
        self.assertEqual(event['end'] - event['start'], 172800)
        self.assertFalse(b.select_events([event], event['start'] + 3600)[0])

    def test_no_end_is_point(self):
        event = b.normalize_notion(self.notion('2026-10-07T10:00:00+08:00'), 'Date', '工作', TZ)
        self.assertTrue(event['point'])
        self.assertEqual(b.select_events([event], event['start'])[0], [])
        self.assertTrue(b.overlaps(event, event['start'] - 1, event['start'] + 1))

    def test_long_running_range(self):
        event = b.normalize_notion(self.notion('2026-10-01T10:00:00+08:00', '2026-10-10T10:00:00+08:00'), 'Date', '工作', TZ)
        self.assertTrue(b.overlaps(event, b.parse_time('2026-10-07', TZ), b.parse_time('2026-10-08', TZ)))

    def test_overlap_order(self):
        event = b.normalize_notion(self.notion('2026-10-07T10:00:00+08:00', '2026-10-07T11:00:00+08:00'), 'Date', '工作', TZ)
        earlier = dict(event, id='earlier', end=event['end'] - 600)
        active, _ = b.select_events([event, earlier], event['start'] + 60)
        self.assertEqual([x['id'] for x in active], ['earlier', 'notion:page'])

    def test_pagination(self):
        with patch.object(b, 'request_json', side_effect=[{'items': [1], 'nextPageToken': 'cursor'}, {'items': [2]}]) as mock:
            self.assertEqual(b.paged('https://example.com?x=y', {}), [1, 2])
            self.assertIn('&pageToken=cursor', mock.call_args[0][0])
        with patch.object(b, 'request_json', side_effect=[{'results': [1], 'has_more': True, 'next_cursor': 'next'}, {'results': [2]}]) as mock:
            self.assertEqual(b.paged('https://example.com', {}, 'results', {'page_size': 100}), [1, 2])
            self.assertEqual(mock.call_args[0][2]['start_cursor'], 'next')

    def test_private_atomic_cache_and_failure_retains_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            config, cache = folder / 'config/config.json', folder / 'state/events.json'
            now = dt.datetime.now(TZ).timestamp()
            event = {'id': 'notion:one', 'provider': 'notion', 'start': now - 60, 'end': now + 600}
            b.save_json(config, {'notion': {'token': 'test'}})
            b.save_json(cache, {'events': [event], 'sources': {'notion': {'updated': now - 300}}})
            with patch.object(b, 'CONFIG', config), patch.object(b, 'CACHE', cache), patch.object(b, 'STATE_DIR', cache.parent), \
                 patch.object(b, 'notion_events', side_effect=b.CalendarError('网络失败')):
                b.sync()
            saved = b.read_json(cache)
            self.assertTrue(saved['events'][0]['stale'])
            self.assertFalse(saved['sources']['notion']['ok'])
            self.assertTrue(saved['sources']['notion']['connected'])
            self.assertNotIn('google', saved['sources'])
            self.assertEqual(cache.stat().st_mode & 0o777, 0o600)

    def test_database_id_from_url(self):
        self.assertEqual(b.resolve_database_id('https://www.notion.so/team/Tasks-0123456789abcdef0123456789abcdef?v=xyz'), '0123456789abcdef0123456789abcdef')
        with self.assertRaises(b.CalendarError):
            b.resolve_database_id('invalid')

    def test_setup_does_not_expose_saved_credentials(self):
        with patch.object(b, 'read_json', side_effect=[{'notion': {'token': 'secret-test'}, 'google': {'client': {'client_secret': 'google-secret'}}}, {}]):
            page = b.setup_page(csrf='csrf-test')
        self.assertNotIn('secret-test', page)
        self.assertNotIn('google-secret', page)
        self.assertIn('csrf-test', page)


if __name__ == '__main__':
    unittest.main()
