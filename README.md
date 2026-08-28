# weeTiles — tile library browser for Maya

A standalone tool, separate from weeScript: its own file, its own window, its own
hotkey. It shares no code with weeScript and every global is prefixed `wt`/`_wt`,
so both can be loaded in Maya at the same time without colliding.

Browse the Serapool tile models as thumbnails, drag one into the viewport, or fill
a floor with grid / running bond / herringbone in one click.

## Load it

```python
import urllib.request, __main__
exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py').read().decode('utf-8'), __main__.__dict__)
```

Opens the browser and registers **Alt+2**, which re-pulls the file and reopens it
(same idea as weeScript's Alt+1). To reopen without re-downloading, run `weeTiles()`.

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
