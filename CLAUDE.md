# weeTiles — project context for Claude Code

Two independent single-file Maya tools (Python 3) for the Serapool tile catalogue.
Personal tools by the user (ersizzle). User-facing docs: `README.md`.

- **`weeTiles.py`** (PySide) — browses a tile-model library and imports/scatters the
  models. Most of this file describes it.
- **`weeBuild.py`** (native `cmds` UI) — a weeScript-style dockable button panel that
  *builds* tiles procedurally and imports grate/coping models. See the weeBuild
  section at the bottom.

They share no code. Keep it that way: neither imports the other.

**Sibling project, deliberately unrelated:** `weeScript` (`../WeeScript`) is the user's
big shelf-panel tool. weeTiles was split out of it on purpose — do **not** add weeTiles
code to weeScript or make either import the other.

## How it loads / runs

- Loaded the same way as weeScript, by exec'ing the raw file into `__main__`:
  ```python
  import urllib.request, __main__
  exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py').read().decode('utf-8'), __main__.__dict__)
  ```
- Bottom of the file calls `weeTiles()` (opens the browser). **No hotkey** — Alt+2 and
  Alt+3 are taken in the user's Maya. weeBuild owns Shift+Alt+1; if weeTiles ever wants
  one, pick a different free combo and copy `wbHotkey`'s hotkey-set handling.
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

## Testing (weeTiles)

The pure regions can be tested without Maya by exec'ing the slice between `WT_VERSION =`
and `#  Maya side:` with a stubbed `mc` object (`optionVar`/`internalVar`/`warning`).
The existing suite covers URL/UNC normalisation, size parsing, all three layouts
(sampling interior points to assert **exactly one** tile covers each — this is what
validates the herringbone lattice), manifest load over a real local HTTP server,
download/cache/`rev` busting, spaces in filenames, and settings round-trip.

## Verified in Maya

**Confirmed working** (user screenshot, 2026-08-31): the weeBuild panel opens, and the
coping sweep builds correctly — `polyCreateFacet` on the 27-point *concave* profile,
`polyExtrudeFacet`, the `polyCloseBorder` back cap, outward-facing wall normals, and the
ribs. The bullnose and grip undercut read correctly in the viewport.

Still unconfirmed. weeTiles: the Qt layout, `mc.file` import of the real FBX files, the
viewport drop hook, and `_wtTrim`. weeBuild: the tile `polyBevel3` recipe, the coping
**end cap bevel** (added after that screenshot) and the `polyProjection` UV result on
both. Ask the user before assuming any of these work.

##############################################################################

# weeBuild (`weeBuild.py`)

A weeScript-style dockable button panel: **Tiles**, **Copings** (both built
procedurally), then **Grates** / **Coping models** (imported from a folder).
`buildTiles.py` in this folder is the weeScript excerpt it was built from — reference
only, not loaded by anything.

## How it loads / runs

- Same exec-the-raw-file pattern as the others; `WB_SELF_URL` points at
  `.../weeTiles/master/weeBuild.py`.
- Bottom of the file calls `weeBuild()` then `wbHotkey()`, which binds **Shift+Alt+1** to
  open the panel. Alt+1 (weeScript), Alt+2 and Alt+3 are taken in the user's Maya —
  don't bind those. `wbHotkey(key=, alt=, sht=, ctl=)` rebinds it.
- Two things that make hotkey code here non-obvious, both covered by tests:
  - **`Maya_Default` is read-only**, so a hotkey written into it silently does nothing.
    `_wbEditableHotkeySet` copies it to `WB_HOTKEY_SET` (`weeTools`) and switches, but
    only when the current set *is* `Maya_Default` — a set the user already picked is left
    alone.
  - `nameCommand` needs `sourceType='python'` **with raw Python**, or `'mel'` with a
    `python("…")` wrapper. The old removed code mixed the two, which could never have
    fired. Don't reintroduce that.
- The bound command **reopens the panel** when `weeBuild` is already in `__main__`, and
  only fetches `WB_SELF_URL` when it isn't (so it still works after a Maya restart). It
  deliberately does *not* re-download on every press: nothing is pushed to that URL, so
  that would serve a stale file over the copy being worked on.
- `weeBuild()` makes the `workspaceControl` whose `uiScript` is `'wbUI()'`, so **`wbUI`
  must stay a module-level name in `__main__`** and must be re-runnable — Maya calls it
  again whenever it restores the panel. It rebuilds `_wbFields` / `_wbCols` each time.

## Conventions (IMPORTANT — same spirit as weeTiles)

- **Indentation is TABS.**
- **Every global is prefixed `wb` / `_wb` / `WB_`.** Three tools now share Maya's
  `__main__`; only `mc`, `mel` and `os` are (deliberately) common.
- Button commands are **Python callables**, not `eval`'d strings — model paths contain
  spaces and backslashes. They all go through `_wbGuard`, which turns an exception into
  `mc.warning` instead of a traceback.
- **`_wbSafe` exists because Maya node names take no dots.** A decimal point becomes
  `p` (`16.5x66` → `16p5x66`), so half the presets would otherwise make illegal names.
  `fragment=True` skips the leading-digit `_` for tokens that sit inside a longer name.
- After ANY edit: `python3 -c "import ast; ast.parse(open('weeBuild.py').read())"` and
  `python tests/test_build_logic.py`.

## Architecture

Regions in file order, marked with banner comments:

1. **settings** — `_wbGetSettings`/`_wbSaveSettings` (optionVar `weeBuildSettings`,
   JSON), `_wbFolder`/`_wbSetFolder` per model section.
2. **helpers** — `_wbGuard`, `_wbSafe`/`_wbToken`, `_wbUnique` (lowest free `%02d`),
   `_wbBottomPivot`, `_wbWrap` (button labels), `_wbNum` (reads a panel field, falls
   back to the default when the panel is shut).
3. **tiles** — `_wbFaceCenterY` + `_wbBuildTile` are **weeScript's `_buildTile` verbatim**
   (box → chamfer the 4 top edges → delete the bottom face → planar-Y UVs rotated 90°
   → pivot to bottom centre; thickness 0.76, grout 0.15). Do not "improve" the recipe —
   it is proven in the user's pipeline. Geometry still straddles Y=0, as in weeScript;
   only the pivot goes to the bottom. `wbTile` is the scriptable entry point; presets
   live in `WB_TILES` as `(label, short, long)` — **long edge along X, short along Z**.
4. **copings** — `_wbCopingProfile`/`_wbCopingNoses`/`_wbCopingRibs`/`_wbArea`/`_wbCCW`
   are **pure, no Maya**, so they are unit-testable like weeTiles' `_wtLayout`.
   `_wbBuildCoping` sweeps the profile with `polyCreateFacet` →
   `polyExtrudeFacet(localTranslateZ=…)` → `polyCloseBorder`, bevels the end caps,
   merges any ribs with `polyUnite`, then does the UVs. `wbCoping` is the entry point.
   - **`WB_COPING_PROFILES` is a dict of records**, one per profile, each measured off a
     model in `tile_models/copings/`. Keys: `pts` (the (X, Y) loop in cm), `back` (points
     at or behind this X move when the width changes), `noses` (`(side, X)` ends that a
     top projection squashes; side `1` = X ≥, `-1` = X ≤), `ribs`, `minw`, `size`.
   - Three profiles today: **`flat`** (27 pts, 25×2.26, the only one with ribs),
     **`overflow`** (16 pts, 25×1.20, rounded at *both* ends so it has two noses),
     **`channel`** (42 pts, 25×1.60, a 0.75-deep channel with S-curve walls).
   - **Never assume a stored winding.** The three do not agree — which way a loop runs
     depends only on how it was traced out of the source file. `_wbCCW` measures the
     signed area and orients it, because `polyCreateFacet` takes the face normal from the
     winding and a CW loop sweeps its walls inward. Do not go back to `reversed(profile)`.
   - Widening moves only points at `X <= spec['back']`, i.e. the flat back run — every
     nose, lip, channel and undercut keeps the shape it was measured at. That is the whole
     point of rebuilding these rather than importing. `_wbCopingNoses` applies the *same*
     shift to the thresholds, which matters for `overflow`: its left bullnose sits behind
     `back`, so the threshold has to travel with the points.
   - **Arc quality differs by profile.** `flat`'s bullnose is an exact **R0.9651** arc
     (deviation 3.5e-05, the rounding floor of 4-decimal coords) and `overflow`'s two are
     exact **R0.9650** quarter circles — the same tooling radius. **Do not round those
     decimals**; check `[12]` refits them. `channel` is *not* built from clean radii (its
     bullnose fits R0.99 to only 6e-03), so don't generalise that claim to it.
   - `flat`'s top is **not flat** (1.56 at the back edge rising to 2.2191 at the nose) and
     the user confirmed that is correct. Don't level it.
   - Ribs interpenetrate the slab rather than being booleaned — that is what the source
     model does, so it is deliberate.
   - UVs: `polyProjection` planar from **+Y (top)** — deliberate, and it matches how the
     real tiles are laser-painted from above, so **do not replace it with an unroll**.
     Then `_wbRelaxUV` widens the noses and `_wbFitUV` stretches the shell to fill **0-1
     in both directions**. Order matters — relax first, fit last — so the noses keep the
     extra share of U. **Do not** make the fit preserve real width:length proportions: the
     textures are authored to fill the square. **No** 90° rotation (unlike the tiles),
     since the length already runs along Z.
   - A top projection maps each face by its X span, so it compresses whatever is steep.
     Worst cases: `flat` front face 4.99× and bullnose 2.18×; `overflow` both bullnoses
     1.57×; `channel` bullnose 1.58× and channel walls 1.35×. Vertical faces collapse
     outright. The user does not need side or back faces, so only the noses are corrected.
   - `_wbRelaxUV` scales each nose in **U only**, pivoting on whichever end of that nose's
     block faces the rest of the shell, so the middle never moves and the shell only grows
     outward — which also makes it independent of which way round Maya laid U out (tested
     both ways). **Only ends can be treated this way**: widening an interior run (the
     `channel` walls) would need everything beyond it shifted too, so those are left as
     projected. Because `_wbFitUV` normalises afterwards, the factor sets a nose's
     **share** of the square, not an absolute size.
   - `_wbCapEdges` picks the two end cap perimeters (both of an edge's verts at the same
     Z) and `polyBevel3` chamfers them: **fraction** `WB_COPING_BEVEL` = 0.03, 1 segment,
     chamfer on — the settings the user dialled in by hand. It runs **before** the ribs
     are united, so the ribs keep square ends. The `fraction` attribute is also set with
     `setAttr` after the call, because in some Maya versions it is a separate attribute
     from `offset` and the `offsetAsFraction` flag alone does not land the value.
   - **Adding a profile** is a new record in `WB_COPING_PROFILES` plus one line in
     `WB_COPINGS` — no other code changes. Measure `pts` off the model rather than
     transcribing: every wall triangle of a swept model is parallel to Z, so projecting
     that primitive to XY recovers the loop exactly.
5. **models** — `_wbModelFiles`, `wbImport` (ported from weeTiles' `_wtImportOne`: diff
   `mc.ls(assemblies=True)`, keep roots containing a mesh, rename `<file>_geo`, drop
   pivot), `wbSetFolder`, `wbRefresh`.
6. **UI** — `_wbRow`/`_wbNums`/`_wbCheck`/`_wbLabel`/`_wbFolderRow` (module level, not closures, so
   `_wbFillModels` can rebuild rows on Refresh), `_wbFillModels`, `wbUI`.

## Adding a section

`WB_SECTIONS = [('grates', 'Grates'), ('copings', 'Coping models')]` — one more tuple adds a
whole section: folder field, browse, Refresh, and one import button per model file
found. No other code changes.

## Testing (weeBuild)

`python tests/test_build_logic.py` — stubs `maya.cmds`/`maya.mel` with a recorder and
exec's the *whole* file, so loading the panel is covered too (and `[1]` asserts that no
hotkey is registered). The stub answers enough poly queries to trace a real build: faces are `.f[0]`…
`.f[5]` with "world Y" = the index, so `.f[5]` is always the top. Checks cover name
sanitising, all 8 presets making legal distinct names, the polyCube dims (long→X,
short→Z), bevel offset, X spacing, numbering across repeat presses, rejected arguments,
the coping profile (bbox, area, winding, both fitted arc radii, width stretching, rib
layout) and the coping build (reversed loop, sweep length, rib section, unite, UVs),
folder scanning (spaces, case-blind sort, non-model files, subfolders), import
root-picking and clash-free renaming, and the panel actually building its buttons.

## Git

Repo: `weeTiles` (separate from `weeScript`). Push with the user's local git auth:
```
git add -A && git commit -m "..." && git push
```
