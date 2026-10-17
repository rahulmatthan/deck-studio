#!/usr/bin/env python3
"""deck — assemble and maintain HTML decks built on the shared engine.

  deck new <dir> --theme <slug> [--title T]   start a deck folder (deck.html, notes.json, refs/, images/)
  deck refresh <dir|deck.html>                 re-inline the current engine + theme into a deck
  deck theme <dir|deck.html> <slug>            switch a deck's theme
  deck themes                                  list themes
  deck gallery                                 rebuild gallery/ (every theme on the same sample slides)
  deck shots <dir|deck.html> [--out D]         screenshot every slide (fully built) for visual QA
  deck studio [<dir>]                          start the review studio (127.0.0.1:4646) and open it
  deck notes <dir> [--all]                     print the notes waiting for Claude, with slide numbers
  deck resolve <dir> <note-id> "<reply>" [--question]   mark a note applied (or ask a question back)
  deck prompt <dir> <slide-id> "<prompt>"      attach an image prompt (Midjourney) to a slide
  deck export <dir> [--formats html,pdf,pptx] [--dest D]   save the final version (default ~/Documents/speaking)
  deck publish <dir> [--expiry 72]             publish a share link on exmachina.in/deck-studio

A deck is one self-contained deck.html. The engine and theme sit inside it between markers, so
`refresh` can upgrade old decks without touching their slides.
"""
import argparse, glob, html, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, 'engine')
THEMES = os.path.join(ENGINE, 'themes')


# ---------- engine + themes ----------

def themes():
    order = [l.strip() for l in open(os.path.join(THEMES, 'ORDER')) if l.strip()]
    out = []
    for slug in order:
        src = open(os.path.join(THEMES, slug + '.css')).read()
        meta = dict(re.findall(r'@(\w+)\s+(.+)', src.split('*/', 1)[0]))
        out.append({'slug': slug, 'name': meta.get('name', slug), 'fonts': meta.get('fonts', ''),
                    'about': meta.get('about', ''), 'css': src.split('*/', 1)[1].strip()})
    return out


def theme(slug):
    for t in themes():
        if t['slug'] == slug:
            return t
    sys.exit(f'no theme "{slug}" — try: deck themes')


def engine_css():
    return open(os.path.join(ENGINE, 'engine.css')).read()


def engine_js():
    logo = open(os.path.join(ENGINE, 'logo.b64')).read().strip()
    return open(os.path.join(ENGINE, 'engine.js')).read().replace('__LOGO__', logo)


def fonts_block(t):
    return ('<!--deck:fonts-->\n<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link href="{t["fonts"]}" rel="stylesheet">\n<!--/deck:fonts-->')


def assemble(slides_html, slug, title='Presentation', body_class='', trans='fade', local_css=''):
    t = theme(slug)
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{html.escape(title)}</title>
{fonts_block(t)}
<style id="deck-engine">
{engine_css()}
</style>
<style id="deck-theme" data-theme="{slug}">
{t["css"]}
</style>
<style id="deck-local">
{local_css}
</style>
</head>
<body class="{body_class}" data-trans="{trans}">
<div id="stage">
<!-- ===== SLIDES ===== -->
{slides_html.strip()}
<!-- ===== /SLIDES ===== -->
</div>
<script id="deck-js">
{engine_js()}
</script>
</body>
</html>
'''


def deck_path(p):
    return os.path.join(p, 'deck.html') if os.path.isdir(p) else p


def current_theme(src):
    m = re.search(r'<style id="deck-theme" data-theme="([\w-]+)">', src)
    return m.group(1) if m else 'keynote'


def refresh(path, slug=None):
    path = deck_path(path)
    src = open(path).read()
    slug = slug or current_theme(src)
    t = theme(slug)
    sub = lambda pat, rep, s: re.sub(pat, lambda m: rep, s, count=1, flags=re.S)
    src = sub(r'<!--deck:fonts-->.*?<!--/deck:fonts-->', fonts_block(t), src)
    src = sub(r'<style id="deck-engine">.*?</style>', f'<style id="deck-engine">\n{engine_css()}\n</style>', src)
    src = sub(r'<style id="deck-theme"[^>]*>.*?</style>',
              f'<style id="deck-theme" data-theme="{slug}">\n{t["css"]}\n</style>', src)
    src = sub(r'<script id="deck-js">.*?</script>', f'<script id="deck-js">\n{engine_js()}\n</script>', src)
    open(path, 'w').write(src)
    return path


# ---------- new deck ----------

def new(d, slug, title):
    os.makedirs(os.path.join(d, 'refs'), exist_ok=True)
    os.makedirs(os.path.join(d, 'images'), exist_ok=True)
    p = os.path.join(d, 'deck.html')
    if os.path.exists(p):
        sys.exit(f'{p} already exists')
    slides = (f'<section class="slide" data-id="s1">\n  <div class="cover-t">{html.escape(title)}</div>\n'
              '  <div class="rule"></div>\n</section>')
    open(p, 'w').write(assemble(slides, slug, title))
    notes = os.path.join(d, 'notes.json')
    if not os.path.exists(notes):
        json.dump({'deck': [], 'slides': {}}, open(notes, 'w'), indent=2)
    print(p)


# ---------- screenshots ----------

def chrome_bin():
    for c in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
              shutil.which('chromium') or '', shutil.which('chromium-browser') or '',
              shutil.which('google-chrome') or '', shutil.which('google-chrome-stable') or '']:
        if c and os.path.exists(c):
            return c
    sys.exit('no Chrome/Chromium found')


def count_slides(path):
    return len(re.findall(r'<section class="slide[ "]', open(path).read()))


def shot(url, out, w=1280, h=720, budget=3500):
    subprocess.run([chrome_bin(), '--headless=new', '--disable-gpu', '--hide-scrollbars',
                    f'--window-size={w},{h}', f'--virtual-time-budget={budget}',
                    f'--screenshot={out}', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def shots(path, out=None):
    path = os.path.abspath(deck_path(path))
    out = out or tempfile.mkdtemp(prefix='deckshots-')
    os.makedirs(out, exist_ok=True)
    n = count_slides(path)
    for k in range(1, n + 1):
        shot(f'file://{path}#{k},bare', os.path.join(out, f'{k:02d}.png'))
    print(out)
    return out


# ---------- gallery ----------

SAMPLE = '''
<section class="slide" data-id="g1">
  <div class="eyebrow">Trilegal Knowledge Series</div>
  <div class="cover-t">Data is <em>infrastructure.</em></div>
  <div class="cover-sub">Rahul Matthan</div>
  <div class="rule"></div>
</section>
<section class="slide center" data-id="g2">
  <div class="word">Consent<em>.</em></div>
</section>
<section class="slide" data-id="g3">
  <div class="eyebrow">The argument</div>
  <div class="idea">India built its digital rails <em>in public</em>, and let the market run on them.</div>
</section>
<section class="slide" data-id="g4">
  <div class="vs">
    <div class="side a"><div class="lbl">Then</div><div class="big">Ownership</div><p>Data as property to be hoarded.</p></div>
    <div class="sep"></div>
    <div class="side b"><div class="lbl">Now</div><div class="big">Stewardship</div><p>Data as a duty owed to the person.</p></div>
  </div>
</section>
<section class="slide" data-id="g5">
  <div class="stat">1.4 bn</div>
  <div class="stat-sub">digital identities, issued in under fifteen years.</div>
</section>
<section class="slide center" data-id="g6">
  <div class="swap"><span class="old">Privacy</span> <span class="new">Agency</span></div>
  <div class="note">The question is no longer who sees the data, but who decides.</div>
</section>
'''


def gallery():
    out = os.path.join(ROOT, 'gallery')
    os.makedirs(out, exist_ok=True)
    ts = themes()
    for t in ts:
        open(os.path.join(out, t['slug'] + '.html'), 'w').write(
            assemble(SAMPLE, t['slug'], f'{t["name"]} — sample', body_class='show-logo'))
    n = SAMPLE.count('<section')
    rows = []
    for k, t in enumerate(ts, 1):
        frames = ''.join(f'<div class="f"><iframe loading="lazy" src="{t["slug"]}.html#{s},bare"></iframe></div>'
                         for s in range(1, n + 1))
        font = re.findall(r'family=([^:&]+)', t['fonts'])
        rows.append(f'''<section class="t" id="{t["slug"]}">
  <header><span class="n">{k:02d}</span><h2>{t["name"]}</h2>
  <span class="fonts">{" + ".join(f.replace("+", " ") for f in font)}</span>
  <a href="{t["slug"]}.html" target="_blank">Present ↗</a></header>
  <p>{t["about"]}</p>
  <div class="grid">{frames}</div>
</section>''')
    page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deck themes</title>
<style>
  :root{{--bg:#F4F5F7;--fg:#182B49;--mut:#5b6573;--line:#dde1e6}}
  @media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#111418;--fg:#e8ecf1;--mut:#9aa4b2;--line:#2a3038}}}}
  *{{box-sizing:border-box;margin:0}}
  body{{background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,system-ui,sans-serif;padding:40px 16px 80px}}
  .wrap{{max-width:1500px;margin:0 auto}}
  h1{{font-size:30px;letter-spacing:-.01em}} .lede{{color:var(--mut);margin:6px 0 34px;max-width:820px}}
  .t{{padding:28px 0 36px;border-top:1px solid var(--line)}}
  header{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}}
  .n{{color:var(--mut);font-variant-numeric:tabular-nums}} h2{{font-size:22px}}
  .fonts{{color:var(--mut);font-size:14px}} header a{{margin-left:auto;color:var(--fg);font-size:14px}}
  .t p{{color:var(--mut);margin:4px 0 16px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:14px}}
  .f{{aspect-ratio:16/9;border-radius:6px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.12),0 8px 24px rgba(0,0,0,.08)}}
  iframe{{width:100%;height:100%;border:0;display:block;pointer-events:none}}
  nav{{display:flex;flex-wrap:wrap;gap:8px 16px;margin-bottom:26px;font-size:14px}} nav a{{color:var(--fg)}}
</style></head><body><div class="wrap">
<h1>Deck themes</h1>
<p class="lede">Twelve themes on the same six sample slides: cover, one word, statement, comparison, number, substitution.
Every one keeps the Trilegal ribbon and the legibility floor (nothing below 24px on the canvas, about 18pt).
Pick the ones to keep, and tell me what to change in any of them.</p>
<nav>{" ".join(f'<a href="#{t["slug"]}">{t["name"]}</a>' for t in ts)}</nav>
{"".join(rows)}
</div></body></html>'''
    open(os.path.join(out, 'index.html'), 'w').write(page)
    print(os.path.join(out, 'index.html'))


# ---------- notes (the studio writes them, Claude applies them) ----------

DECKS = os.path.expanduser(os.environ.get('DECKS', '~/coding/decks'))
PORT = int(os.environ.get('DECK_PORT', 4646))


def notes_path(d):
    return os.path.join(os.path.dirname(deck_path(d)), 'notes.json')


def load_notes(d):
    try:
        n = json.load(open(notes_path(d)))
    except (FileNotFoundError, ValueError):
        n = {}
    for k, v in (('deck', []), ('slides', {}), ('prompts', {})):
        n.setdefault(k, v)
    return n


def save_notes(d, n):
    p = notes_path(d)
    json.dump(n, open(p + '.tmp', 'w'), indent=2, ensure_ascii=False)
    os.replace(p + '.tmp', p)


def slide_ids(d):
    return re.findall(r'<section\b[^>]*\bdata-id="([^"]+)"', open(deck_path(d)).read())


def notes(d, everything=False):
    n, ids = load_notes(d), slide_ids(d)
    want = lambda x: everything or x.get('status') == 'open'
    show = lambda x: (f'  [{x["id"]}] ({x["status"]}) ' + x['text'].replace('\n', '\n      ')
                      + ''.join(f'\n      ref: {r}' for r in x.get('refs', []))
                      + (f'\n      reply: {x["reply"]}' if everything and x.get('reply') else ''))
    out = []
    dk = [x for x in n['deck'] if want(x)]
    if dk:
        out.append('WHOLE DECK\n' + '\n'.join(map(show, dk)))
    for sid, lst in sorted(n['slides'].items(), key=lambda kv: ids.index(kv[0]) if kv[0] in ids else 999):
        lst = [x for x in lst if want(x)]
        if lst:
            where = f'slide {ids.index(sid) + 1}' if sid in ids else 'slide (deleted)'
            out.append(f'{where.upper()}  data-id="{sid}"\n' + '\n'.join(map(show, lst)))
    print('\n\n'.join(out) or 'No open notes.')


def resolve(d, nid, reply, question=False):
    n = load_notes(d)
    for x in n['deck'] + [y for v in n['slides'].values() for y in v]:
        if x['id'] == nid:
            x.update(status='question' if question else 'applied', reply=reply)
            save_notes(d, n)
            return
    sys.exit(f'no note {nid}')


def prompt(d, sid, text):
    n = load_notes(d)
    n['prompts'][sid] = {'prompt': text, 'status': 'wanted'}
    save_notes(d, n)


def studio(d=None):
    import urllib.request
    url = f'http://127.0.0.1:{PORT}/'
    try:
        urllib.request.urlopen(url + 'api/themes', timeout=1)
    except OSError:
        log = os.path.join(tempfile.gettempdir(), 'deck-studio.log')
        subprocess.Popen([sys.executable, os.path.join(ROOT, 'studio', 'serve.py'), '--port', str(PORT)],
                         stdout=open(log, 'a'), stderr=subprocess.STDOUT, start_new_session=True)
        import time
        for _ in range(30):
            time.sleep(.2)
            try:
                urllib.request.urlopen(url + 'api/themes', timeout=1); break
            except OSError:
                pass
    if d:
        rel = os.path.relpath(os.path.abspath(os.path.dirname(deck_path(d))), os.path.realpath(DECKS))
        url += '#deck=' + rel.replace(os.sep, '~')
    opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(url)


def exporter():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import export
    return export


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    a = sp.add_parser('new'); a.add_argument('dir'); a.add_argument('--theme', default='keynote'); a.add_argument('--title', default='Untitled')
    a = sp.add_parser('refresh'); a.add_argument('path')
    a = sp.add_parser('theme'); a.add_argument('path'); a.add_argument('slug')
    sp.add_parser('themes'); sp.add_parser('gallery')
    a = sp.add_parser('shots'); a.add_argument('path'); a.add_argument('--out')
    a = sp.add_parser('studio'); a.add_argument('path', nargs='?')
    a = sp.add_parser('notes'); a.add_argument('path'); a.add_argument('--all', action='store_true')
    a = sp.add_parser('resolve'); a.add_argument('path'); a.add_argument('id'); a.add_argument('reply'); a.add_argument('--question', action='store_true')
    a = sp.add_parser('prompt'); a.add_argument('path'); a.add_argument('slide'); a.add_argument('text')
    a = sp.add_parser('export'); a.add_argument('path'); a.add_argument('--formats', default='html,pdf,pptx'); a.add_argument('--dest')
    a = sp.add_parser('publish'); a.add_argument('path'); a.add_argument('--expiry', default='72')
    x = ap.parse_args()
    if x.cmd == 'new': new(x.dir, x.theme, x.title)
    elif x.cmd == 'refresh': print(refresh(x.path))
    elif x.cmd == 'theme': print(refresh(x.path, x.slug))
    elif x.cmd == 'themes':
        for t in themes(): print(f'{t["slug"]:12} {t["name"]:16} {t["about"]}')
    elif x.cmd == 'gallery': gallery()
    elif x.cmd == 'shots': shots(x.path, x.out)
    elif x.cmd == 'studio': studio(x.path)
    elif x.cmd == 'notes': notes(x.path, x.all)
    elif x.cmd == 'resolve': resolve(x.path, x.id, x.reply, x.question)
    elif x.cmd == 'prompt': prompt(x.path, x.slide, x.text)
    elif x.cmd == 'export':
        for p in exporter().export(os.path.dirname(os.path.abspath(deck_path(x.path))), x.formats.split(','), x.dest): print(p)
    elif x.cmd == 'publish': print(exporter().publish(os.path.dirname(os.path.abspath(deck_path(x.path))), x.expiry))


if __name__ == '__main__':
    main()
