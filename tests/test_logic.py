#Tests for the parts of weeTiles.py that do not need Maya.
#
#	python tests/test_logic.py
#
#It exec's the slice of weeTiles.py between "WT_VERSION =" and the "Maya side"
#banner with a stubbed maya.cmds, builds a throwaway tile library in a temp
#folder, and serves it over a real local HTTP server.  No Maya, no Qt, no network.

import functools
import http.server
import json
import os
import random
import shutil
import socketserver
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


class StubMC(object):
	#the handful of maya.cmds calls the pure regions make
	def __init__(self, appdir):
		self.opt = {}
		self.appdir = appdir
	def optionVar(self, **kw):
		if 'exists' in kw:
			return kw['exists'] in self.opt
		if 'q' in kw:
			return self.opt.get(kw['q'], '')
		if 'sv' in kw:
			k, v = kw['sv']
			self.opt[k] = v
	def internalVar(self, **kw):
		return self.appdir
	def warning(self, m):
		print('  WARNING: %s' % m)


def load_core(mc):
	src = open(os.path.join(PROJ, 'weeTiles.py'), encoding='utf-8').read()
	block = src[src.index('WT_VERSION ='):src.index('#  Maya side:')]
	g = {'mc': mc, 'os': os, 'math': __import__('math'), 'random': random, '__name__': 'wt_core'}
	exec(compile(block, 'weeTiles-core', 'exec'), g)
	return g


def make_library(root):
	#three fake tiles, one with a space in the name and one with a decimal size
	for sub in ('tiles/Porcelain', 'tiles/Mosaic', 'thumbs', 'textures'):
		os.makedirs(os.path.join(root, sub))
	files = {
		'tiles/Porcelain/matt_white_33x66.fbx': 'fbx-1',
		'tiles/Porcelain/anti_slip_grey 33x33.fbx': 'fbx-2',
		'tiles/Mosaic/blue_mix_2.5x2.5.fbx': 'fbx-3',
		'thumbs/matt_white_33x66.jpg': 'img',
		'textures/matt_white_33x66_basecolor.jpg': 'tex',
	}
	for rel, body in files.items():
		h = open(os.path.join(root, rel), 'w')
		h.write(body)
		h.close()
	man = {'name': 'Test Tiles', 'version': 1, 'tiles': [
		{'id': 'matt_white_33x66', 'name': 'Matt White', 'category': 'Porcelain', 'size': '33x66',
		 'w': 66.0, 'd': 33.0, 'file': 'tiles/Porcelain/matt_white_33x66.fbx',
		 'thumb': 'thumbs/matt_white_33x66.jpg',
		 'assets': ['textures/matt_white_33x66_basecolor.jpg'], 'rev': 'r1'},
		{'id': 'anti_slip_grey', 'name': 'Anti Slip Grey', 'category': 'Porcelain', 'size': '33x33',
		 'w': 33.0, 'd': 33.0, 'file': 'tiles/Porcelain/anti_slip_grey 33x33.fbx', 'rev': 'r1'},
		{'id': 'blue_mix', 'name': 'Blue Mix', 'category': 'Mosaic', 'size': '2.5x2.5',
		 'file': 'tiles/Mosaic/blue_mix_2.5x2.5.fbx', 'rev': 'r1'},
	]}
	h = open(os.path.join(root, 'library.json'), 'w', encoding='utf-8')
	json.dump(man, h, indent='\t')
	h.close()


FAIL = [0]
def check(label, got, want=True):
	ok = (got == want)
	print(('  ok   ' if ok else '  FAIL ') + label + '  ->  ' + repr(got))
	if not ok:
		print('        expected ' + repr(want))
		FAIL[0] += 1


def _rect(x, z, ry, L, W):
	hx, hz = (L / 2.0, W / 2.0) if abs(ry) < 45 else (W / 2.0, L / 2.0)
	return (x - hx, x + hx, z - hz, z + hz)

def coverage(spots, L, W, area_w, area_l, samples=4000):
	#how many tiles cover each sampled interior point.  {1: n} means the pattern
	#tiles the plane exactly - no overlaps, no gaps.
	rs = [_rect(x, z, ry, L, W) for x, z, ry in spots]
	counts = {}
	rnd = random.Random(7)
	for _ in range(samples):
		px = rnd.uniform(area_w * 0.2, area_w * 0.8)
		pz = rnd.uniform(area_l * 0.2, area_l * 0.8)
		n = 0
		tie = False
		for x0, x1, z0, z1 in rs:
			if abs(px - x0) < 1e-9 or abs(px - x1) < 1e-9 or abs(pz - z0) < 1e-9 or abs(pz - z1) < 1e-9:
				tie = True                      #point sits exactly on a border
				break
			if x0 < px < x1 and z0 < pz < z1:
				n += 1
		if not tie:
			counts[n] = counts.get(n, 0) + 1
	return counts


def main():
	tmp = tempfile.mkdtemp(prefix='weeTiles_test_')
	lib = os.path.join(tmp, 'lib')
	appdir = os.path.join(tmp, 'mayaAppDir')
	os.makedirs(appdir)
	make_library(lib)
	mc = StubMC(appdir)
	g = load_core(mc)
	srv = None
	try:
		print('\n[1] source / url helpers')
		check('folder -> manifest', g['_wtManifestUrl']('https://serapool.com/3d/tiles'), 'https://serapool.com/3d/tiles/library.json')
		check('manifest passthrough', g['_wtManifestUrl']('https://s.com/a/lib.json'), 'https://s.com/a/lib.json')
		check('base of manifest', g['_wtBase']('https://serapool.com/3d/tiles/library.json'), 'https://serapool.com/3d/tiles')
		unc = (chr(92) * 2) + 'srv' + chr(92) + '3d' + chr(92) + 'tiles'
		check('UNC normalised to forward slashes', g['_wtManifestUrl'](unc), '//srv/3d/tiles/library.json')
		check('http detected', g['_wtIsUrl']('HTTPS://a'), True)
		check('UNC is not a url', g['_wtIsUrl']('//srv/x'), False)

		print('\n[2] tile size  ->  (long, short)')
		check('from w/d', g['_wtSize']({'w': 66.0, 'd': 33.0}), (66.0, 33.0))
		check('from size text', g['_wtSize']({'size': '33x66'}), (66.0, 33.0))
		check('single value = square', g['_wtSize']({'size': '15'}), (15.0, 15.0))
		check('unknown', g['_wtSize']({}), (None, None))
		check('search haystack', 'porcelain' in g['_wtHaystack']({'category': 'Porcelain'}), True)

		print('\n[3] GRID layout  (33x33, 300x300 area, no grout)')
		sp = g['_wtLayout']('grid', 33.0, 33.0, 300.0, 300.0, 0.0, False)
		check('tiles placed', len(sp) > 80, True)
		check('every interior point covered exactly once', sorted(coverage(sp, 33.0, 33.0, 300.0, 300.0)), [1])

		print('\n[4] RUNNING BOND layout  (33x66, 600x600, no grout)')
		sp = g['_wtLayout']('bond', 66.0, 33.0, 600.0, 600.0, 0.0, False)
		check('tiles placed', len(sp) > 150, True)
		check('no overlaps, no gaps', sorted(coverage(sp, 66.0, 33.0, 600.0, 600.0)), [1])

		print('\n[5] HERRINGBONE layout  (33x66 = 2:1, 600x600, no grout)')
		sp = g['_wtLayout']('herringbone', 66.0, 33.0, 600.0, 600.0, 0.0, False)
		check('tiles placed', len(sp) > 150, True)
		check('the L-pair lattice tiles the plane exactly once', sorted(coverage(sp, 66.0, 33.0, 600.0, 600.0)), [1])
		check('both orientations present', sorted(set(ry for _x, _z, ry in sp)), [0.0, 90.0])

		print('\n[6] HERRINGBONE with 3mm grout  (gaps fine, overlaps not)')
		cov = coverage(g['_wtLayout']('herringbone', 66.0, 33.0, 600.0, 600.0, 0.3, False), 66.0, 33.0, 600.0, 600.0)
		check('never two tiles on one point', max(cov), 1)
		check('still >95% covered', cov.get(1, 0) / float(sum(cov.values())) > 0.95, True)

		print('\n[7] odds and ends')
		a = g['_wtLayout']('grid', 33.0, 33.0, 300.0, 300.0, 0.0, False)
		b = g['_wtLayout']('grid', 33.0, 33.0, 300.0, 300.0, 0.3, False)
		check('grout widens the step', b[1][0] - a[1][0] > 0.29, True)
		check('bad tile size places nothing', g['_wtLayout']('grid', 0, 0, 100, 100), [])
		check('square tile can spin 4 ways', sorted(set(r for _x, _z, r in g['_wtLayout']('grid', 33.0, 33.0, 300.0, 300.0, 0.0, True))), [0.0, 90.0, 180.0, 270.0])
		check('rectangle only spins 0/180', sorted(set(r for _x, _z, r in g['_wtLayout']('grid', 66.0, 33.0, 600.0, 600.0, 0.0, True))), [0.0, 180.0])

		print('\n[8] manifest + cache from a LOCAL folder')
		mc.optionVar(sv=('weeTilesSource', lib))
		check('tiles read', len(g['_wtLoad'](force=True)['tiles']), 3)
		check('local file resolved in place', os.path.isfile(g['_wtFetch']('tiles/Porcelain/matt_white_33x66.fbx')), True)
		try:
			g['_wtFetch']('tiles/nope.fbx')
			check('missing file raises', False, True)
		except IOError:
			check('missing file raises IOError', True, True)

		print('\n[9] manifest + cache over HTTP')
		handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=lib)
		socketserver.TCPServer.allow_reuse_address = True
		srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
		threading.Thread(target=srv.serve_forever, daemon=True).start()
		url = 'http://127.0.0.1:%d/library.json' % srv.server_address[1]
		mc.optionVar(sv=('weeTilesSource', url))
		g['_wtLib'] = {}
		check('manifest over http', len(g['_wtLoad'](force=True)['tiles']), 3)
		base, cache = g['_wtBase'](url), g['_wtCacheDir']()
		#worker-thread style: base + cache passed in, so no maya.cmds is touched
		rel = 'tiles/Porcelain/anti_slip_grey 33x33.fbx'
		p = g['_wtFetch'](rel, 'r1', base=base, cache=cache)
		check('downloaded despite the space in the name', os.path.isfile(p), True)
		check('content intact', open(p).read().strip(), 'fbx-2')
		check('cached under the maya app dir', cache in p, True)
		mt = os.path.getmtime(p)
		g['_wtFetch'](rel, 'r1', base=base, cache=cache)
		check('second call hits the cache', os.path.getmtime(p) == mt, True)
		g['_wtFetch'](rel, 'r2', base=base, cache=cache)
		check('rev bump forces a re-download', open(p + '.rev').read(), 'r2')
		check('cache size reported', g['_wtCacheSize']() > 0, True)

		print('\n[10] settings round trip')
		g['_wtSaveSettings']({'pattern': 2, 'areaW': 800.0})
		check('settings persist', g['_wtGetSettings']().get('pattern'), 2)
	finally:
		if srv:
			srv.shutdown()
		shutil.rmtree(tmp, ignore_errors=True)

	print('\n%s\n' % ('ALL CHECKS PASSED' if not FAIL[0] else '%d CHECK(S) FAILED' % FAIL[0]))
	return 1 if FAIL[0] else 0


if __name__ == '__main__':
	sys.exit(main())
