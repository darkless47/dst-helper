"""Optional real-browser acceptance check. Uses installed Chrome/Edge and stdlib.

Run: python tests/browser_smoke.py
Uses isolated browser profiles; no shared user preferences are written.
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
        raise AssertionError('Timed out: ' + expression + '\nPage: ' + str(self.js("document.querySelector('#signature-results')?.innerText || document.querySelector('#farm-error')?.innerText")) + '\nErrors: ' + str(self.errors))

    def settled(self):
        self.wait("document.getElementById('planner')?.hidden === false && document.getElementById('ratio-results')?.getAttribute('aria-busy') === 'false'")
        if not self.js("document.getElementById('farm-error').hidden"):
            raise AssertionError(self.js("document.getElementById('farm-error').textContent"))


def run():
    candidates = [Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'), Path('C:/Program Files/Google/Chrome/Application/chrome.exe')]
    browser = next((p for p in candidates if p.exists()), None)
    if browser is None:
        raise SystemExit('No installed Chrome/Edge found; browser checks skipped.')
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        server = create_server(port=0)
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
            assert client.js("Array.from(document.querySelectorAll('#care-reminders h3')).map(n=>n.textContent)") == ['水分', '照料', '起始养分', '周围杂物']
            assert client.js("document.querySelectorAll('#care-panel input,#care-panel select,#care-panel textarea,#care-panel button,#care-panel details').length") == 0
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
            client.js("document.getElementById('crop-brush').value='';document.getElementById('slot-0-0-0').click()")
            client.settled()
            assert client.js("document.querySelectorAll('#care-reminders .care-item').length") == 4
            assert client.js("document.querySelectorAll('#history-flags,#stress-table,#stress-output,#care-checks').length") == 0
            client.js("document.getElementById('care-panel').scrollIntoView()")
            (out / 'farming-care-reminders.png').write_bytes(base64.b64decode(client.call('Page.captureScreenshot')['data']))
            print('PASS: section 05 has exactly four static care reminders and no recording controls')

            assert client.js("document.querySelectorAll('#import-plan,#export-plan,#reload-plan,#save-plan,#export-reset-plan,input[type=file]').length") == 0
            client.js("{const s=document.getElementById('ratio-scale');s.value='7';s.dispatchEvent(new Event('change'));}")
            client.settled()
            client.js('window.__beforeReload = true')
            client.call('Page.reload')
            client.wait("!window.__beforeReload && document.readyState === 'complete'")
            client.settled()
            assert client.js("document.getElementById('ratio-scale').value") == '7'
            print('PASS: browser plan survives reload; all file-transfer and server-save controls removed')

            # A separate browser context models a second user on the same server.
            with urlopen(f'http://127.0.0.1:{port}/json/version') as response:
                browser_socket = json.load(response)['webSocketDebuggerUrl']
            control = DevTools(browser_socket)
            context = control.call('Target.createBrowserContext')['browserContextId']
            second = None
            try:
                target = control.call('Target.createTarget', dict(url='about:blank', browserContextId=context))['targetId']
                with urlopen(f'http://127.0.0.1:{port}/json/list') as response:
                    targets = json.load(response)
                second = DevTools(next(t['webSocketDebuggerUrl'] for t in targets if t['id'] == target))
                second.call('Runtime.enable'); second.call('Page.enable')
                second.call('Page.navigate', dict(url=base + '/farming'))
                second.settled()
                assert second.js("document.getElementById('ratio-scale').value") == '1'
                second.js("{const s=document.getElementById('ratio-scale');s.value='3';s.dispatchEvent(new Event('change'));}")
                second.settled()
                assert client.js("document.getElementById('ratio-scale').value") == '7'
                second.call('Page.navigate', dict(url=base + '/cooking'))
                second.wait("typeof state !== 'undefined' && state.data?.settings && document.getElementById('results').getAttribute('aria-busy') === 'false'")
                assert second.js('state.data.settings.rarities.butter') == 80
                assert len(second.js('state.data.signature.exclusions.dish_ids')) == 3

                client.call('Page.navigate', dict(url=base + '/cooking'))
                client.wait("typeof state !== 'undefined' && state.data?.settings && document.getElementById('results').getAttribute('aria-busy') === 'false'")
                assert client.js('state.data.settings.rarities.butter') == 80
                client.js("openIngredientDetail('butter')")
                client.wait("document.getElementById('rarity-input')?.value === '80'")
                client.js("document.getElementById('rarity-input').value='-9';document.querySelector('.rarity-editor').requestSubmit()")
                client.wait('state.data.settings.rarities.butter === -9')
                client.js("document.getElementById('close-detail').click();setView('signature');document.getElementById('manage-signature-exclusions').click()")
                client.js("document.getElementById('clear-signature-exclusions').click()")
                assert client.js('state.data.signature.exclusions.dish_ids.length') == 0
                client.js("document.getElementById('close-signature-exclusions').click()")
                assert second.js('state.data.settings.rarities.butter') == 80
                assert len(second.js('state.data.signature.exclusions.dish_ids')) == 3
                client.js('window.__beforeReload = true')
                client.call('Page.reload')
                client.wait("!window.__beforeReload && document.readyState === 'complete'")
                client.wait("typeof state !== 'undefined' && state.data?.settings && document.getElementById('results').getAttribute('aria-busy') === 'false'")
                assert client.js('state.data.settings.rarities.butter') == -9
                assert client.js('state.data.signature.exclusions.dish_ids.length') == 0
                print('PASS: two independent browsers have isolated plans, rarities and exclusions; Cooking edits persist')

                # Filter full calculation results locally; excluded winners still compete.
                client.js("setView('signature');signatureUI.openIngredient('twigs')")
                client.wait("document.getElementById('signature-results').getAttribute('aria-busy') === 'false' && Boolean(document.querySelector('#signature-results [data-dish-id]'))", timeout=30)
                assert client.js("Boolean(document.querySelector('[data-dish-id=\"huiji:蒸树枝\"]'))")
                client.js("document.getElementById('manage-signature-exclusions').click();document.getElementById('signature-exclusion-search').value='蒸树枝';document.getElementById('signature-exclusion-search').dispatchEvent(new Event('input'));document.querySelector('#exclusion-candidates [data-exclusion-dish=\"huiji:蒸树枝\"] button').click();document.getElementById('close-signature-exclusions').click()")
                assert not client.js("Boolean(document.querySelector('[data-dish-id=\"huiji:蒸树枝\"]'))")
                assert client.js("(async()=>{const r=await(await fetch('/api/predict?cooker=crock_pot&ingredient=twigs&ingredient=twigs&ingredient=twigs&ingredient=twigs')).json();return r.outcomes.some(d=>d.dish_id==='huiji:蒸树枝');})()")
                client.js("setView('ingredients');document.getElementById('clear-rarities').click()")
                assert client.js('Object.keys(state.data.settings.rarities).length') == 0
                assert client.js('state.data.signature.exclusions.dish_ids.length') == 1
                client.js('window.__beforeReload = true')
                client.call('Page.reload')
                client.wait("!window.__beforeReload && document.readyState === 'complete'")
                client.wait("typeof state !== 'undefined' && state.data?.settings && document.getElementById('results').getAttribute('aria-busy') === 'false'")
                assert client.js('Object.keys(state.data.settings.rarities).length') == 0
                assert client.js('state.data.signature.exclusions.dish_ids.length') == 1
                print('PASS: exclusions filter only displayed recommendations; clear-all rarity remains empty after reload')
                cooking_before = client.js("[localStorage.getItem('dst-helper.cooking.rarities.v1'),localStorage.getItem('dst-helper.cooking.exclusions.v1')]")
                client.call('Page.navigate', dict(url=base + '/farming')); client.settled()
                before_reset = client.js("localStorage.getItem('dst-helper.farming.plan.v1')")
                client.js("document.getElementById('reset-plan').click();document.getElementById('close-reset-plan').click()")
                assert client.js("localStorage.getItem('dst-helper.farming.plan.v1')") == before_reset

                # Quota/security errors must retain the current plan and surface a warning.
                client.js("window.__setItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new DOMException('Quota exceeded','QuotaExceededError');};document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()")
                client.wait("!document.getElementById('reset-plan-error').hidden")
                assert client.js("document.getElementById('reset-plan-dialog').open")
                assert client.js("localStorage.getItem('dst-helper.farming.plan.v1')") == before_reset
                assert client.js("document.getElementById('ratio-scale').value") == '7'
                client.js("Storage.prototype.setItem=window.__setItem;document.getElementById('confirm-reset-plan').click()")
                client.settled()
                assert not client.js("document.getElementById('reset-plan-dialog').open")
                assert client.js("document.getElementById('ratio-scale').value") == '1'
                assert client.js("document.querySelectorAll('.plant-slot.planted').length") == 0
                assert client.js("localStorage.getItem('dst-helper.farming-ratio-layout')") is None
                assert client.js("[localStorage.getItem('dst-helper.cooking.rarities.v1'),localStorage.getItem('dst-helper.cooking.exclusions.v1')]") == cooking_before
                print('PASS: reset cancellation, storage failure recovery, and Farming reset leaves Cooking untouched')

                # Delay a calculation, then reset: an older response cannot restore the plan.
                client.js("window.__fetch=window.fetch;window.__waiting=false;window.__delay=true;window.fetch=async(...args)=>{const response=await window.__fetch(...args);if(args[0]==='/api/farming/analyze' && window.__delay){window.__delay=false;window.__waiting=true;await new Promise(r=>setTimeout(r,500));}return response;};{const s=document.getElementById('ratio-scale');s.value='11';s.dispatchEvent(new Event('change'));}")
                client.wait('window.__waiting')
                client.js("document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()")
                client.settled()
                assert client.js("JSON.parse(localStorage.getItem('dst-helper.farming.plan.v1')).value.scale") == 1
                assert client.js("document.getElementById('ratio-scale').value") == '1'
                client.js('window.fetch=window.__fetch')
                print('PASS: reset cannot race an in-flight calculation')
                # Failed computation must not prevent immediate browser autosave.
                client.js("window.fetch=async(...args)=>{if(args[0]==='/api/farming/analyze')throw new Error('Simulated offline calculation');return window.__fetch(...args);};{const s=document.getElementById('ratio-scale');s.value='15';s.dispatchEvent(new Event('change'));}")
                client.wait("document.getElementById('ratio-count').textContent === '计算失败'")
                assert client.js("JSON.parse(localStorage.getItem('dst-helper.farming.plan.v1')).value.scale") == 15
                assert client.js("document.getElementById('save-status').textContent.startsWith('已自动保存')")
                client.js("window.fetch=window.__fetch;document.querySelector('#ratio-results button').click()")
                client.settled()
                print('PASS: calculation failures do not prevent browser autosave; retry recovers')

                # Clearing Cooking preferences must fail visibly when storage is blocked.
                second.js("window.__setItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new DOMException('Blocked','SecurityError');};setView('ingredients');document.getElementById('clear-rarities').click();setView('signature');document.getElementById('manage-signature-exclusions').click();document.getElementById('clear-signature-exclusions').click()")
                assert second.js('state.data.settings.rarities.butter') == 80
                assert len(second.js('state.data.signature.exclusions.dish_ids')) == 3
                assert second.js("Boolean(document.getElementById('browser-storage-warning'))")
                second.js('Storage.prototype.setItem=window.__setItem')
                second.call('Page.navigate', dict(url=base + '/farming')); second.settled()
                second.js("localStorage.setItem('dst-helper.farming.plan.v1','{broken');window.__beforeReload=true")
                second.call('Page.reload'); second.wait("!window.__beforeReload && document.readyState === 'complete'"); second.settled()
                assert second.js("localStorage.getItem('dst-helper.farming.plan.v1')") == '{broken'
                assert second.js("document.getElementById('ratio-scale').value") == '1'
                assert second.js("Boolean(document.getElementById('browser-storage-warning'))")
                second.js("document.getElementById('reset-plan').click();document.getElementById('confirm-reset-plan').click()"); second.settled()
                assert second.js("JSON.parse(localStorage.getItem('dst-helper.farming.plan.v1')).schema_version") == 1
                print('PASS: blocked Cooking storage retains values; corrupt Farming storage is preserved until reset')
                assert not second.errors, second.errors
            finally:
                if second: second.socket.close()
                control.call('Target.disposeBrowserContext', dict(browserContextId=context))
                control.socket.close()
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
