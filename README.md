# Deck Studio

The engine, themes and review studio behind Rahul's presentations. Claude builds the decks
(the `/slides` skill); Rahul reviews them here, leaving notes beside each slide, and Claude
applies them. Decks themselves live in the private [decks](https://github.com/rahulmatthan/decks)
repo (`~/coding/decks`).

```
engine/engine.css, engine.js   the shared deck engine (inlined into every deck)
engine/themes/*.css, ORDER     twelve themes, all with the Trilegal ribbon
tools/deck.py                  the `deck` CLI
tools/export.py                final versions (HTML, PDF, .pptx) and share links
studio/serve.py, index.html    the local review studio (http://127.0.0.1:4646)
gallery/                       every theme on the same sample slides (`deck gallery`)
d/                             published share links (served by GitHub Pages)
index.html                     the old in-browser deck builder (still live at exmachina.in/deck-studio)
```

## The `deck` command

`~/.local/bin/deck` runs `tools/deck.py` (from `~/dotfiles/local-bin/deck`).

```
deck new <dir> --theme <slug> --title "…"   start a deck folder
deck studio [<dir>]                         open the review studio
deck notes <dir>                            the notes waiting for Claude
deck resolve <dir> <id> "<reply>" [--question]
deck prompt <dir> <slide-id> "<prompt>"     an image prompt for Midjourney, shown in the studio
deck theme <dir> <slug> · deck refresh <dir> · deck themes · deck gallery · deck shots <dir>
deck export <dir> [--formats html,pdf,pptx] save to ~/Documents/speaking
deck publish <dir> [--expiry 72]            share link at exmachina.in/deck-studio/d/…
```

## A deck

One self-contained `deck.html`. The fonts link, engine CSS, theme CSS and engine JS sit inside it
between markers (`<!--deck:fonts-->`, `style#deck-engine`, `style#deck-theme`, `script#deck-js`),
so `deck refresh` upgrades an old deck to the current engine without touching its slides.
Deck-specific CSS goes in `style#deck-local`. Every slide carries a stable `data-id`; notes in
`notes.json` are keyed on it.

Keys when presenting: → / space next build or slide, ← back, F fullscreen (keeps the screen
awake), H shows the counter. `#N` opens slide N fully built, `#N,start` unbuilt.

## The studio

`deck studio` starts a small Python server (standard library only, bound to 127.0.0.1) and opens
it. Left: the slides. Centre: the slide, with arrows to step through builds, the slide's
transition, and **Edit slide** to change words directly or set what appears on a click. Right:
notes for this slide or for the whole deck, with reference images (attach, paste or drop).
Claude's replies and questions appear on the notes; the page reloads when Claude changes the
deck. Drop an image on the slide to have Claude place it. **Save final** writes HTML, PDF and
.pptx to `~/Documents/speaking`; **Share link** publishes an expiring copy.

## Share links

Published files are `d/<id>.<expiryEpochMs|x>.html`, committed with `gh`. A soft in-page gate
shows "link expired" after the deadline, and the hourly `cleanup` GitHub Action deletes expired
files. The repo is public: anything published here can be read on GitHub until it expires.

## On the other machine

```
gh repo clone rahulmatthan/deck-studio ~/coding/deck-studio
gh repo clone rahulmatthan/decks ~/coding/decks
ln -s ~/coding/dotfiles/local-bin/deck ~/.local/bin/deck
```
Exports need Chrome or Chromium, and `uv` for the .pptx step.
