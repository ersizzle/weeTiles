#!/usr/bin/env python3
#Build the library.json manifest that the weeTools Tile Library reads.
#
#Run it OUTSIDE Maya (plain Python 3) on the folder you are going to upload:
#
#	python make_tile_library.py  D:/serapool_tiles
#
#Expected folder layout (thumbs/ and textures/ are optional):
#
#	serapool_tiles/
#		tiles/
#			Porcelain/  matt_white_33x66.fbx
#			Mosaic/     blue_mix_2.5x2.5.fbx
#		thumbs/         matt_white_33x66.jpg
#		textures/       matt_white_33x66_basecolor.jpg
#		library.json    <- written by this script
#
#Rules
#	category  = the sub-folder under tiles/  ('Other' if the file sits directly in tiles/)
#	size      = the first  NNxNN  found in the file name (cm), e.g. 33x66
#	thumb     = thumbs/<same name>.jpg|png|...  (or an image next to the model)
#	assets    = every file in textures/ whose name starts with the model's name
#	rev       = short hash of the model file, so the tool re-downloads it when it changes
#
#Anything you hand-edit in library.json (name, tags, category, size) is kept on
#the next run - only new tiles are added and removed tiles are dropped.

import hashlib
import json
import os
import re
import sys

MODEL_EXT = ('.fbx', '.ma', '.mb', '.obj')
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.tga')
SIZE_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*[xX*]\s*(\d+(?:[.,]\d+)?)')
KEEP = ('name', 'category', 'size', 'w', 'd', 'tags', 'code', 'note')


def rel(root, path):
	return os.path.relpath(path, root).replace('\\', '/')


def digest(path):
	h = hashlib.md5()
	f = open(path, 'rb')
	try:
		while True:
			b = f.read(1 << 20)
			if not b:
				break
			h.update(b)
	finally:
		f.close()
	return h.hexdigest()[:8]


def parse_size(stem):
	m = SIZE_RE.search(stem)
	if not m:
		return '', None, None
	a = float(m.group(1).replace(',', '.'))
	b = float(m.group(2).replace(',', '.'))
	return '%gx%g' % (min(a, b), max(a, b)), max(a, b), min(a, b)


def pretty(stem):
	#'matt_white_33x66' -> 'Matt White 33x66'
	return ' '.join(w.capitalize() if w.islower() else w for w in re.split(r'[_\-]+', stem) if w)


def find_image(folder, stem):
	for ext in IMAGE_EXT:
		for cand in (stem + ext, stem + ext.upper()):
			p = os.path.join(folder, cand)
			if os.path.isfile(p):
				return p
	return None


def scan(root):
	tiles_dir = os.path.join(root, 'tiles')
	if not os.path.isdir(tiles_dir):
		tiles_dir = root                                     #flat folder is fine too
	thumbs_dir = os.path.join(root, 'thumbs')
	tex_dir = os.path.join(root, 'textures')
	tex_files = []
	if os.path.isdir(tex_dir):
		for dirpath, _dirs, names in os.walk(tex_dir):
			tex_files += [os.path.join(dirpath, n) for n in names]

	out = []
	for dirpath, _dirs, names in os.walk(tiles_dir):
		for n in sorted(names):
			if not n.lower().endswith(MODEL_EXT):
				continue
			path = os.path.join(dirpath, n)
			stem = os.path.splitext(n)[0]
			cat = rel(tiles_dir, dirpath).split('/')[0]
			if cat in ('.', ''):
				cat = 'Other'
			size, long_, short = parse_size(stem)
			thumb = None
			if os.path.isdir(thumbs_dir):
				thumb = find_image(thumbs_dir, stem)
			if not thumb:
				thumb = find_image(dirpath, stem)
			entry = {
				'id': stem,
				'name': pretty(stem),
				'category': cat,
				'size': size,
				'file': rel(root, path),
				'rev': digest(path),
			}
			if long_:
				entry['w'] = long_                            #long edge, along X
				entry['d'] = short                            #short edge, along Z
			if thumb:
				entry['thumb'] = rel(root, thumb)
			assets = [rel(root, t) for t in tex_files if os.path.basename(t).startswith(stem)]
			if assets:
				entry['assets'] = sorted(assets)
			out.append(entry)
	return out


def merge(old_path, tiles):
	#keep whatever was hand-edited in the previous manifest
	if not os.path.isfile(old_path):
		return tiles
	try:
		old = json.load(open(old_path, encoding='utf-8')).get('tiles') or []
	except Exception as e:
		print('  (could not read the old manifest: %s)' % e)
		return tiles
	by_id = dict((t.get('id'), t) for t in old)
	for t in tiles:
		prev = by_id.get(t['id'])
		if not prev:
			continue
		for k in KEEP:
			if prev.get(k) not in (None, '', []) and prev.get(k) != t.get(k):
				t[k] = prev[k]
	return tiles


def report(root, tiles):
	total = 0
	big = []
	for t in tiles:
		for r in [t['file'], t.get('thumb')] + list(t.get('assets') or []):
			if not r:
				continue
			p = os.path.join(root, r)
			if os.path.isfile(p):
				sz = os.path.getsize(p)
				total += sz
				if sz > 50 * 1024 * 1024:
					big.append((r, sz))
	print('  %d tile(s), %.1f MB total' % (len(tiles), total / 1048576.0))
	for r, sz in big:
		print('  WARNING  %s is %.0f MB - over GitHub\'s 50 MB warning (100 MB hard limit)' % (r, sz / 1048576.0))
	if total > 900 * 1024 * 1024:
		print('  WARNING  the library is close to 1 GB - host it on the website, not GitHub')


def main():
	if len(sys.argv) < 2:
		print(__doc__ or '')
		print('usage: python make_tile_library.py <library folder> [-o library.json] [--name "Serapool Tiles"]')
		return 1
	root = os.path.abspath(sys.argv[1])
	if not os.path.isdir(root):
		print('not a folder: %s' % root)
		return 1
	out = os.path.join(root, 'library.json')
	title = 'Serapool Tile Library'
	if '-o' in sys.argv:
		out = os.path.abspath(sys.argv[sys.argv.index('-o') + 1])
	if '--name' in sys.argv:
		title = sys.argv[sys.argv.index('--name') + 1]

	print('scanning %s' % root)
	tiles = merge(out, scan(root))
	if not tiles:
		print('  no %s files found under tiles/' % ' / '.join(MODEL_EXT))
		return 1
	data = {'name': title, 'version': 1, 'tiles': tiles}
	f = open(out, 'w', encoding='utf-8')
	try:
		json.dump(data, f, indent='\t', ensure_ascii=False)
		f.write('\n')
	finally:
		f.close()
	report(root, tiles)
	cats = sorted(set(t['category'] for t in tiles))
	print('  categories: %s' % ', '.join(cats))
	print('wrote %s' % out)
	print('\nUpload this whole folder, then paste its address into the Tile Library')
	print('source field, e.g.  https://www.serapool.com/3d/tiles/library.json')
	return 0


if __name__ == '__main__':
	sys.exit(main())
