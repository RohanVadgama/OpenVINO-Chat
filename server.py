"""Local OpenVINO chat. Python standard library only; uses installed OVMS."""
import base64
import re
import atexit
import hashlib
import http.server
import json
import math
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
IMAGES = DATA / 'images'
IMAGES.mkdir(exist_ok=True)
INSTALL = Path(os.environ['LOCALAPPDATA']) / 'Programs/AI Playground/resources'
OVMS = INSTALL / 'OpenVINO/ovms'
PORT = 48200
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
STATE = {'phase': 'idle', 'model': None, 'device': None, 'error': None}
PROCESS = None
LOG = None
BACKEND_PORT = None


def roots():
    defaults = [str(INSTALL / 'models/LLM/openvino'), str(ROOT.parents[1] / 'work/qwen35-openvino')]
    try:
        return defaults + json.loads((DATA / 'folders.json').read_text())
    except (OSError, ValueError):
        return defaults


def valid_model(p):
    return (p / 'config.json').is_file() and any((p / n).is_file() for n in ['openvino_model.xml', 'openvino_language_model.xml'])


def models():
    result = {}
    for r in roots():
        p = Path(r)
        candidates = [p]
        if p.is_dir():
            candidates += [x for x in p.iterdir() if x.is_dir()]
        for candidate in candidates:
            if not valid_model(candidate):
                continue
            name = candidate.name.replace('OpenVINO---', '').replace('-int4-gq-ov', ' · INT4').replace('-int4-ov', ' · INT4')
            if candidate.name == 'qwen35-openvino':
                name = 'Qwen3.5 4B · INT4'
            key = hashlib.sha256(str(candidate.resolve()).lower().encode()).hexdigest()[:16]
            result[key] = {'id': key, 'name': name, 'path': str(candidate.resolve()), 'vision': any(candidate.glob('openvino_vision*.xml'))}
    return list(result.values())


def unload():
    global PROCESS, LOG
    if PROCESS:
        PROCESS.terminate()
        try:
            PROCESS.wait(timeout=12)
        except subprocess.TimeoutExpired:
            PROCESS.kill()
            PROCESS.wait()
    PROCESS = None
    if LOG:
        LOG.close()
        LOG = None
    STATE.update(phase='idle', model=None, device=None, error=None)


def load(model_id, device):
    global PROCESS, LOG, BACKEND_PORT
    if device not in ['GPU', 'CPU']:
        raise ValueError('Choose GPU or CPU.')
    model = next((m for m in models() if m['id'] == model_id), None)
    if not model:
        raise ValueError('Model folder is no longer available. Refresh the model list.')
    if PROCESS and PROCESS.poll() is None and STATE['model'] == model_id and STATE['device'] == device:
        return
    unload()
    STATE.update(phase='loading', model=model_id, device=device)
    cache = DATA / model_id
    cache.mkdir(exist_ok=True)
    path = json.dumps(Path(model['path']).as_posix())
    graph = '''input_stream: "HTTP_REQUEST_PAYLOAD:input"
output_stream: "HTTP_RESPONSE_PAYLOAD:output"
node {
 name: "LLMExecutor"
 calculator: "HttpLLMCalculator"
 input_stream: "LOOPBACK:loopback"
 input_stream: "HTTP_REQUEST_PAYLOAD:input"
 input_side_packet: "LLM_NODE_RESOURCES:llm"
 output_stream: "LOOPBACK:loopback"
 output_stream: "HTTP_RESPONSE_PAYLOAD:output"
 input_stream_info { tag_index: "LOOPBACK:0" back_edge: true }
 node_options { [type.googleapis.com/mediapipe.LLMCalculatorOptions] {
 models_path: MODEL_PATH
 device: DEVICE
 max_num_seqs: 1
 enable_prefix_caching: false
 } }
 input_stream_handler { input_stream_handler: "SyncSetInputStreamHandler" options {
 [mediapipe.SyncSetInputStreamHandlerOptions.ext] { sync_set { tag_index: "LOOPBACK:0" } } } }
}'''.replace('MODEL_PATH', path).replace('DEVICE', json.dumps(device))
    (cache / 'graph.pbtxt').write_text(graph)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        BACKEND_PORT = s.getsockname()[1]
    env = os.environ.copy()
    env['PYTHONHOME'] = str(OVMS / 'python')
    env['PYTHONNOUSERSITE'] = '1'
    env['PATH'] = str(OVMS) + os.pathsep + str(OVMS / 'python') + os.pathsep + env.get('PATH', '')
    env['ESPEAK_DATA_PATH'] = str(OVMS / 'espeak-ng-data')
    LOG = (DATA / 'backend.log').open('w', encoding='utf-8')
    PROCESS = subprocess.Popen([str(OVMS / 'ovms.exe'), '--model_name', 'local', '--model_path', str(cache),
        '--rest_port', str(BACKEND_PORT), '--rest_bind_address', '127.0.0.1', '--cache_dir', str(cache / 'cache')],
        env=env, cwd=str(OVMS), stdout=LOG, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if PROCESS.poll() is not None:
            raise RuntimeError('OpenVINO could not load this model. Details are in data/backend.log.')
        try:
            with OPENER.open(f'http://127.0.0.1:{BACKEND_PORT}/v1/config', timeout=1) as response:
                status = response.read().decode()
                if 'AVAILABLE' in status:
                    STATE['phase'] = 'ready'
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.4)
    raise RuntimeError('Model loading timed out after four minutes. See data/backend.log.')


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def safe_host(self):
        return self.headers.get('Host') in [f'127.0.0.1:{PORT}', f'localhost:{PORT}']

    def reply(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.safe_host():
            return self.reply({'error': 'Invalid host'}, 403)
        if self.path == '/api/status':
            if PROCESS and PROCESS.poll() is not None and STATE['phase'] == 'ready':
                STATE.update(phase='error', error='The model server stopped. Load the model again.')
            return self.reply(dict(STATE, models=models(), token=TOKEN))
        if self.path.startswith('/images/'):
            name = self.path.removeprefix('/images/')
            if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name) or not (IMAGES / name).is_file():
                return self.reply({'error': 'Image not found'}, 404)
            image = (IMAGES / name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', str(len(image)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(image)
            return
        path = self.path.split('?')[0]
        if path == '/':
            path = '/index.html'
        target = (ROOT / 'static' / path.lstrip('/')).resolve()
        if not target.is_relative_to((ROOT / 'static').resolve()) or not target.is_file():
            return self.reply({'error': 'Not found'}, 404)
        import mimetypes
        body = target.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self.safe_host() or self.headers.get('X-Local-Token') != TOKEN:
            return self.reply({'error': 'Refresh the page to reconnect.'}, 403)
        origin = self.headers.get('Origin')
        if origin and origin not in [f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}']:
            return self.reply({'error': 'Invalid origin'}, 403)
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > (8000000 if self.path == "/api/images" else 200000) or length < 0:
                raise ValueError('Request too large.')
            body = json.loads(self.rfile.read(length) or b'{}')
            if self.path == '/api/images':
                raw = body.get('data', '')
                if not raw.startswith('data:image/jpeg;base64,'):
                    raise ValueError('Attach a JPEG, PNG or WebP image using the image button.')
                content = base64.b64decode(raw.split(',', 1)[1], validate=True)
                if len(content) > 5000000 or not content.startswith(b'\xff\xd8\xff'):
                    raise ValueError('Invalid image or image exceeds 5 MB.')
                name = secrets.token_hex(16) + '.jpg'
                (IMAGES / name).write_bytes(content)
                return self.reply({'id': name})
            if self.path == '/api/folders':
                p = Path(body.get('path', '')).expanduser().resolve()
                if not valid_model(p):
                    raise ValueError('Choose a model folder containing config.json and OpenVINO XML files.')
                f = DATA / 'folders.json'
                items = json.loads(f.read_text()) if f.exists() else []
                if str(p) not in items:
                    items.append(str(p))
                f.write_text(json.dumps(items, indent=2))
                return self.reply({'models': models()})
            if not LOCK.acquire(blocking=False):
                return self.reply({'error': 'A model is loading or generating. Stop or wait for it first.'}, 409)
            try:
                if self.path == '/api/load':
                    load(body['model'], body.get('device', 'GPU'))
                    return self.reply(STATE)
                if self.path == '/api/unload':
                    unload()
                    return self.reply(STATE)
                if self.path == '/api/chat':
                    return self.chat(body)
                return self.reply({'error': 'Not found'}, 404)
            finally:
                LOCK.release()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            if STATE['phase'] == 'loading':
                unload()
                STATE.update(phase='error', error=str(e))
            self.reply({'error': str(e)}, 400)

    def chat(self, body):
        if STATE['phase'] != 'ready' or not PROCESS or PROCESS.poll() is not None:
            raise ValueError('Load a model before sending a message.')
        messages = body.get('messages', [])
        if not isinstance(messages, list) or not messages:
            raise ValueError('A message is required.')
        text_length = 0
        image_count = 0
        normalized = []
        for m in messages:
            if m.get('role') not in ['system', 'user', 'assistant']:
                raise ValueError('Invalid message role.')
            content = m.get('content')
            if isinstance(content, str):
                text_length += len(content)
                normalized.append(m)
                continue
            if not isinstance(content, list) or m['role'] != 'user':
                raise ValueError('Invalid message content.')
            parts = []
            for part in content:
                if part.get('type') == 'text' and isinstance(part.get('text'), str):
                    text_length += len(part['text'])
                    parts.append(part)
                elif part.get('type') == 'image_ref':
                    name = part.get('id', '')
                    if not re.fullmatch(r'[a-f0-9]{32}\.jpg', name) or not (IMAGES / name).is_file():
                        raise ValueError('A saved image is missing. Attach it again.')
                    image_count += 1
                    if image_count > 8:
                        raise ValueError('Up to eight images can be included in a conversation. Start a new chat.')
                    encoded = base64.b64encode((IMAGES / name).read_bytes()).decode()
                    parts.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,'+encoded}})
                else:
                    raise ValueError('Unsupported content type.')
            normalized.append({'role': m['role'], 'content': parts})
        if image_count:
            model = next((m for m in models() if m['id'] == STATE['model']), {})
            if not model.get('vision'):
                raise ValueError('The loaded model is text-only. Load a vision model such as Qwen3.5 4B.')
        messages = normalized
        if text_length > 24000:
            raise ValueError('This conversation is long. Compact context or start a new chat.')
        def number(key, default, low, high):
            value = float(body.get(key, default))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{key} must be between {low} and {high}.')
            return value
        limit_value = number('max_tokens', 1024, 1, 32768)
        if not limit_value.is_integer():
            raise ValueError('max_tokens must be a whole number.')
        limit = int(limit_value)
        temperature = number('temperature', .4, 0, 2)
        top_p = number('top_p', 1, .01, 1)
        repetition_penalty = number('repetition_penalty', 1, 1, 2)
        payload = {'model': 'local', 'messages': messages, 'max_tokens': limit, 'temperature': temperature, 'top_p': top_p, 'repetition_penalty': repetition_penalty,
            'stream': True, 'stream_options': {'include_usage': True},
            'chat_template_kwargs': {'enable_thinking': bool(body.get('thinking', False))}}
        req = urllib.request.Request(f'http://127.0.0.1:{BACKEND_PORT}/v3/chat/completions', json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        try:
            response = OPENER.open(req, timeout=180)
        except urllib.error.HTTPError as e:
            raise ValueError(e.read().decode()[:1500]) from e
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        start = time.perf_counter()
        first = last = None
        usage = None
        def event(data):
            self.wfile.write(('data: ' + json.dumps(data) + '\n\n').encode())
            self.wfile.flush()
        try:
            with response:
                for line in response:
                    if not line.startswith(b'data: '):
                        continue
                    raw = line[6:].strip()
                    if raw == b'[DONE]':
                        break
                    data = json.loads(raw)
                    if data.get('usage'):
                        usage = data['usage']
                    for choice in data.get('choices', []):
                        delta = choice.get('delta', {})
                        if delta.get('content') or delta.get('reasoning_content') or delta.get('reasoning'):
                            last = time.perf_counter()
                            first = first or last
                        event({'delta': delta, 'finish_reason': choice.get('finish_reason')})
                tokens = usage.get('completion_tokens') if usage else None
                event({'done': True, 'usage': usage, 'seconds': time.perf_counter()-start,
                    'ttft': first-start if first else None,
                    'tps': (tokens-1)/(last-first) if tokens and tokens > 1 and last and last > first else None})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            event({'error': str(e)})


atexit.register(unload)
if __name__ == '__main__':
    http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
