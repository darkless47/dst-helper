"""Optional real-browser acceptance check. Uses installed Chrome/Edge and stdlib.

Run: python tests/browser_smoke.py
Uses temporary settings and an isolated headless browser profile.
"""
import base64
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dst_helper.server import create_server


class DevTools:
    def __init__(self, url):
        parts = urlsplit(url)
        self.socket = socket.create_connection((parts.hostname, parts.port), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        self.socket.sendall((f'GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        headers = b''
        while not headers.endswith(b'\r\n\r\n'):
            headers += self.read(1)
        if not headers.startswith(b'HTTP/1.1 101 '):
            raise RuntimeError(headers.decode())
        self.counter = 0
        self.errors = []

    def read(self, count):
        result = b''
        while len(result) < count:
            chunk = self.socket.recv(count - len(result))
            if not chunk:
                raise ConnectionError('Browser closed the debugging socket')
            result += chunk
        return result

    def call(self, method, params=None):
        self.counter += 1
        raw = json.dumps(dict(id=self.counter, method=method, params=params or {})).encode()
        n, mask = len(raw), os.urandom(4)
        header = bytes([0x81, 0x80 | n]) if n < 126 else bytes([0x81, 0xFE]) + struct.pack('!H', n) if n < 65536 else bytes([0x81, 0xFF]) + struct.pack('!Q', n)
        self.socket.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(raw)))
        while True:
            first, second = self.read(2)
            length = second & 127
            if length == 126:
                length = struct.unpack('!H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.read(8))[0]
            payload = self.read(length)
            if first & 15 == 8:
                raise ConnectionError('Debugging socket closed')
            message = json.loads(payload)
            if message.get('method') == 'Runtime.exceptionThrown':
                self.errors.append(message)
            if message.get('id') == self.counter:
                if 'error' in message:
                    raise RuntimeError(message['error'])
                return message.get('result', {})

    def js(self, expression):
        result = self.call('Runtime.evaluate', dict(expression=expression, returnByValue=True, awaitPromise=True))
        if result.get('exceptionDetails'):
            raise AssertionError(result['exceptionDetails'])
        return result.get('result', {}).get('value')

    def wait(self, expression, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js(expression):
                return
            time.sleep(.1)
        raise AssertionError('Timed out: ' + expression)

    def settled(self):
        self.wait("document.getElementById('save-status')?.textContent.startsWith('已自动保存') && document.getElementById('ratio-results')?.getAttribute('aria-busy') === 'false'")
        if not self.js("document.getElementById('farm-error').hidden"):
            raise AssertionError(self.js("document.getElementById('farm-error').textContent"))


def run():
    candidates = [Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'), Path('C:/Program Files/Google/Chrome/Application/chrome.exe')]
    browser = next((p for p in candidates if p.exists()), None)
    if browser is None:
        raise SystemExit('No installed Chrome/Edge found; browser checks skipped.')
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        server = create_server(port=0, settings_path=Path(tmp) / 'settings.sqlite')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        process = subprocess.Popen([str(browser), '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1', '--user-data-dir=' + str(Path(tmp) / 'browser'), 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = None
        try:
            port_file = Path(tmp) / 'browser/DevToolsActivePort'
            deadline = time.monotonic() + 15
            while not port_file.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            port = port_file.read_text().splitlines()[0]
            with urlopen(f'http://127.0.0.1:{port}/json/list') as response:
                targets = json.load(response)
            client = DevTools(next(t['webSocketDebuggerUrl'] for t in targets if t['type'] == 'page'))
            client.call('Runtime.enable')
            client.call('Page.enable')
            client.call('Emulation.setDeviceMetricsOverride', dict(width=1440, height=1000, deviceScaleFactor=1, mobile=False))
            base = f'http://127.0.0.1:{server.server_port}'
            client.call('Page.navigate', dict(url=base + '/'))
            client.wait("document.querySelectorAll('.module-card').length === 2")
            client.js("document.querySelector('a.module-card[href=\"/farming\"]').click()")
            client.settled()
            assert client.js("document.getElementById('ratio-count').textContent.startsWith('74 ')")
            assert client.js("document.querySelectorAll('#crop-rows tr:not([hidden])').length") == 14
            print('PASS: home navigation, 14 crops and 74 ratios')
            assert client.js("Array.from(document.querySelectorAll('.ratio-card .ratio-crops:first-of-type')).every(d=>d.querySelectorAll('dt').length>=2 && Array.from(d.querySelectorAll('.ratio-crop-row')).every(r=>r.querySelector('dt') && r.querySelector('dd')))")
            client.js("document.querySelector('[data-ratio-layout=table]').click()")
            assert client.js("document.querySelectorAll('#ratio-results tbody tr').length") == 74
            client.js("document.querySelectorAll('#ratio-results tbody tr button')[2].click()")
            client.settled()
            assert client.js("document.querySelectorAll('#ratio-results tbody tr.selected').length") == 1
            client.js("document.querySelector('[data-ratio-layout=cards]').click()")
            assert client.js("document.querySelectorAll('#ratio-results .ratio-card.selected').length") == 1
            client.js("document.querySelector('[data-ratio-layout=table]').click()")
            print('PASS: crop counts on separate card rows; card/table selection stays consistent across all 74 ratios')

            client.js("document.querySelector('#season-presets button[data-seasons=\"winter\"]').click()")
            client.settled()
            assert client.js("document.getElementById('ratio-count').textContent.startsWith('4 ')")
            assert client.js("document.querySelectorAll('#crop-rows tr:not([hidden])').length") == 5
            client.js("document.getElementById('no-seeds').click()")
            client.settled()
            assert client.js("document.getElementById('ratio-count').textContent.startsWith('0 ')")
            client.js("document.querySelector('#season-presets button[data-seasons=\"\"]').click()")
            client.settled()
            assert client.js("document.querySelectorAll('#crop-rows input[type=checkbox]:checked').length") == 0
            client.js("document.getElementById('all-seeds').click(); document.querySelectorAll('#season-checkboxes input').forEach(i=>{i.checked=true;i.dispatchEvent(new Event('change'));})")
            client.settled()
            assert client.js("document.querySelectorAll('#crop-rows tr:not([hidden])').length") == 1
            assert client.js("document.getElementById('ratio-count').textContent.startsWith('0 ')")
            print('PASS: winter, empty availability, clear preserves seeds, four-season intersection')

            client.js("document.querySelector('#layout-examples button').click()")
            client.settled()
            assert client.js("document.getElementById('layout-report').textContent.includes('所有作物通过')")
            assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 8
            assert client.js("document.getElementById('stress-output').textContent.includes('0–28')")
            client.js("document.querySelectorAll('#layout-examples button')[1].click()")
            client.settled()
            assert client.js("document.getElementById('layout-report').textContent.includes('所有作物通过')")
            client.js("document.getElementById('crop-brush').value=''; for(let r=0;r<3;r++)for(let c=0;c<3;c++)document.getElementById('slot-1-'+r+'-'+c).click()")
            client.settled()
            assert client.js("document.getElementById('layout-report').textContent.includes('均配平')")
            assert client.js("!document.getElementById('layout-report').textContent.includes('所有作物通过')")
            assert client.js("Array.from(document.querySelectorAll('#plant-report tbody tr')).filter(r=>r.textContent.includes('火龙果') && r.textContent.includes('未通过')).length") == 3
            print('PASS: both supplied layouts; six tomatoes / three dragonfruit fail minority family')

            client.js("{let s=document.querySelector('#crop-tomato input[type=number]');s.value='0';s.dispatchEvent(new Event('change'));}")
            client.settled()
            assert client.js("!document.getElementById('ratio-results').textContent.includes('番茄')")
            client.js("{let s=document.querySelector('#crop-tomato input[type=number]');s.value='';s.dispatchEvent(new Event('change'));}")
            client.settled()
            print('PASS: zero stock excludes tomato, blank restores unconstrained stock')

            assert client.js("Array.from(document.getElementById('tile-count').options).map(o=>o.text)") == ['一块田', '两块田', '四块田']
            client.js("{const s=document.getElementById('tile-count');s.value='4';s.dispatchEvent(new Event('change'));}document.getElementById('crop-brush').value='potato';['slot-2-0-0','slot-2-0-1','slot-2-0-2','slot-3-0-0'].forEach(id=>document.getElementById(id).click())")
            client.settled()
            assert client.js("document.querySelectorAll('.plant-slot').length") == 36
            assert client.js("Array.from(document.querySelectorAll('#plant-report tbody tr')).filter(r=>r.textContent.includes('土豆') && r.querySelector('td:nth-child(5)').textContent==='通过').length") == 4
            assert client.js("Array.from(document.querySelectorAll('#plant-report tbody tr')).filter(r=>r.textContent.startsWith('田4')).length") == 1
            client.js("{const s=document.getElementById('tile-count');s.value='2';s.dispatchEvent(new Event('change'));}")
            assert client.js("document.getElementById('tile-count').value") == '4'
            assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 13
            client.js("document.querySelector('[data-ratio-layout=cards]').click()")
            print('PASS: four fields, 36 slots, cross-boundary family on bottom row and safe field-count reduction')

            out = ROOT / '.local/qa'
            out.mkdir(parents=True, exist_ok=True)
            client.js("document.getElementById('ratio-title').scrollIntoView()")
            (out / 'farming-cards.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            client.js("document.querySelector('[data-ratio-layout=table]').click();document.getElementById('ratio-title').scrollIntoView()")
            (out / 'farming-table.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            client.js("document.getElementById('layout-panel').scrollIntoView()")
            assert client.js("(()=>{const b=[...document.querySelectorAll('.tile-board')].map(n=>n.getBoundingClientRect());return b[0].left===b[2].left && b[1].left===b[3].left && b[0].top===b[1].top && b[2].top===b[3].top && b[0].top<b[2].top;})()")
            (out / 'farming-desktop.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            client.call('Emulation.setDeviceMetricsOverride', dict(width=390, height=844, deviceScaleFactor=1, mobile=True))
            client.js("document.getElementById('layout-panel').scrollIntoView()")
            assert client.js("(()=>{const b=[...document.querySelectorAll('.tile-board')].map(n=>n.getBoundingClientRect());return b[0].left===b[2].left && b[1].left===b[3].left && b[0].top===b[1].top && b[2].top===b[3].top && b[0].top<b[2].top;})()")
            assert client.js('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile four-field layout overflows horizontally'
            (out / 'farming-four-fields-mobile.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            client.js('window.scrollTo(0,0)')
            assert client.js('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile page overflows horizontally'
            (out / 'farming-mobile.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            print('PASS: desktop/mobile rendering without page overflow; screenshots in .local/qa')

            client.js("document.querySelector('#crop-tomato .crop-link').click()")
            client.wait("document.getElementById('detail-dialog')?.open && document.getElementById('detail-content')?.dataset.entityId === 'tomato'")
            assert int(client.js("document.getElementById('ingredient-count').textContent")) > 0
            client.js("document.getElementById('close-detail').click();document.querySelector('a[href=\"/farming\"]').click()")
            client.settled()
            assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 13
            assert client.js("document.getElementById('tile-count').value") == '4'
            assert client.js("document.querySelector('[data-ratio-layout=table]').getAttribute('aria-pressed')") == 'true'
            client.js("document.getElementById('crop-brush').value='';['slot-2-0-0','slot-2-0-1','slot-2-0-2','slot-3-0-0'].forEach(id=>document.getElementById(id).click());{const s=document.getElementById('tile-count');s.value='2';s.dispatchEvent(new Event('change'));}")
            client.settled()
            assert client.js("document.querySelectorAll('.plant-slot').length") == 18
            assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 9
            client.js("document.querySelectorAll('#history-flags select').forEach(s=>{s.value='true';s.dispatchEvent(new Event('change'));});document.querySelectorAll('#stress-table select').forEach(s=>{s.value='false';s.dispatchEvent(new Event('change'));})")
            client.settled()
            assert client.js("document.getElementById('stress-output').textContent.includes('符合已记录')")
            client.js("document.querySelectorAll('#stress-table select').forEach((s,i)=>{if(i<2){s.value='true';s.dispatchEvent(new Event('change'));}})")
            client.settled()
            assert client.js("document.getElementById('stress-output').textContent.includes('不满足')")
            client.js("document.getElementById('crop-brush').value='';document.getElementById('slot-0-0-0').click()")
            client.settled()
            assert client.js("document.getElementById('stress-output').textContent.includes('0–28')")
            print('PASS: recorded stress eligibility and resetting history after layout changes')

            client.js("(async()=>{const d=await(await fetch('/api/farming')).json();d.preferences.state.scale=5;await fetch('/api/farming/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:d.preferences.state,expected_version:d.preferences.version})});})()")
            client.js("{const s=document.getElementById('ratio-scale');s.value='7';s.dispatchEvent(new Event('change'));}")
            client.wait("document.getElementById('save-status').textContent.includes('尚未保存')")
            assert client.js("document.getElementById('ratio-scale').value") == '7'
            client.js("document.getElementById('reload-plan').click()")
            client.settled()
            assert client.js("document.getElementById('ratio-scale').value") == '5'
            print('PASS: concurrent save conflict retains the draft, explicit reload gets server state')

            client.js("(async()=>{const d=await(await fetch('/api/farming')).json();d.preferences.state.scale=9;const transfer=new DataTransfer();transfer.items.add(new File([JSON.stringify(d.preferences.state)],'plan.json',{type:'application/json'}));const input=document.getElementById('import-plan');input.files=transfer.files;input.dispatchEvent(new Event('change'));})()")
            client.wait("document.getElementById('ratio-scale').value==='9'")
            client.settled()
            client.js("(async()=>{const d=await(await fetch('/api/farming')).json();d.preferences.state.dataset_version='future';const transfer=new DataTransfer();transfer.items.add(new File([JSON.stringify(d.preferences.state)],'plan.json',{type:'application/json'}));const input=document.getElementById('import-plan');input.files=transfer.files;input.dispatchEvent(new Event('change'));})()")
            client.wait("document.getElementById('farm-error').textContent.includes('导入失败')")
            assert client.js("document.getElementById('ratio-scale').value") == '9'
            print('PASS: plan import restores state and rejects incompatible data without replacing the draft')

            downloads = Path(tmp) / 'downloads'
            downloads.mkdir()
            client.call('Browser.setDownloadBehavior', dict(behavior='allow', downloadPath=str(downloads)))
            client.js("{const s=document.querySelector('#crop-tomato input[type=number]');s.value='15';s.dispatchEvent(new Event('change'));}document.querySelector('#crop-carrot input[type=checkbox]').click();{const s=document.querySelector('#care-checks select');s.value='true';s.dispatchEvent(new Event('change'));}")
            client.settled()
            before_reset = client.js("(async()=> (await(await fetch('/api/farming')).json()).preferences.state)()")
            client.js("document.getElementById('reset-plan').click()")
            assert client.js("document.getElementById('reset-plan-dialog').open")
            assert client.js("Array.from(document.querySelectorAll('.reset-actions button')).map(b=>b.textContent)") == ['Reset', 'Export and Reset']
            assert client.js("document.activeElement.id") == 'close-reset-plan'
            assert client.js('document.documentElement.scrollWidth <= window.innerWidth')
            (out / 'farming-reset-dialog.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            client.js("document.getElementById('close-reset-plan').click()")
            assert not client.js("document.getElementById('reset-plan-dialog').open")
            assert client.js("(async()=> (await(await fetch('/api/farming')).json()).preferences.state)()") == before_reset
            assert not list(downloads.iterdir())

            # A failed save must leave the plan and table preference intact.
            client.js("window.__realFetch=window.fetch;window.__failReset=true;window.fetch=async(...args)=>{if(args[0]==='/api/farming/preferences' && window.__failReset){window.__failReset=false;return new Response(JSON.stringify({error:'Simulated save failure'}),{status:500,headers:{'Content-Type':'application/json'}});}return window.__realFetch(...args);};document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()")
            client.wait("!document.getElementById('reset-plan-error').hidden && !document.getElementById('confirm-reset-plan').disabled")
            assert client.js("document.getElementById('reset-plan-dialog').open")
            assert client.js("document.getElementById('ratio-scale').value") == '9'
            assert client.js("localStorage.getItem('dst-helper.farming-ratio-layout')") == 'table'
            assert client.js("(async()=> (await(await fetch('/api/farming')).json()).preferences.state)()") == before_reset
            assert not list(downloads.iterdir())
            client.js("window.fetch=window.__realFetch;document.getElementById('export-reset-plan').click()")
            client.wait("!document.getElementById('reset-plan-dialog').open")
            client.settled()
            export_file = downloads / 'dst-farming-plan.json'
            deadline = time.monotonic() + 5
            while (not export_file.exists() or list(downloads.glob('*.crdownload'))) and time.monotonic() < deadline:
                time.sleep(.1)
            self_export = json.loads(export_file.read_text(encoding='utf-8'))
            assert self_export == before_reset, 'Export must contain the pre-reset draft'
            assert client.js("(async()=>{const d=await(await fetch('/api/farming')).json();return JSON.stringify(d.preferences.state)===JSON.stringify(d.defaults);})()")
            assert client.js("localStorage.getItem('dst-helper.farming-ratio-layout')") is None
            assert client.js("document.getElementById('ratio-scale').value") == '1'
            assert client.js("document.getElementById('tile-count').value") == '2'
            assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 0
            assert client.js("document.querySelector('[data-ratio-layout=cards]').getAttribute('aria-pressed')") == 'true'
            assert client.js("document.getElementById('ratio-count').textContent.startsWith('74 ')")
            print('PASS: reset confirmation cancellation, failed-save recovery and actual pre-reset JSON download')

            # Hold an existing autosave response open while Reset is confirmed.
            client.js("window.__delaySave=true;window.__saveWaiting=false;window.fetch=async(...args)=>{const response=await window.__realFetch(...args);if(args[0]==='/api/farming/preferences' && window.__delaySave){window.__delaySave=false;window.__saveWaiting=true;await new Promise(r=>setTimeout(r,400));}return response;};{const s=document.getElementById('ratio-scale');s.value='11';s.dispatchEvent(new Event('change'));}")
            client.wait('window.__saveWaiting===true')
            client.js("document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()")
            client.wait("!document.getElementById('reset-plan-dialog').open")
            client.settled()
            client.js('window.fetch=window.__realFetch')
            assert client.js("(async()=>{const d=await(await fetch('/api/farming')).json();return JSON.stringify(d.preferences.state)===JSON.stringify(d.defaults);})()")
            assert len(list(downloads.iterdir())) == 1, 'Reset must not export a second file'

            # Opening the confirmation also pauses an autosave still in the queue.
            client.js("{const s=document.getElementById('ratio-scale');s.value='12';s.dispatchEvent(new Event('change'));}document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()")
            client.wait("!document.getElementById('reset-plan-dialog').open")
            client.settled()
            assert client.js("(async()=>{const d=await(await fetch('/api/farming')).json();return JSON.stringify(d.preferences.state)===JSON.stringify(d.defaults);})()")
            assert len(list(downloads.iterdir())) == 1
            print('PASS: Reset without export clears all saved Farming state and cannot race pending or in-flight autosaves')
            assert not client.errors, client.errors
            print('PASS: cooking ingredient deep link and return preserve farming plan; no JavaScript exceptions')
        finally:
            if client:
                try:
                    client.call('Browser.close')
                except (ConnectionError, OSError):
                    pass
                client.socket.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(3)


if __name__ == '__main__':
    run()
