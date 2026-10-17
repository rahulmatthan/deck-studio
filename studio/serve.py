#!/usr/bin/env python3
"""Deck Studio — the local review server.

  python3 studio/serve.py [--port 4646] [--decks ~/coding/decks]   (or: deck studio)

Serves the studio page, every deck under the decks folder, and a small JSON API the studio
uses to read and write each deck's notes.json, save direct edits, switch themes, take
uploads and run exports. Claude edits deck.html and notes.json on disk; the studio polls
/stamp and reloads when either changes. Binds to 127.0.0.1 only.
"""
import argparse, html, json, mimetypes, os, re, subprocess, sys, threading, time, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
import deck  # noqa: E402

DECKS = os.path.expanduser(os.environ.get('DECKS', '~/coding/decks'))
LOCK = threading.Lock()
SECTION = re.compile(r'<section\b([^>]*)>(.*?)</section>', re.S)


# ---------- decks on disk ----------

def key_of(rel):        # "private/foo" travels in URLs as "private~foo"
    return rel.replace(os.sep, '~')


def dir_of(key):
    rel = key.replace('~', os.sep)
    d = os.path.realpath(os.path.join(DECKS, rel))
    if not d.startswith(os.path.realpath(DECKS) + os.sep) or not os.path.isfile(os.path.join(d, 'deck.html')):
        raise FileNotFoundError(key)
    return d


def list_decks():
    out = []
    for pattern in ('*', os.path.join('private', '*')):
        for p in sorted(glob_dirs(pattern)):
            rel = os.path.relpath(p, DECKS)
            src = open(os.path.join(p, 'deck.html')).read()
            n = load_notes(p)
            out.append({'key': key_of(rel), 'name': rel, 'title': title_of(src), 'private': rel.startswith('private'),
                        'theme': deck.current_theme(src), 'slides': len(SECTION.findall(src)),
                        'open': open_count(n), 'mtime': os.path.getmtime(os.path.join(p, 'deck.html'))})
    return sorted(out, key=lambda d: -d['mtime'])


def glob_dirs(pattern):
    import glob
    return [os.path.dirname(f) for f in glob.glob(os.path.join(DECKS, pattern, 'deck.html'))]


def title_of(src):
    m = re.search(r'<title>(.*?)</title>', src, re.S)
    return html.unescape(m.group(1).strip()) if m else 'Untitled'


def attr(attrs, name):
    m = re.search(r'\b' + name + r'="([^"]*)"', attrs)
    return m.group(1) if m else ''


def ensure_ids(path):
    """Give every slide a stable data-id (notes are keyed on it). Returns the source."""
    src = open(path).read()
    used = set(re.findall(r'<section\b[^>]*\bdata-id="([^"]+)"', src))
    if all('data-id="' in m.group(1) for m in SECTION.finditer(src)):
        return src
    k = [0]

    def fresh():
        while True:
            k[0] += 1
            if f's{k[0]}' not in used:
                used.add(f's{k[0]}')
                return f's{k[0]}'

    src = SECTION.sub(lambda m: m.group(0) if 'data-id="' in m.group(1)
                      else f'<section{m.group(1)} data-id="{fresh()}">{m.group(2)}</section>', src)
    open(path, 'w').write(src)
    return src


def label_of(inner):
    inner = re.sub(r'<aside class="notes">.*?</aside>|<script\b.*?</script>|<style\b.*?</style>', ' ', inner, flags=re.S)
    inner = re.sub(r'</?(em|b|i|strong|span|a)\b[^>]*>', '', inner)
    t = html.unescape(re.sub(r'<[^>]+>', ' ', inner))
    return re.sub(r'\s+', ' ', t).strip()[:90]


def state(d):
    path = os.path.join(d, 'deck.html')
    with LOCK:
        src = ensure_ids(path)
    body = re.search(r'<body\b([^>]*)>', src).group(1)
    cls = attr(body, 'class').split()
    slides = []
    for m in SECTION.finditer(src):
        a, inner = m.group(1), m.group(2)
        sp = re.search(r'<aside class="notes">(.*?)</aside>', inner, re.S)
        slides.append({'id': attr(a, 'data-id'), 'trans': attr(a, 'data-trans'), 'label': label_of(inner),
                       'speaker': html.unescape(re.sub(r'<[^>]+>', '', sp.group(1))).strip() if sp else ''})
    return {'title': title_of(src), 'theme': deck.current_theme(src), 'trans': attr(body, 'data-trans') or 'fade',
            'logo': 'show-logo' in cls, 'ribbon': 'no-ribbon' not in cls, 'slides': slides,
            'notes': load_notes(d), 'stamp': stamp(d)}


def stamp(d):
    f = lambda n: os.path.getmtime(os.path.join(d, n)) if os.path.exists(os.path.join(d, n)) else 0
    return {'deck': f('deck.html'), 'notes': f('notes.json')}


# ---------- notes.json ----------

def load_notes(d):
    p = os.path.join(d, 'notes.json')
    try:
        n = json.load(open(p))
    except (FileNotFoundError, ValueError):
        n = {}
    n.setdefault('deck', []); n.setdefault('slides', {}); n.setdefault('prompts', {})
    return n


def save_notes(d, n):
    p = os.path.join(d, 'notes.json')
    tmp = p + '.tmp'
    json.dump(n, open(tmp, 'w'), indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def open_count(n):
    return sum(x.get('status') == 'open' for x in n['deck']) + \
        sum(x.get('status') == 'open' for v in n['slides'].values() for x in v)


def notes_op(d, req):
    """op add|update|delete on scope 'deck' or a slide id; prompt ops on notes.prompts."""
    with LOCK:
        n = load_notes(d)
        op, scope = req['op'], req.get('scope', 'deck')
        if op.startswith('prompt'):
            p = n['prompts'].setdefault(scope, {})
            p.update(req.get('fields', {}))
            save_notes(d, n)
            return n
        lst = n['deck'] if scope == 'deck' else n['slides'].setdefault(scope, [])
        if op == 'add':
            note = {'id': 'n' + base36(int(time.time() * 1000)), 'text': req['text'].strip(), 'status': 'open',
                    'reply': '', 'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'refs': req.get('refs', [])}
            lst.append(note)
        else:
            for k, x in enumerate(lst):
                if x['id'] == req['id']:
                    if op == 'delete':
                        lst.pop(k)
                    else:
                        x.update(req.get('fields', {}))
                    break
        if scope != 'deck' and not lst:
            n['slides'].pop(scope, None)
        save_notes(d, n)
        return n


def base36(x):
    s = ''
    while x:
        x, r = divmod(x, 36)
        s = '0123456789abcdefghijklmnopqrstuvwxyz'[r] + s
    return s


# ---------- edits to deck.html ----------

def save_section(d, sid, new_html):
    path = os.path.join(d, 'deck.html')
    if not re.match(r'\s*<section\b', new_html) or f'data-id="{sid}"' not in new_html.split('>', 1)[0]:
        raise ValueError('not a slide section')
    with LOCK:
        src = open(path).read()
        pat = re.compile(r'<section\b[^>]*\bdata-id="' + re.escape(sid) + r'"[^>]*>.*?</section>', re.S)
        if not pat.search(src):
            raise ValueError(f'no slide {sid}')
        src = pat.sub(lambda m: new_html.strip(), src, count=1)
        open(path, 'w').write(src)


def set_body(d, req):
    path = os.path.join(d, 'deck.html')
    with LOCK:
        src = open(path).read()
        m = re.search(r'<body\b([^>]*)>', src)
        a = m.group(1)
        cls = attr(a, 'class').split()
        trans = req.get('trans') or attr(a, 'data-trans') or 'fade'
        for flag, c, on in (('logo', 'show-logo', True), ('ribbon', 'no-ribbon', False)):
            if flag in req:
                want = bool(req[flag]) == on
                if want and c not in cls: cls.append(c)
                if not want and c in cls: cls.remove(c)
        src = src[:m.start()] + f'<body class="{" ".join(cls)}" data-trans="{trans}">' + src[m.end():]
        open(path, 'w').write(src)


def upload(d, kind, name, data):
    if kind not in ('refs', 'images'):
        raise ValueError('kind')
    base, ext = os.path.splitext(os.path.basename(name or 'image.png'))
    base = re.sub(r'[^\w-]+', '-', base).strip('-')[:40] or 'image'
    os.makedirs(os.path.join(d, kind), exist_ok=True)
    rel = f'{kind}/{time.strftime("%m%d-%H%M%S")}-{base}{ext.lower() or ".png"}'
    open(os.path.join(d, rel), 'wb').write(data)
    return rel


def reveal(p):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', p])
    else:
        subprocess.Popen(['xdg-open', os.path.dirname(p)])


# ---------- HTTP ----------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype='application/json'):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in u.path.strip('/').split('/') if p]
        try:
            if not parts:
                return self.send(200, open(os.path.join(HERE, 'index.html'), 'rb').read(), 'text/html; charset=utf-8')
            if parts == ['api', 'decks']:
                return self.send(200, {'decks': list_decks(), 'root': DECKS})
            if parts == ['api', 'themes']:
                return self.send(200, [{k: t[k] for k in ('slug', 'name', 'about')} for t in deck.themes()])
            if parts == ['api', 'published']:
                return self.send(200, exporter().published())
            if len(parts) == 4 and parts[:2] == ['api', 'd']:
                d = dir_of(parts[2])
                if parts[3] == 'state': return self.send(200, state(d))
                if parts[3] == 'stamp': return self.send(200, stamp(d))
            if parts[0] == 'd' and len(parts) >= 3:      # /d/<key>/<file…> — the deck folder
                d = dir_of(parts[1])
                f = os.path.realpath(os.path.join(d, *parts[2:]))
                if f.startswith(d + os.sep) and os.path.isfile(f):
                    ctype = mimetypes.guess_type(f)[0] or 'application/octet-stream'
                    return self.send(200, open(f, 'rb').read(), ctype)
            self.send(404, {'error': 'not found'})
        except FileNotFoundError as e:
            self.send(404, {'error': f'not found: {e}'})
        except Exception as e:
            self.send(500, {'error': str(e)})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        parts = [urllib.parse.unquote(p) for p in u.path.strip('/').split('/') if p]
        try:
            if parts == ['api', 'revoke']:
                exporter().revoke(json.loads(self.body())['name'])
                return self.send(200, {'ok': True})
            if parts == ['api', 'reveal']:
                reveal(json.loads(self.body())['path'])
                return self.send(200, {'ok': True})
            if len(parts) != 4 or parts[:2] != ['api', 'd']:
                return self.send(404, {'error': 'not found'})
            d, what = dir_of(parts[2]), parts[3]
            if what == 'upload':
                return self.send(200, {'path': upload(d, q.get('kind', 'refs'), q.get('name'), self.body())})
            req = json.loads(self.body() or b'{}')
            if what == 'notes':
                return self.send(200, notes_op(d, req))
            if what == 'section':
                save_section(d, req['id'], req['html'])
            elif what == 'body':
                set_body(d, req)
            elif what == 'theme':
                with LOCK:
                    deck.refresh(d, req['slug'])
            elif what == 'refresh':
                with LOCK:
                    deck.refresh(d)
            elif what == 'export':
                return self.send(200, {'paths': exporter().export(d, req.get('formats') or ['html', 'pdf', 'pptx'])})
            elif what == 'publish':
                return self.send(200, {'url': exporter().publish(d, req.get('expiry', '72'))})
            else:
                return self.send(404, {'error': 'not found'})
            self.send(200, state(d))
        except FileNotFoundError as e:
            self.send(404, {'error': f'not found: {e}'})
        except Exception as e:
            self.send(500, {'error': f'{type(e).__name__}: {e}'})


def exporter():
    import export
    return export


def main():
    global DECKS
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=int(os.environ.get('DECK_PORT', 4646)))
    ap.add_argument('--decks', default=DECKS)
    x = ap.parse_args()
    DECKS = os.path.realpath(os.path.expanduser(x.decks))
    os.makedirs(DECKS, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', x.port), H)
    print(f'Deck Studio on http://127.0.0.1:{x.port}  (decks: {DECKS})', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
