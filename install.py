#!/usr/bin/env python3
"""Install this user's local Noctalia plugin, preserving existing settings."""
from pathlib import Path
import datetime
import shutil
import subprocess
import tomllib

source = Path(__file__).resolve().parent
home = Path.home()
target = home / '.config/noctalia/plugins/notion-now'
settings = home / '.local/state/noctalia/settings.toml'
units = home / '.config/systemd/user'
target.mkdir(parents=True, exist_ok=True)
units.mkdir(parents=True, exist_ok=True)
for name in ['plugin.toml', 'widget.luau', 'panel.luau', 'service.luau', 'preferences.luau', 'timeline.luau', 'settings.luau', 'canvas_panel.py', 'canvas_engine.py', 'bar_canvas.py', 'bar_model.py', 'calendar_bridge.py']:
    shutil.copy2(source / name, target / name)

script = target / 'calendar_bridge.py'
(units / 'notion-now-sync.service').write_text(f'''[Unit]
Description=Read-only Notion calendar sync
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {script} sync
UMask=0077
TimeoutStartSec=300
NoNewPrivileges=true
''')
(units / 'notion-now-sync.timer').write_text('''[Unit]
Description=Refresh Noctalia calendar every two minutes

[Timer]
OnStartupSec=15
OnUnitInactiveSec=120
AccuracySec=5
Persistent=true

[Install]
WantedBy=timers.target
''')
(units / 'notion-now-setup.service').write_text(f'''[Unit]
Description=Local calendar connection page

[Service]
Type=simple
ExecStart=/usr/bin/python3 {script} serve
UMask=0077
NoNewPrivileges=true
''')

text = settings.read_text()
parsed = tomllib.loads(text)
backup = settings.with_name('settings.toml.bak-notion-now-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
shutil.copy2(settings, backup)
widget = 'notion-now'
plugin = 'pyrider3/notion-now'
start = parsed['bar']['default'].get('start', [])
if widget not in start:
    # Preserve formatting and unrelated config, alter only this exact array.
    import re
    section_start = text.index('[bar.default]')
    section_end = text.find('\n[', section_start + 1)
    if section_end == -1:
        section_end = len(text)
    section = text[section_start:section_end]
    match = re.search(r'^start\s*=\s*\[[^\]]*\]', section, re.M)
    if not match:
        raise RuntimeError('Could not find bar.default.start; no settings changed')
    insertion = start.index('clock') + 1 if 'clock' in start else len(start)
    start.insert(insertion, widget)
    import json
    section = section[:match.start()] + 'start = ' + json.dumps(start) + section[match.end():]
    text = text[:section_start] + section + text[section_end:]
if widget not in parsed.get('widget', {}):
    text += '\n[widget.notion-now]\ntype = "pyrider3/notion-now:now"\n'
tomllib.loads(text)
settings.write_text(text)
subprocess.run(['noctalia', 'config', 'validate', str(settings)], check=True)
subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
subprocess.run(['systemctl', '--user', 'enable', '--now', 'notion-now-sync.timer'], check=True)
subprocess.run(['systemctl', '--user', 'start', 'notion-now-sync.service', 'notion-now-setup.service'], check=True)
subprocess.run(['noctalia', 'msg', 'plugins', 'update', 'local'], check=True)
subprocess.run(['noctalia', 'msg', 'plugins', 'enable', plugin], check=True)
subprocess.run(['noctalia', 'msg', 'config-reload'], check=True)
print('Installed Notion Now. Setup: http://127.0.0.1:18743')
