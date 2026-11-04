"""Exercise the real HTTP server against a temporary database, without GPIO."""
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port=probe.getsockname()[1]
    process=subprocess.Popen([sys.executable,str(ROOT/'run_app.py'),'--port',str(port),'--db',str(Path(directory)/'smoke.db')],
                             cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    base=f'http://127.0.0.1:{port}'
    def request(path,payload=None):
        body=json.dumps(payload).encode() if payload is not None else None
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json'}),timeout=4) as response:
            return json.load(response)
    try:
        for _ in range(50):
            try: state=request('/api/state');break
            except OSError: time.sleep(.1)
        else: raise AssertionError('Server did not start')
        idle=socket.create_connection(('127.0.0.1',port))
        try:
            start=time.monotonic();request('/api/state')
            assert time.monotonic()-start<3,'Idle browser connection blocked state'
        finally:idle.close()
        request('/api/buzz',{'player':1})
        request('/api/action',{'action':'wrong'})
        state=request('/api/state')
        assert state['attempts'][0]['interrupt'] is True
        assert request('/api/games')
        print('PASS HTTP: startup, idle connection recovery, buzz logging, game listing')
    finally:
        process.terminate();process.wait(timeout=5)
