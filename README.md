# Deck Studio

A single-file, self-contained web app for building 16:9 HTML slide decks in Rahul's house styles,
hosted on GitHub Pages so it's usable from any machine. Decks save straight to your Mac
(`~/Documents/speaking`), and can optionally be published as shareable links with a timed expiry.

- **Studio:** https://rahulmatthan.github.io/deck-studio/
- **Published decks:** `https://rahulmatthan.github.io/deck-studio/d/<id>.<expiry>.html`

## One-time setup

### 1. Create the repo and push
```bash
cd ~/Coding/deck-studio
git init -b main
git add -A
git commit -m "Deck Studio + publish"

# with the GitHub CLI:
gh repo create deck-studio --public --source=. --remote=origin --push

# …or, if you made the empty repo on github.com first:
# git remote add origin https://github.com/rahulmatthan/deck-studio.git
# git push -u origin main
```

### 2. Turn on GitHub Pages
Repo → **Settings → Pages** → *Build and deployment* → Source: **Deploy from a branch** →
Branch: **main**, folder **/(root)** → Save. Give it a minute; Studio appears at
`https://rahulmatthan.github.io/deck-studio/`.

### 3. Make a fine-grained token (only needed to *publish* links)
github.com → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate**:
- **Resource owner:** rahulmatthan
- **Repository access:** *Only select repositories* → **deck-studio**
- **Permissions → Repository → Contents:** **Read and write**
- Generate, copy the `github_pat_…` string.

In Studio: **Share → paste the token → Connect**. It's stored only in that browser
(localStorage). Use *Forget token* to remove it; revoke it anytime on GitHub.

## Using it

- **Build on the go:** open the Studio URL anywhere, *New* or *Open* a deck, edit.
- **Save locally:** *Save both* writes `<name>.html` (editable master) + `<name> (shareable).html`
  (present-only) into a folder you pick once (`~/Documents/speaking`). Chrome/Edge only.
- **Publish a link:** *Share → pick an expiry → Publish*. Commits a present-only copy to `d/`,
  gives you a public link to send the technician.
- **Revoke:** *Share → Published links → Revoke* deletes it immediately.
- **Present:** press **F** for fullscreen — the screen stays awake (Wake Lock) until you exit.

## How expiry works

Each published file is named `<id>.<expiryEpochMs>.html` (or `<id>.x.html` for no expiry).
- A soft in-page gate shows "link expired" the moment the deadline passes.
- The hourly **`cleanup` GitHub Action** actually deletes expired files from the repo, so the
  link truly 404s. (Run it manually anytime from the Actions tab.)

**Note on "single-use":** a strict open-once link can't be enforced on static hosting (nothing runs
when someone views a static file). Timed-expiry + Revoke covers keeping viewers out after a talk.
True single-use would need a tiny serverless function — not included here.

## Notes
- `.nojekyll` keeps GitHub Pages from processing files through Jekyll.
- Everything is static; no build step.
