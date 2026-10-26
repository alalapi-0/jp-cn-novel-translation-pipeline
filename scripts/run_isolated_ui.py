#!/usr/bin/env python3
"""Run actual Playwright browsers inside the synthetic PID/mount/network view."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from isolated_checks import require_view


def main():
    require_view()
    env=dict(os.environ)
    for name in ('DISPLAY','WAYLAND_DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS'):
        env.pop(name,None)
    env['PLAYWRIGHT_PORT']='5174'
    command=['npm','run','test:ui','--','--workers=1','--retries=0',*sys.argv[1:]]
    process=subprocess.Popen(command,env=env)
    start=int(Path(f'/proc/{process.pid}/stat').read_text().rsplit(') ',1)[1].split()[19])
    code=process.wait()
    with socket.socket() as connection:
        connection.settimeout(1)
        port_closed=connection.connect_ex(('127.0.0.1',5174))!=0
    evidence=Path('artifacts/ui-runtime.json');evidence.parent.mkdir(parents=True,exist_ok=True)
    evidence.write_text(json.dumps({'schema':'private-ui-runtime/1','browser':'real Chromium headless; independent temporary profile; no physical display connection',
        'npm_pid_namespace':process.pid,'npm_start_ticks':start,'npm_exited':process.poll() is not None,'npm_exit':code,'fixture_port_closed':port_closed,
        'boundary':'private PID/mount/network namespace; cleared environment; original homes/data hidden; no external network',
        'headed_display':'unverified: isolated Xvfb Mesa startup segfault retained; no foreground fallback',
        'outer_cleanup':'namespace exits with its init; host runner verifies command completion/removes disposable view'},indent=2)+'\n')
    if not port_closed:raise RuntimeError('owned UI fixture port remained open')
    return code

if __name__=='__main__':raise SystemExit(main())
