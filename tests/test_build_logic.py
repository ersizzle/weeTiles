#Tests for weeBuild.py without Maya.
#
#	python tests/test_build_logic.py
#
#It stubs maya.cmds / maya.mel with a recorder object and exec's the whole file,
#so even opening the panel and registering the hotkey is exercised.  The stub
#answers just enough poly queries that a real tile build can be traced: what
#polyCube was asked for, what the bevel offset was, and where each tile landed.

import os
import re
import shutil
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)


class StubMC(object):
	#the maya.cmds surface weeBuild touches.  faces are named .f[0]...f[5] and
	#their "world Y" is the index, so f[5] is always the top and f[0] the bottom.
	def __init__(self):
		self.opt = {}
		self.objects = set()      #objExists answers from here
		self.fields = {}          #textField name -> text
		self.assemblies = []      #what ls(assemblies=True) returns
		self.meshRoots = set()    #which of those carry a mesh
		self.newOnImport = []     #what the next file(i=True) creates
		self.calls = []
		self.warnings = []

	def _rec(self, _call, *a, **kw):
		self.calls.append((_call, a, kw))
	def find(self, name):
		return [c for c in self.calls if c[0] == name]

	#-- settings ------------------------------------------------------------
	def optionVar(self, **kw):
		if 'exists' in kw:
			return kw['exists'] in self.opt
		if 'q' in kw:
			return self.opt.get(kw['q'], '')
		if 'sv' in kw:
			k, v = kw['sv']
			self.opt[k] = v
	def warning(self, m):
		self.warnings.append(m)

	#-- scene ---------------------------------------------------------------
	def objExists(self, n):
		return n in self.objects
	def ls(self, *a, **kw):
		if kw.get('assemblies'):
			return list(self.assemblies)
		pat = a[0] if a else ''
		if isinstance(pat, str) and pat.endswith('.f[*]'):
			return ['%s.f[%d]' % (pat[:-5], i) for i in range(6)]
		if isinstance(pat, (list, tuple)):
			return list(pat)
		return [pat] if pat else []
	def polyCube(self, **kw):
		nm = kw.get('name') or kw.get('n') or 'pCube'
		self._rec('polyCube', **kw)
		self.objects.add(nm)
		return [nm, 'polyCube1']
	def polyListComponentConversion(self, comp, **kw):
		c = comp if isinstance(comp, str) else comp[0]
		if kw.get('tv'):
			return ['%s.vtx' % c]
		if kw.get('te'):
			return ['%s.e' % c]
		return ['%s.map' % c]
	def pointPosition(self, v, **kw):
		m = re.search(r'\.f\[(\d+)\]', v)
		return [0.0, float(m.group(1)) if m else 0.0, 0.0]
	def polyBevel3(self, edges, **kw):
		self._rec('polyBevel3', edges, **kw)
		return ['polyBevel1']
	def polyProjection(self, *a, **kw):
		self._rec('polyProjection', *a, **kw)
	def polyEvaluate(self, *a, **kw):
		return ((0.0, 1.0), (0.0, 1.0))
	def polyEditUV(self, *a, **kw):
		self._rec('polyEditUV', *a, **kw)
	def delete(self, *a, **kw):
		self._rec('delete', *a, **kw)
	def move(self, *a, **kw):
		self._rec('move', *a, **kw)
	def xform(self, *a, **kw):
		if kw.get('q'):
			return [-1.0, 0.0, -1.0, 1.0, 2.0, 1.0]
		self._rec('xform', *a, **kw)
	def select(self, *a, **kw):
		self._rec('select', *a, **kw)
	def rename(self, old, new):
		self.assemblies = [new if n == old else n for n in self.assemblies]
		if old in self.meshRoots:
			self.meshRoots.discard(old)
			self.meshRoots.add(new)
		self.objects.discard(old)
		self.objects.add(new)
		return new
	def listRelatives(self, n, **kw):
		return ['%sShape' % n] if n in self.meshRoots else None
	def file(self, path, **kw):
		self._rec('file', path, **kw)
		for n in self.newOnImport:
			self.assemblies.append(n)
			self.objects.add(n)
	def loadPlugin(self, *a, **kw):
		self._rec('loadPlugin', *a, **kw)

	#-- dialogs / UI (no-ops, they only need to not explode) -----------------
	def promptDialog(self, *a, **kw):
		return ''
	def fileDialog2(self, *a, **kw):
		return None
	def textField(self, *a, **kw):
		nm = a[0] if a else 'tf%d' % len(self.fields)
		if kw.get('q'):
			if kw.get('exists'):
				return nm in self.fields
			return self.fields.get(nm, '')
		if kw.get('e') and 'text' in kw:
			self.fields[nm] = kw['text']
		elif not kw.get('e'):
			self.fields.setdefault(nm, kw.get('text', ''))
		return nm
	def columnLayout(self, *a, **kw):
		if kw.get('q'):
			return False
		return 'col%d' % len(self.calls)
	def frameLayout(self, *a, **kw):
		return 'frame%d' % len(self.calls)
	def formLayout(self, *a, **kw):
		return 'form%d' % len(self.calls)
	def button(self, *a, **kw):
		self._rec('button', *a, **kw)
		return 'btn%d' % len(self.calls)
	def text(self, *a, **kw):
		self._rec('text', *a, **kw)
		return 'txt%d' % len(self.calls)
	def layout(self, *a, **kw):
		return []
	def workspaceControl(self, *a, **kw):
		self._rec('workspaceControl', *a, **kw)
		return False if kw.get('q') else (a[0] if a else 'wc')
	def window(self, *a, **kw):
		return False
	def deleteUI(self, *a, **kw):
		self._rec('deleteUI', *a, **kw)
	def nameCommand(self, *a, **kw):
		return a[0] if a else 'nc'
	def hotkey(self, *a, **kw):
		self._rec('hotkey', *a, **kw)


class StubMel(object):
	def eval(self, s):
		pass


def load(mc):
	#stub maya, then exec weeBuild.py exactly as Maya would
	maya = types.ModuleType('maya')
	maya.cmds = mc
	maya.mel = StubMel()
	sys.modules['maya'] = maya
	sys.modules['maya.cmds'] = mc
	sys.modules['maya.mel'] = maya.mel
	src = open(os.path.join(PROJ, 'weeBuild.py'), encoding='utf-8').read()
	g = {'__name__': 'weeBuildTest'}
	exec(compile(src, 'weeBuild.py', 'exec'), g)
	return g


FAIL = [0]


def check(label, got, want):
	ok = got == want
	if not ok:
		FAIL[0] += 1
	print('  %s %-52s %r%s' % ('ok  ' if ok else 'FAIL', label, got,
							   '' if ok else '   (want %r)' % (want,)))


def main():
	mc = StubMC()
	g = load(mc)
	tmp = tempfile.mkdtemp(prefix='weebuild_')
	try:
		print('\n[1] the file loads and opens the panel')
		check('version', g['WB_VERSION'], '1.0')
		check('workspaceControl created', bool(mc.find('workspaceControl')), True)
		check('Alt+3 registered', mc.find('hotkey')[0][2].get('k'), '3')
		check('no warnings on load', mc.warnings, [])

		print('\n[2] node names - Maya takes no dots')
		check('16.5 x 66 token', g['_wbToken'](16.5, 66.0), '16p5x66')
		check('12.5 x 25 token', g['_wbToken'](12.5, 25.0), '12p5x25')
		check('33 x 66 token', g['_wbToken'](33.0, 66.0), '33x66')
		check('spaces and dashes go', g['_wbSafe']('grate long-bar v2.1'), 'grate_long_bar_v2p1')
		check('leading digit gets a _', g['_wbSafe']('3d_grate'), '_3d_grate')
		check('empty falls back', g['_wbSafe']('...'), 'wbNode')
		names = [g['_wbToken'](s, l) for _lbl, s, l in g['WB_TILES']]
		valid = re.compile(r'^[A-Za-z_][0-9A-Za-z_]*$')
		check('every preset makes a legal name', all(valid.match('tile_%s_01_geo' % n) for n in names), True)
		check('every preset name is distinct', len(set(names)), len(g['WB_TILES']))

		print('\n[3] all 8 sizes the panel offers')
		check('preset count', len(g['WB_TILES']), 8)
		check('presets', [lbl for lbl, _s, _l in g['WB_TILES']],
			  ['33 x 66', '33 x 33', '16.5 x 66', '16.5 x 16.5', '11 x 33', '10 x 10', '5 x 5', '12.5 x 25'])

		print('\n[4] building one tile')
		mc.calls = []
		made = g['wbTile'](16.5, 66.0)
		check('one tile made', made, ['tile_16p5x66_01_geo'])
		cube = mc.find('polyCube')[0][2]
		check('long edge along X', cube['w'], 66.0)
		check('short edge along Z', cube['d'], 16.5)
		check('thickness', cube['h'], 0.76)
		check('bevel offset is the grout', mc.find('polyBevel3')[0][2]['offset'], 0.15)
		check('bevelled the 4 top edges only', mc.find('polyBevel3')[0][1][0], ['tile_16p5x66_01_geo.f[5].e'])
		check('bottom face deleted', mc.find('delete')[1][1][0], 'tile_16p5x66_01_geo.f[0]')
		check('planar Y projection', mc.find('polyProjection')[0][2]['md'], 'y')
		check('UVs rotated 90', mc.find('polyEditUV')[0][2]['angle'], 90)
		check('pivot dropped to bbox bottom', mc.find('xform')[0][2]['piv'], (0.0, 0.0, 0.0))

		print('\n[5] building several - spacing and unique names')
		mc.calls = []
		made = g['wbTile'](33.0, 66.0, count=3)
		check('three tiles', made, ['tile_33x66_01_geo', 'tile_33x66_02_geo', 'tile_33x66_03_geo'])
		check('laid out along X by long + 5', [c[1][0] for c in mc.find('move')], [0.0, 71.0, 142.0])
		again = g['wbTile'](33.0, 66.0, count=2)
		check('a second press keeps numbering up', again, ['tile_33x66_04_geo', 'tile_33x66_05_geo'])

		print('\n[6] tile arguments that should be refused')
		for label, args in [('count 0', (33.0, 66.0, 0)), ('zero size', (0.0, 66.0, 1)),
							('grout wider than half the tile', (10.0, 10.0, 1, 0.76, 6.0))]:
			try:
				g['wbTile'](*args)
				check(label + ' raises', False, True)
			except ValueError:
				check(label + ' raises', True, True)
		mc.calls = []
		flat = g['wbTile'](33.0, 33.0, grout=0)
		check('grout 0 builds with no bevel', (len(flat), len(mc.find('polyBevel3'))), (1, 0))

		print('\n[7] panel number fields')
		check('no panel -> default', g['_wbNum']('count', 1, integer=True), 1)
		g['_wbFields']['count'] = 'countField'
		mc.fields['countField'] = '4'
		check('reads the field', g['_wbNum']('count', 1, integer=True), 4)
		mc.fields['countField'] = ''
		check('empty field -> default', g['_wbNum']('count', 7, integer=True), 7)
		mc.fields['countField'] = 'abc'
		try:
			g['_wbNum']('count', 1, integer=True)
			check('junk field raises', False, True)
		except ValueError:
			check('junk field raises', True, True)
		g['_wbFields'].clear()

		print('\n[8] model folders')
		grates = os.path.join(tmp, 'grate models')
		os.makedirs(grates)
		for f in ['B_grate.fbx', 'a_grate.ma', 'Zed grate.mb', 'notes.txt', 'thumb.png']:
			open(os.path.join(grates, f), 'w').close()
		os.makedirs(os.path.join(grates, 'wip.fbx'))          #a folder, not a model
		g['wbSetFolder']('grates', grates.replace('/', os.sep) + os.sep)
		check('trailing slash trimmed', g['_wbFolder']('grates').endswith('grate models'), True)
		check('stored forward slashed', '\\' in g['_wbFolder']('grates'), False)
		found = [os.path.basename(p) for p in g['_wbModelFiles']('grates')]
		check('models only, sorted case blind', found, ['a_grate.ma', 'B_grate.fbx', 'Zed grate.mb'])
		check('folder persists in the optionVar', 'grates' in g['_wbGetSettings'](), True)
		check('unset section is empty', g['_wbModelFiles']('copings'), [])
		g['_wbSetFolder']('copings', os.path.join(tmp, 'nope'))
		check('missing folder is empty, not an error', g['_wbModelFiles']('copings'), [])

		print('\n[9] importing a model')
		mc.calls = []
		mc.assemblies = ['stray_locator']
		mc.newOnImport = ['grate_mesh_grp', 'importedCam']
		mc.meshRoots = set(['grate_mesh_grp'])
		out = g['wbImport'](os.path.join(grates, 'B_grate.fbx'))
		check('only the mesh root is kept', out, ['B_grate_geo'])
		check('fbx plugin loaded', mc.find('loadPlugin')[0][1][0], 'fbxmaya')
		check('imported as FBX', mc.find('file')[0][2].get('type'), 'FBX')
		check('pivot dropped on the import too', bool(mc.find('xform')), True)
		mc.assemblies = ['B_grate_geo']
		mc.newOnImport = ['grate_mesh_grp2']
		mc.meshRoots = set(['grate_mesh_grp2'])
		out = g['wbImport'](os.path.join(grates, 'B_grate.fbx'))
		check('a second import does not clash', out, ['B_grate_01_geo'])
		mc.newOnImport = ['emptyGrp']
		mc.meshRoots = set()
		mc.warnings = []
		check('no mesh -> nothing back', g['wbImport'](os.path.join(grates, 'a_grate.ma')), [])
		check('no mesh -> a warning', len(mc.warnings), 1)
		try:
			g['wbImport'](os.path.join(tmp, 'ghost.fbx'))
			check('missing file raises', False, True)
		except ValueError:
			check('missing file raises', True, True)

		print('\n[10] button labels')
		check('short name kept', g['_wbWrap']('drain'), 'drain')
		check('long name wraps once', g['_wbWrap']('long_pool_coping_left'), 'long pool\ncoping left')
		check('unbroken name still splits', g['_wbWrap']('aaaaaaaaaaaaaaaa'), 'aaaaaaaaaaaa\naaaa')

		print('\n[11] the panel builds')
		mc.calls = []
		g['wbUI']()
		labels = [c[2].get('label') for c in mc.find('button')]
		check('a button per tile preset', sum(1 for l in labels if l and 'x' in l and '\n' in l), 8)
		check('custom size button', 'Custom size...' in labels, True)
		check('a folder row per model section', labels.count('Refresh'), len(g['WB_SECTIONS']))
	finally:
		shutil.rmtree(tmp, ignore_errors=True)

	print('\n%s\n' % ('ALL CHECKS PASSED' if not FAIL[0] else '%d CHECK(S) FAILED' % FAIL[0]))
	return 1 if FAIL[0] else 0


if __name__ == '__main__':
	sys.exit(main())
