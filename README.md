# weeTiles — tile library browser for Maya

A standalone tool, separate from weeScript: its own file, its own window, its own
hotkey. It shares no code with weeScript and every global is prefixed `wt`/`_wt`,
so both can be loaded in Maya at the same time without colliding.

Browse the Serapool tile models as thumbnails, drag one into the viewport, or fill
a floor with grid / running bond / herringbone in one click.

> This repo also holds a second tool, **weeBuild** (`weeBuild.py`) - a button panel
> that builds tiles procedurally and imports grate / coping models. It is documented
> at the bottom of this file.

## Load it

```python
import urllib.request, __main__
exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py').read().decode('utf-8'), __main__.__dict__)
```

Opens the browser. It registers **no hotkey** — Alt+2 / Alt+3 are already taken in
Maya — so to reopen it without re-downloading, run `weeTiles()`.

Needs Maya 2022+ — PySide2 on 2022–2024, PySide6 on 2025+, picked automatically.

---

## 1. Where the tiles live

One **Library source** field, bottom right. It takes any of these, and remembers
what you typed (optionVar `weeTilesSource`):

| Source | Example | Notes |
|---|---|---|
| **Your website** *(recommended)* | `https://www.serapool.com/3d/tiles/library.json` | Works anywhere, no VPN, no size limits. Must be publicly reachable — no login page in front of it. |
| Network folder | `\\serapool-srv\3d\tiles` | Fastest, nothing to download, but office/VPN only. **Browse…** picks one. |
| GitHub | `https://raw.githubusercontent.com/ersizzle/weeTiles/master/library.json` | Free and works anywhere, but **100 MB per file** (warning at 50 MB), repos should stay under ~1 GB, and GitHub discourages using raw as a CDN. Fine for geometry, tight once 4K textures are involved. |

Point it at the folder or the file — `https://…/3d/tiles` gets `/library.json` appended.

Remote files download **once** into `<maya app dir>/weeTiles/cache/` and are reused,
so the second import is instant and works offline. The panel shows the cache size;
**Clear Cache** empties it. Bumping a tile's `rev` in the manifest re-downloads just
that tile.

## 2. Using it

- **Search** matches name, id, code, size, category and tags as you type; the
  dropdown filters by category.
- **Double-click** a tile, or **Import Selected**, to bring it in at the origin
  (several at once land side by side along X).
- **Drag a tile into the viewport** to drop it where you release — it lands on the
  ground plane under the cursor.
- **Replace Scene Objects** — select tiles already in the scene, pick one library
  tile, press it: each object is swapped for the new product, keeping its exact
  position, rotation, scale and parent. Good for trying products on a finished floor.
- **Import + Fill** — imports the ticked tiles and immediately fills the area.
  With several tiles ticked it picks among them at random, so 4–6 variations of one
  product give a natural floor.
- **Fill with Selected Objects** does the same using tiles already in the scene.

Every imported tile gets its pivot dropped to the bottom centre and is named `<id>_geo`.
*As reference* imports a live link to the library file instead of a copy.

### Patterns

| Pattern | Rotation | Notes |
|---|---|---|
| Grid | 0/90/180/270 for squares, 0/180 for rectangles | Straight stack |
| Running bond | 0/180 | Half-tile offset per row |
| Herringbone | fixed by the pattern | **Needs a 2:1 tile** (33×66). Anything else falls back to running bond with a warning — the interlocking pattern only tiles the plane at 2:1. |

*Grout cm* spaces the tiles (0.3 = 3 mm). *Trim to area* combines a duplicate of the
tiles and live-booleans it against a box the size of the area, so the edges are cut
flush — the original tiles are kept, hidden, in case you want to re-cut.

## 3. Building the library

Folder layout (`thumbs/` and `textures/` optional):

```
serapool_tiles/
	tiles/
		Porcelain/   matt_white_33x66.fbx
		Mosaic/      blue_mix_2.5x2.5.fbx
	thumbs/          matt_white_33x66.jpg      <- same name as the model
	textures/        matt_white_33x66_*.jpg    <- name starts with the model name
	library.json                               <- generated
```

- Sub-folder under `tiles/` becomes the **category**.
- The first `NNxNN` in the file name becomes the **size** (`33x66` → long edge 66
  along X, short edge 33 along Z) and drives the pattern maths.
- A flat folder of FBX files works too — everything lands in category `Other`.

Generate the manifest with plain Python 3, outside Maya:

```bash
python make_tile_library.py D:/serapool_tiles --name "Serapool Tiles"
```

It reports total size, warns about GitHub's limits, and preserves anything you
hand-edited (`name`, `category`, `size`, `tags`) when you re-run it after adding tiles.
Then upload the folder and paste its address into the source field.

### Manifest format

Only `file` is required.

```json
{
	"name": "Serapool Tiles",
	"version": 1,
	"tiles": [
		{
			"id": "matt_white_33x66",
			"name": "Matt White 33x66",
			"category": "Porcelain",
			"size": "33x66",
			"w": 66.0,
			"d": 33.0,
			"file": "tiles/Porcelain/matt_white_33x66.fbx",
			"thumb": "thumbs/matt_white_33x66.jpg",
			"assets": ["textures/matt_white_33x66_basecolor.jpg"],
			"tags": ["white", "matt", "pool"],
			"rev": "f538ecc6"
		}
	]
}
```

| Field | Meaning |
|---|---|
| `id` | Unique key; also the imported node's name (`<id>_geo`). |
| `file` | Model path relative to the manifest — `.fbx`, `.ma`, `.mb`, `.obj`. |
| `thumb` | Preview image, relative to the manifest. Missing → grey placeholder. |
| `assets` | Extra files (textures) cached alongside, keeping the same relative layout so the model's relative texture paths resolve. |
| `w` / `d` | Long edge (X) and short edge (Z) in cm — drives the pattern maths. |
| `rev` | Change it to force a re-download of that tile. |

## 4. If something goes wrong

- **"could not read the library"** — open the manifest address in a browser. If it
  doesn't load there (404, login page, firewall), it won't load in Maya either.
- **Thumbnails stay grey** — the `thumb` path in the manifest is wrong, or the host
  isn't serving images. Everything else still works.
- **Model downloads but doesn't import** — check the script editor; FBX needs the
  `fbxmaya` plugin (loaded automatically), OBJ needs `objExport`.
- **Textures missing** — list them under `assets` so they get cached next to the
  model, and make sure the FBX references them by *relative* path.
- **Drag into the viewport does nothing** — the browser hooks the model panels when
  it opens; if you created a new viewport afterwards, reopen the browser. Import
  Selected always works regardless.
- **Web server refuses .fbx** — some hosts only serve known extensions; add the MIME
  type `application/octet-stream` for `.fbx`.

## 5. Development

The pattern maths and the library/cache code have no Maya dependency, so they are
tested outside it — no Maya, no Qt, no network needed (it spins up a local server):

```bash
python tests/test_logic.py
```

The important one is the coverage test: it samples thousands of interior points and
asserts **exactly one** tile covers each, which is what proves the herringbone lattice
is right. Run it after touching `_wtLayout` or anything under the library banner.

Not covered, because they need a running Maya: the Qt widgets, `mc.file` import,
the viewport drop hook, and the boolean trim.

---

# weeBuild — tile / grate / coping panel for Maya

A second, independent tool in this repo (`weeBuild.py`). Where weeTiles browses a
library of finished models, weeBuild is a weeScript-style dockable button panel that
**builds** tiles from scratch and imports your grate and coping models.

Its own file, its own panel, its own hotkey, and every global prefixed `wb`/`_wb` —
weeScript, weeTiles and weeBuild can all be loaded in Maya at once.

## Load it

```python
import urllib.request, __main__
exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeBuild.py').read().decode('utf-8'), __main__.__dict__)
```

Opens the panel and binds **Shift+Alt+1** to reopen it. Maya remembers hotkeys, so it
survives a restart — after one, the key pulls the file down again before opening.

Because Maya's own `Maya_Default` hotkey set is read-only, the binding goes into a set
called `weeTools`, copied from whatever you were on. If you already use your own custom
set, it is used as-is and nothing is switched. `wbHotkey('7', sht=False)` rebinds to
something else; it warns rather than silently stealing a key that was already in use.

## Tiles

One button per size — **33x66, 33x33, 16.5x66, 16.5x16.5, 11x33, 10x10, 5x5, 12.5x25**
— plus **Custom size…** for anything else. Three fields above them:

| Field | Default | What it does |
| --- | --- | --- |
| Count | 1 | How many master tiles to build, laid out in a row along X |
| Thick | 0.76 | Tile thickness in cm (Y) |
| Grout | 0.15 | Chamfer per top edge, so two tiles meet in a 0.3cm grout valley |

Each tile is built exactly the way weeScript's *Build Tile* builds them: a box, the
four top edges chamfered, the hidden bottom face deleted, planar-Y UVs rotated 90° so
the texture runs along the long edge, and the pivot dropped to bottom centre. The long
edge goes along X, the short one along Z.

They are named `tile_<size>_<nn>_geo` — `tile_33x66_01_geo`, and because Maya node
names cannot contain a dot, `tile_16p5x66_01_geo` for the half sizes. Numbering picks
up from whatever is already in the scene, so pressing a button twice does not clash.

Set Grout to `0` for a plain, unchamfered box.

## Copings

Built procedurally, not imported. Each profile is the real swept cross-section measured
straight off the model in `tile_models/copings/`, so the nose, lip, channel and undercut
are the shapes the product actually has — not an approximation.

| Button | Profile | Notes |
| --- | --- | --- |
| Flat 25 x 50 | `flat` | Bullnose + finger-grip undercut, ribbed underside. Top is not level — it rises 0.66cm to the nose |
| Overflow 25 x 50 | `overflow` | A 25 x 1.20 bar rounded at **both** top edges, exactly symmetric |
| Channel 25 x 50 | `channel` | 25 x 1.60 with a channel 4.03 wide, 0.75 deep, S-curve walls |
| Channel 30 x 50 | `channel` | The same profile widened |

| Field | Default | What it does |
| --- | --- | --- |
| Count | 1 | How many to build, in a row along X |
| Width | per profile | Across the coping, in cm |
| Length | per profile | Along the coping, in cm |
| Bevel | 0.03 | Chamfer on both end cap perimeters, as a *fraction* of the shortest adjacent edge. `0` turns it off |
| Relax | 2 | Gives the squashed nose(s) a bigger share of the UV square, in U only. `1` turns it off |
| underside ribs | per profile | On for `flat`, off for the others |

Changing **Width** stretches only the flat back run. Every nose, lip, channel and
undercut keeps its measured shape — which is the point of rebuilding these rather than
importing a fixed mesh. So `Channel 30 x 50` is the 25cm profile with 5cm more flat
behind it, exactly as the real product varies.

Named `coping_<profile>_<size>_<nn>_geo`, with the same `p`-for-a-dot rule as the tiles —
`coping_channel_30x50_01_geo`.

UVs are projected planar **from the top** — the way the real tiles are painted — and the
shell is then stretched to fill **the whole 0-1 square**, so the texture registers.
Projecting from above compresses anything steep, so **Relax** gives the rounded ends a
bigger share; on the overflow bar it does both ends. Side and back faces are left as the
projection puts them, since they are never seen.

More profiles are one record in `WB_COPING_PROFILES` plus one line in `WB_COPINGS` — no
other code changes.

## Grates and Coping models

These import model files rather than building them. Point a section at a folder with
the **…** button (remembered per Maya user), and you get one button per model file in
it — `.ma`, `.mb`, `.fbx`, `.obj`. Add or remove files and press **Refresh**; no code
change is needed.

Clicking a button imports the file, keeps the top-level nodes that actually contain a
mesh, renames them `<filename>_geo` and drops the pivot to bottom centre.

Any folder works, including one inside this project — the repo's `.gitignore` already
excludes `*.fbx` / `*.ma` / `*.mb`, so models dropped there will not be committed.

Adding another section later (mosaics, steps, …) is one line: append to `WB_SECTIONS`.

## Development

Tested without Maya — `maya.cmds` is stubbed with a recorder and the whole file is
exec'd, so opening the panel is covered too:

```bash
python tests/test_build_logic.py
```

Not covered, because they need a running Maya: the actual panel layout and what
`polyBevel3` / `polyProjection` really produce.
