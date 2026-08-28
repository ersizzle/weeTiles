# weeTiles — project context for Claude Code

A single-file Maya tool (`weeTiles.py`, Python 3, PySide) that browses a tile-model
library and imports/scatters the models. Built for the Serapool tile catalogue.
Personal tool by the user (ersizzle). User-facing docs: `README.md`.

**Sibling project, deliberately unrelated:** `weeScript` (`../WeeScript`) is the user's
big shelf-panel tool. weeTiles was split out of it on purpose — do **not** add weeTiles
code to weeScript or make either import the other.

## How it loads / runs

- Loaded the same way as weeScript, by exec'ing the raw file into `__main__`:
  ```python
  import urllib.request, __main__
  exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py').read().decode('utf-8'), __main__.__dict__)
  ```
- Bottom of the file calls `weeTiles()` (opens the browser) and registers **Alt+2**,
  which re-pulls the file from `WT_SELF_URL` and reopens it.
- Entry point `weeTiles()`; `WtBrowser` is the window; the open window is kept in `_wtWin`.

## Conventions (IMPORTANT — keep these)

- **Indentation is TABS** (same as weeScript). Never introduce spaces.
- **Every global is prefixed `wt` / `_wt` / `WT_` / `Wt`.** Both tools exec into Maya's
  `__main__`, so an unprefixed name (`group`, `scale`, `rotate`…) would clobber weeScript.
- **No `maya.cmds` off the main thread.** `WtThumbJob` runs in a `QThreadPool`; it may only
  touch the network and disk. That is why `_wtFetch(rel, rev, base=..., cache=...)` takes
  `base`/`cache` explicitly — resolving them calls `mc.optionVar`/`mc.internalVar`.
  Same rule for `QPixmap`: built on the main thread in `WtBrowser._thumb` only.
- **Qt compat:** PySide6 (Maya 2025+) / PySide2 (2022–2024) via the shim at the top.
  Avoid `QAction` (moved modules), `QRegExp` (gone in Qt6), and `exec_` vs `exec`
  (`WtListView.startDrag` handles both). Classic enum spellings (`QtCore.Qt.UserRole`)
  work in both.
- After ANY edit: `python3 -c "import ast; ast.parse(open('weeTiles.py').read())"` and
  re-run the logic tests (below).

## Architecture

Five regions, in file order, marked with banner comments:

1. **settings** — `_wtSrc/_wtSetSrc` (optionVar `weeTilesSource`), `_wtGetSettings/_wtSaveSettings`
   (optionVar `weeTilesSettings`, JSON), `_wtCacheDir/_wtCacheSize`.
2. **library** — `_wtManifestUrl/_wtBase` (everything normalised to forward slashes, so
   `\\srv\3d` → `//srv/3d`), `_wtRead`, `_wtFetch` (md5-of-base cache folder + `.rev`
   sidecar for cache busting), `_wtLoad` (manifest, fetched with a `?t=` CDN cache-buster),
   `_wtSize` → **(long, short)**, `_wtHaystack`.
3. **pattern maths** — `_wtLayout(pattern, tile_l, tile_w, area_w, area_l, grout, rotate)`
   returns `[(x, z, ry), …]` tile **centres**. Deliberately **pure — no Maya** — so it is
   unit-testable. Patterns: `grid`, `bond`, `herringbone`.
   - Herringbone uses the L-pair lattice `t1 = (2·Lu, 0)`, `t2 = (Wu, Wu)` with the two
     tiles at `(Lu/2, Wu/2, ry 0)` and `(Lu + Wu/2, (2Wu − Lu)/2, ry 90)`. **This only
     tiles the plane when long = 2 × short** (33×66). `wtScatter` warns and falls back to
     `bond` otherwise — verified numerically, don't "fix" it to accept other ratios.
   - Grout is added to the lattice step (`lu = tile_l + grout`), so with grout the
     herringbone joints vary by up to `grout`; that is accepted, not a bug.
4. **Maya side** — `_wtImportOne` (diffs `mc.ls(assemblies=True)` around `mc.file`, keeps
   roots containing a mesh, renames to `<id>_geo`, drops pivot to bottom centre),
   `wtImport`, `wtReplace`, `wtScatter`, `wtImportScatter`, `_wtTrim` (instances→objects,
   combine a duplicate, live boolean intersect with a box — ported from weeScript's
   `_trimTileScatter`, which is proven in the user's pipeline).
5. **UI** — `WtThumbJob/WtThumbSignals`, `WtFilterProxy`, `WtListView` (custom `startDrag`
   carrying `WT_MIME` = the tile ids), `WtBrowser`, plus `WtDropFilter`/`_wtHookViewports`
   for dropping onto model panels and `_wtGroundPoint` (screen → Y=0 plane via
   `M3dView.viewToWorld`, note the Qt/Maya Y flip).

## Library format

The tile models are **not** in this repo — they live on a web host or a network folder,
described by a `library.json` manifest. `make_tile_library.py` (plain Python 3, run outside
Maya) generates that manifest from a folder and preserves hand-edited fields on re-runs.
Format reference and hosting notes are in `README.md`.

`WT_LIB_DEFAULT` is a placeholder address — the real one is whatever the user types into
the browser's Library field (it persists in the optionVar).

## Testing

The pure regions can be tested without Maya by exec'ing the slice between `WT_VERSION =`
and `#  Maya side:` with a stubbed `mc` object (`optionVar`/`internalVar`/`warning`).
The existing suite covers URL/UNC normalisation, size parsing, all three layouts
(sampling interior points to assert **exactly one** tile covers each — this is what
validates the herringbone lattice), manifest load over a real local HTTP server,
download/cache/`rev` busting, spaces in filenames, and settings round-trip.

## Verified in Maya

Nothing yet — the tool was written and logic-tested outside Maya. Still unconfirmed:
the Qt layout, `mc.file` import of the real FBX files, the viewport drop hook, and
`_wtTrim`. Ask the user before assuming any of these work.

## Git

Repo: `weeTiles` (separate from `weeScript`). Push with the user's local git auth:
```
git add -A && git commit -m "..." && git push
```
