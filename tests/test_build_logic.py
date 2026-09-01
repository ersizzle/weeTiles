#Tests for weeBuild.py without Maya.
#
#	python tests/test_build_logic.py
#
#It stubs maya.cmds / maya.mel with a recorder object and exec's the whole file,
#so even opening the panel and registering the hotkey is exercised.  The stub
#answers just enough poly queries that a real tile build can be traced: what
#polyCube was asked for, what the bevel offset was, and where each tile landed.

import math
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
		self.checks = {}          #checkBox name -> value
		self.attrs = {}           #setAttr'd plug -> value
		#stub sweep topology for the coping: e[0..26] is the cap loop at Z=0,
		#e[27..53] the cap loop at Z=sweepLen, e[54..80] the walls between them
		self.profileEdges = 27
		self.sweepLen = 50.0
		#stub UV layout: map[i] sits at u = i/(n-1) * 0.5 and belongs to a vertex at
		#X = -18.86 + i/(n-1) * 25.  uvFlip reverses U so the nose lands at low u,
		#which is how we check the relax pivot does not depend on Maya's U direction.
		self.uvCount = 20
		self.uvFlip = False
		#the X span the stub's verts cover.  defaults to the 25cm the profiles were
		#measured at; a test building a wider coping must widen this too, or the nose
		#thresholds land outside the stub's verts and nothing gets selected
		self.uvXMin = -18.86
		self.uvXSpan = 25.0
		self.uvBB = ((0.0, 1.0), (0.0, 1.0))   #what polyEvaluate(bb2) reports
		self.promptButton = ''                 #what promptDialog returns
		self.promptText = ''                   #and what it says when queried
		self.hotkeySets = set()
		self.hotkeySetCur = 'Maya_Default'     #the read only one Maya starts on
		self.hotkeyTaken = ''                  #what hotkey(q=True, name=True) answers
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
		if isinstance(pat, str) and pat.endswith('.e[*]'):
			return ['%s.e[%d]' % (pat[:-5], i) for i in range(3 * self.profileEdges)]
		if isinstance(pat, str) and pat.endswith('.map[*]'):
			return ['%s.map[%d]' % (pat[:-7], i) for i in range(self.uvCount)]
		if isinstance(pat, (list, tuple)):
			return list(pat)
		return [pat] if pat else []
	def polyCube(self, **kw):
		nm = kw.get('name') or kw.get('n') or 'pCube'
		self._rec('polyCube', **kw)
		self.objects.add(nm)
		return [nm, 'polyCube1']
	def _uvFrac(self, c):
		m = re.search(r'\.map\[(\d+)\]', c)
		return (int(m.group(1)) if m else 0) / float(max(self.uvCount - 1, 1))
	def polyListComponentConversion(self, comp, **kw):
		c = comp if isinstance(comp, str) else comp[0]
		if kw.get('fuv') and kw.get('tv'):
			#the vert this UV belongs to, with its X baked into the name
			return ['%s|x%g' % (c, self.uvXMin + self._uvFrac(c) * self.uvXSpan)]
		if kw.get('fe') and kw.get('tv'):
			#an edge's two verts, with their Z baked into the name for pointPosition
			m = re.search(r'\.e\[(\d+)\]', c)
			i = int(m.group(1)) if m else 0
			n = self.profileEdges
			if i < n:
				z0 = z1 = 0.0
			elif i < 2 * n:
				z0 = z1 = self.sweepLen
			else:
				z0, z1 = 0.0, self.sweepLen
			return ['%s|z%g' % (c, z0), '%s|z%g' % (c, z1)]
		if kw.get('tv'):
			return ['%s.vtx' % c]
		if kw.get('te'):
			return ['%s.e' % c]
		return ['%s.map' % c]
	def pointPosition(self, v, **kw):
		if '|z' in v:
			return [0.0, 0.0, float(v.split('|z')[1])]
		if '|x' in v:
			return [float(v.split('|x')[1]), 0.0, 0.0]
		m = re.search(r'\.f\[(\d+)\]', v)
		return [0.0, float(m.group(1)) if m else 0.0, 0.0]
	def polyCylinder(self, **kw):
		nm = kw.get('name') or kw.get('n') or 'pCylinder'
		self._rec('polyCylinder', **kw)
		self.objects.add(nm)
		return [nm, 'polyCylinder1']
	def polyCreateFacet(self, **kw):
		nm = kw.get('name') or kw.get('n') or 'pFacet'
		self._rec('polyCreateFacet', **kw)
		self.objects.add(nm)
		return [nm, 'polyCreateFacet1']
	def polyExtrudeFacet(self, *a, **kw):
		self._rec('polyExtrudeFacet', *a, **kw)
		return ['polyExtrudeFace1']
	def polyCloseBorder(self, *a, **kw):
		self._rec('polyCloseBorder', *a, **kw)
	def polyUnite(self, parts, **kw):
		nm = kw.get('name') or kw.get('n') or 'polySurface1'
		self._rec('polyUnite', parts, **kw)
		self.objects.add(nm)
		return [nm, 'polyUnite1']
	def polyBevel3(self, edges, **kw):
		self._rec('polyBevel3', edges, **kw)
		return ['polyBevel1']
	def polyProjection(self, *a, **kw):
		self._rec('polyProjection', *a, **kw)
	def polyEvaluate(self, *a, **kw):
		return self.uvBB
	def polyEditUV(self, *a, **kw):
		if kw.get('q'):
			c = a[0] if isinstance(a[0], str) else a[0][0]
			f = self._uvFrac(c)
			return [(1.0 - f) * 0.5 if self.uvFlip else f * 0.5, 0.0]
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
	def setAttr(self, plug, *a, **kw):
		self._rec('setAttr', plug, *a, **kw)
		self.attrs[plug] = a[0] if a else None
	def loadPlugin(self, *a, **kw):
		self._rec('loadPlugin', *a, **kw)

	#-- dialogs / UI (no-ops, they only need to not explode) -----------------
	def promptDialog(self, *a, **kw):
		if kw.get('q'):
			return self.promptText
		self._rec('promptDialog', *a, **kw)
		return self.promptButton
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
	def checkBox(self, *a, **kw):
		nm = a[0] if a else 'chk%d' % len(self.checks)
		if kw.get('q'):
			if kw.get('exists'):
				return nm in self.checks
			return self.checks.get(nm, False)
		if kw.get('e') and 'value' in kw:
			self.checks[nm] = kw['value']
		elif not kw.get('e'):
			self._rec('checkBox', *a, **kw)
			self.checks.setdefault(nm, kw.get('value', False))
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
		self._rec('nameCommand', *a, **kw)
		return a[0] if a else 'nc'
	def hotkey(self, *a, **kw):
		if kw.get('q'):
			return self.hotkeyTaken
		self._rec('hotkey', *a, **kw)
	def hotkeySet(self, *a, **kw):
		self._rec('hotkeySet', *a, **kw)
		if kw.get('q'):
			return self.hotkeySetCur if kw.get('current') else False
		if kw.get('exists'):
			return (a[0] if a else '') in self.hotkeySets
		nm = a[0] if a else 'hotkeySet1'
		self.hotkeySets.add(nm)
		self.hotkeySetCur = nm
		return nm


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


def area(pts):
	#signed area of the closed profile - sign tells us the winding
	n = len(pts)
	return sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
			   for i in range(n)) / 2.0


def fitcirc(pts):
	#least squares circle (Kasa): x^2+y^2 + Ax + By + C = 0, solved by hand so
	#the tests stay dependency free.  returns (cx, cy, r, worst deviation).
	M = [[0.0] * 4 for _ in range(3)]
	for x, y in pts:
		row = [x, y, 1.0]
		w = -(x * x + y * y)
		for i in range(3):
			for j in range(3):
				M[i][j] += row[i] * row[j]
			M[i][3] += row[i] * w
	for i in range(3):
		pv = max(range(i, 3), key=lambda r: abs(M[r][i]))
		M[i], M[pv] = M[pv], M[i]
		for r in range(3):
			if r != i and M[i][i]:
				f = M[r][i] / M[i][i]
				for c in range(i, 4):
					M[r][c] -= f * M[i][c]
	A, B, C = [M[i][3] / M[i][i] for i in range(3)]
	cx, cy = -A / 2.0, -B / 2.0
	r = math.sqrt(max(cx * cx + cy * cy - C, 0.0))
	dev = max(abs(math.hypot(x - cx, y - cy) - r) for x, y in pts)
	return cx, cy, r, dev


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
		hk = mc.find('hotkey')[0]
		check('Shift+Alt+1 bound', hk[1][0], '1')
		check('   alt', hk[2].get('altModifier'), True)
		check('   shift', hk[2].get('shiftModifier'), True)
		check('   not ctrl', hk[2].get('ctrlModifier'), False)
		check('bound to our nameCommand', hk[2].get('name'), 'weeBuildOpen')
		nm = mc.find('nameCommand')[0][2]
		check('the command is python, not MEL', nm.get('sourceType'), 'python')
		check('reopens when already loaded', '__main__.weeBuild()' in nm['command'], True)
		check('bootstraps from the URL when not', g['WB_SELF_URL'] in nm['command'], True)
		check('left the read only default set', mc.hotkeySetCur, 'weeTools')
		check('copied it rather than starting blank',
			  mc.find('hotkeySet')[-1][2].get('source'), 'Maya_Default')
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
		tilebtn = [l for l in labels if l and l.replace('\n', ' ').replace('x', '').replace(' ', '')
				   .replace('.', '').isdigit()]
		check('a button per tile preset', len(tilebtn), 8)
		check('custom size button', 'Custom size...' in labels, True)
		check('a folder row per model section', labels.count('Refresh'), len(g['WB_SECTIONS']))
		check('a button per coping preset',
			  sum(1 for l in labels if l and l.replace('\n', ' ') in
				  [c[0] for c in g['WB_COPINGS']]), len(g['WB_COPINGS']))
		check('four coping presets', len(g['WB_COPINGS']), 4)
		check('all three profiles offered',
			  sorted(set(c[1] for c in g['WB_COPINGS'])), ['channel', 'flat', 'overflow'])
		check('a Custom button for tiles, copings and grates',
			  labels.count('Custom size...'), 3)
		check('a button per grate preset',
			  sum(1 for l in labels if l in [q[0] for q in g['WB_GRATES']]), len(g['WB_GRATES']))
		check('ribs checkbox', [c[2].get('label') for c in mc.find('checkBox')], ['underside ribs'])

		print('\n[12] coping profile maths - no Maya in here')
		prof = g['WB_COPING_PROFILES']['flat']['pts']
		xs = [x for x, _y in prof]
		ys = [y for _x, y in prof]
		check('27 measured points', len(prof), 27)
		check('width as measured', round(max(xs) - min(xs), 4), 25.0)
		check('height as measured', round(max(ys) - min(ys), 4), 2.2591)
		check('sits on the floor', round(min(ys), 4), -0.04)
		check('cross-section area', round(abs(area(prof)), 4), 27.6757)
		check('measured loop runs clockwise', area(prof) < 0, True)
		#the bullnose is an exact circle in the source - if someone "tidies" the
		#stored decimals this is what notices
		nose = prof[19:26]
		_cx, _cy, r, dev = fitcirc(nose)
		check('bullnose is 7 points', len(nose), 7)
		check('bullnose radius', round(r, 4), 0.9651)
		#3.5e-05 is the rounding floor of 4-decimal coordinates, so this is as
		#circular as the stored numbers can express - it is a true arc, not a fit
		check('bullnose is an exact arc', dev < 1e-4, True)
		_cx, _cy, r2, dev2 = fitcirc(prof[0:8])
		check('grip undercut radius', round(r2, 3), 1.035)
		check('grip undercut is near-circular', dev2 < 0.03, True)

		same = g['_wbCopingProfile']('flat', 25.0)
		check('default width is a no-op', same, prof)
		wide = g['_wbCopingProfile']('flat', 35.0)
		wx = [x for x, _y in wide]
		check('wider: back edge moves back', round(min(wx), 4), -28.86)
		check('wider: nose stays put', round(max(wx), 4), 6.14)
		check('wider: width comes out right', round(max(wx) - min(wx), 4), 35.0)
		check('wider: nose detail untouched',
			  [pt for pt in wide if pt[0] > -13.0], [pt for pt in prof if pt[0] > -13.0])
		check('wider: still 27 points', len(wide), 27)

		check('only the flat profile has ribs',
			  [k for k, v in sorted(g['WB_COPING_PROFILES'].items()) if v['ribs']], ['flat'])
		check('ribs at 25cm', [round(c, 4) for c in g['_wbCopingRibs'](prof)],
			  [-18.32, -15.32, -12.32, -9.32, -6.32, -3.32, -0.32, 2.68])
		check('8 ribs, as the source model has', len(g['_wbCopingRibs'](prof)), 8)
		check('a wider coping gets more ribs', len(g['_wbCopingRibs'](wide)), 11)
		check('last rib stops short of the nose',
			  round(max(g['_wbCopingRibs'](prof)) + g['WB_RIB_W'] / 2.0, 4), g['WB_RIB_LIMIT'])

		for bad, why in ((15.0, 'too narrow'), (0.0, 'zero')):
			try:
				g['_wbCopingProfile']('flat', bad)
				check('width %s rejected' % why, False, True)
			except ValueError:
				check('width %s rejected' % why, True, True)
		try:
			g['_wbCopingProfile']('round', 25.0)
			check('unknown profile rejected', False, True)
		except ValueError:
			check('unknown profile rejected', True, True)

		print('\n[13] building a coping')
		mc.calls = []
		made = g['wbCoping']()
		check('one coping made', made, ['coping_flat_25x50_01_geo'])
		facet = mc.find('polyCreateFacet')[0][2]
		check('27 point facet', len(facet['p']), 27)
		check('the loop is reversed for the sweep', facet['p'][0], (6.14, -0.04, 0.0))
		check('facet is flat in Z', set(pt[2] for pt in facet['p']), set([0.0]))
		check('swept along the normal by the length',
			  mc.find('polyExtrudeFacet')[0][2]['localTranslateZ'], 50.0)
		check('back cap closed', len(mc.find('polyCloseBorder')), 1)
		ribs = mc.find('polyCube')
		check('8 ribs built', len(ribs), 8)
		check('rib section', (ribs[0][2]['w'], ribs[0][2]['h'], ribs[0][2]['d']), (1.0, 1.3, 50.0))
		check('ribs merged, not booleaned', len(mc.find('polyUnite')[0][1][0]), 9)
		check('planar Y projection', mc.find('polyProjection')[0][2]['md'], 'y')
		check('no UV rotation on a coping',
			  [c for c in mc.find('polyEditUV') if 'angle' in c[2]], [])
		#the fit is the last thing done to the UVs - relax runs before it
		fit = mc.find('polyEditUV')[-2:]
		check('shell stretched to fill 0-1',
			  (fit[0][2]['scaleU'], fit[0][2]['scaleV']), (1.0, 1.0))
		check('scaled about the shell corner',
			  (fit[0][2]['pivotU'], fit[0][2]['pivotV']), (0.0, 0.0))
		check('then moved to the 0-1 origin', fit[1][2]['relative'], True)

		mc.calls = []
		g['wbCoping'](ribs=False)
		check('ribs off -> no cubes', mc.find('polyCube'), [])
		check('ribs off -> nothing to unite', mc.find('polyUnite'), [])

		mc.calls = []
		three = g['wbCoping'](count=3, ribs=False)
		check('three copings', len(three), 3)
		check('numbering keeps going', three[-1], 'coping_flat_25x50_05_geo')
		check('laid out along X by width + 5',
			  [round(c[1][0], 4) for c in mc.find('move')], [0.0, 30.0, 60.0])
		check('decimal sizes make a legal name',
			  g['wbCoping'](width=22.5, length=37.5, ribs=False), ['coping_flat_22p5x37p5_01_geo'])

		for kw, why in (({'length': 0}, 'zero length'), ({'count': 0}, 'zero count'),
						({'width': 10}, 'too narrow')):
			try:
				g['wbCoping'](**kw)
				check('%s rejected' % why, False, True)
			except ValueError:
				check('%s rejected' % why, True, True)
		print('\n[14] the end cap bevel')
		mc.calls = []
		node = g['wbCoping'](ribs=False)[0]
		bev = mc.find('polyBevel3')
		check('bevel applied once', len(bev), 1)
		check('fraction, not an absolute offset', bev[0][2]['offsetAsFraction'], True)
		check('fraction is 0.03 as dialled in', bev[0][2]['offset'], 0.03)
		check('one segment', bev[0][2]['segments'], 1)
		check('depth 1', bev[0][2]['depth'], 1)
		check('"Fraction" attr set directly too', list(mc.attrs.values()), [0.03])
		#e[0..26] is the cap loop at Z=0 and e[27..53] the one at Z=length; the
		#walls e[54..80] run between the two ends and must be left alone
		edges = bev[0][1][0]
		check('both cap loops bevelled', len(edges), 54)
		check('the near cap', edges[0], node + '.e[0]')
		check('the far cap', edges[-1], node + '.e[53]')
		check('no wall edge bevelled',
			  [e for e in edges if int(e.split('[')[1][:-1]) >= 54], [])
		check('history baked after the bevel', len(mc.find('delete')) >= 1, True)

		mc.calls = []
		mc.attrs = {}
		g['wbCoping'](ribs=False, bevel=0)
		check('bevel 0 -> no polyBevel3', mc.find('polyBevel3'), [])

		mc.calls = []
		g['wbCoping'](bevel=0.03)
		check('ribs keep their square ends',
			  [e for e in mc.find('polyBevel3')[0][1][0] if 'rib' in e], [])
		check('bevel runs before the ribs are united',
			  [c[0] for c in mc.calls].index('polyBevel3') <
			  [c[0] for c in mc.calls].index('polyUnite'), True)

		for bad in (-0.1, 0.5, 1.0):
			try:
				g['wbCoping'](bevel=bad)
				check('bevel %g rejected' % bad, False, True)
			except ValueError:
				check('bevel %g rejected' % bad, True, True)

		print('\n[15] the shell fills 0-1')
		#whatever the projection produced, the shell must come out spanning exactly
		#0-1 in both directions - the textures are authored to fill the square, so a
		#shell that only reaches 0.35 leaves the texture misregistered
		for bb, su, sv in ((((0.0, 0.5), (0.0, 1.0)), 2.0, 1.0),
						   (((0.2, 0.7), (0.0, 2.0)), 2.0, 0.5),
						   (((-0.4, 0.1), (0.5, 0.75)), 2.0, 4.0),
						   (((0.0, 1.0), (0.0, 1.0)), 1.0, 1.0)):
			mc.uvBB = bb
			mc.calls = []
			g['wbCoping'](ribs=False, relax=1.0)
			e = mc.find('polyEditUV')
			check('bb u %s -> scale (%g, %g)' % (bb[0], su, sv),
				  (round(e[-2][2]['scaleU'], 9), round(e[-2][2]['scaleV'], 9)), (su, sv))
			check('   then shifted to the origin',
				  (e[-1][2]['uValue'], e[-1][2]['vValue']), (-bb[0][0], -bb[1][0]))
		mc.uvBB = ((0.3, 0.3), (0.0, 1.0))
		mc.calls = []
		mc.warnings = []
		g['_wbFitUV']('flatNode')
		check('a degenerate shell warns, not divides by zero', len(mc.warnings), 1)
		check('and touches no UVs', mc.find('polyEditUV'), [])
		mc.uvBB = ((0.0, 1.0), (0.0, 1.0))

		print('\n[16] relaxing the nose UVs')
		check('flat has one nose', g['_wbCopingNoses']('flat', 25.0), [(1, 4.7927)])
		check('widening does not move it', g['_wbCopingNoses']('flat', 40.0), [(1, 4.7927)])
		#the overflow bar is rounded at BOTH ends, and its left nose sits behind
		#'back', so widening has to carry that threshold along with the points
		check('overflow has two noses', g['_wbCopingNoses']('overflow', 25.0),
			  [(1, 5.175), (-1, -17.895)])
		check('widening moves only the one behind back',
			  g['_wbCopingNoses']('overflow', 30.0), [(1, 5.175), (-1, -22.895)])
		check('channel has one nose', g['_wbCopingNoses']('channel', 25.0), [(1, 5.098)])

		#stub UVs run u = 0..0.5 against X = -18.86..6.14, so only map[18] and map[19]
		#sit at or beyond the nose at X 4.7927
		mc.calls = []
		mc.uvFlip = False
		node = g['wbCoping'](ribs=False)[0]
		rel = [c for c in mc.find('polyEditUV') if c[2].get('scaleU') == 2.0]
		check('one relax call', len(rel), 1)
		check('only the nose UVs move', rel[0][1][0],
			  [node + '.map[18]', node + '.map[19]'])
		check('U only, V untouched', rel[0][2]['scaleV'], 1.0)
		check('pivot on the inner edge of the nose block',
			  round(rel[0][2]['pivotU'], 4), round(18 / 19.0 * 0.5, 4))

		#same object with U laid out backwards: the nose is now at low u, so the pivot
		#has to flip to the other end or the relax would drag the top surface with it
		mc.calls = []
		mc.uvFlip = True
		g['wbCoping'](ribs=False)
		rel = [c for c in mc.find('polyEditUV') if c[2].get('scaleU') == 2.0]
		check('flipped U still finds the nose', len(rel[0][1][0]), 2)
		check('pivot flips to the other end',
			  round(rel[0][2]['pivotU'], 4), round((1 - 18 / 19.0) * 0.5, 4))
		mc.uvFlip = False

		mc.calls = []
		g['wbCoping'](ribs=False, relax=1.0)
		#with relax off the only UV work left is the fit: one scale, one move
		check('relax 1 -> nothing but the fit', len(mc.find('polyEditUV')), 2)

		for bad in (0.5, 0.0, 5.5):
			try:
				g['wbCoping'](relax=bad)
				check('relax %g rejected' % bad, False, True)
			except ValueError:
				check('relax %g rejected' % bad, True, True)

		print('\n[17] the hotkey binding')
		check('label reads the way the user says it',
			  g['_wbKeyLabel']('1', True, False, True), 'Shift+Alt+1')
		check('all three modifiers', g['_wbKeyLabel']('a', True, True, True), 'Shift+Ctrl+Alt+A')
		check('no modifiers', g['_wbKeyLabel']('5', False, False, False), '5')

		#a different key, and shift off - the label and the flags must follow
		mc.calls = []
		check('returns what it bound', g['wbHotkey'](key='7', sht=False), 'Alt+7')
		hk = mc.find('hotkey')[0]
		check('bound key 7', hk[1][0], '7')
		check('shift off', hk[2].get('shiftModifier'), False)

		#binding over something else should say so rather than silently stealing it
		mc.calls = []
		mc.warnings = []
		mc.hotkeyTaken = 'SomeOtherThing'
		g['wbHotkey']()
		check('warns when replacing another binding', len(mc.warnings), 1)
		check('names what it replaced', 'SomeOtherThing' in mc.warnings[0], True)
		check('still binds it', len(mc.find('hotkey')), 1)

		mc.calls = []
		mc.warnings = []
		mc.hotkeyTaken = 'weeBuildOpen'
		g['wbHotkey']()
		check('rebinding our own is not a clash', mc.warnings, [])
		mc.hotkeyTaken = ''

		#already on an editable set: leave it alone, do not force weeTools on the user
		mc.calls = []
		mc.hotkeySetCur = 'ErbaysOwnSet'
		g['wbHotkey']()
		check('keeps a set the user already chose', mc.hotkeySetCur, 'ErbaysOwnSet')
		check('and creates nothing',
			  [c for c in mc.find('hotkeySet') if c[2].get('source')], [])
		mc.hotkeySetCur = 'Maya_Default'

		print('\n[18] all three coping profiles')
		P = g['WB_COPING_PROFILES']
		check('three profiles', sorted(P), ['channel', 'flat', 'overflow'])
		#(points, measured width, measured thickness, default build size).  the overflow
		#model was exported on the same 25 x 50 footprint as the others, but the real
		#product is 33 x 66 - so its default size is NOT what it was measured at
		facts = {'flat': (27, 25.0, 2.2591, (25.0, 50.0)),
				 'overflow': (16, 25.0, 1.2, (33.0, 66.0)),
				 'channel': (42, 25.0, 1.6, (25.0, 50.0))}
		for kind, (npt, w, h, size) in sorted(facts.items()):
			pts = P[kind]['pts']
			xs = [x for x, _y in pts]
			ys = [y for _x, y in pts]
			check('%-8s %d points' % (kind, npt), len(pts), npt)
			check('%-8s %g x %g cm' % (kind, w, h),
				  (round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)), (w, h))
			check('%-8s builds %gx%g by default' % ((kind,) + size), P[kind]['size'], size)

		#the stored profiles do NOT agree on winding - which is exactly why the build
		#orients them itself rather than reversing unconditionally
		wind = {k: ('CCW' if g['_wbArea'](v['pts']) > 0 else 'CW') for k, v in P.items()}
		check('stored windings genuinely differ', len(set(wind.values())), 2)
		for kind in sorted(P):
			check('%-8s oriented CCW for the sweep' % kind,
				  g['_wbArea'](g['_wbCCW'](P[kind]['pts'])) > 0, True)
		sq = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
		check('a CCW loop is left alone', g['_wbCCW'](sq), sq)
		check('a CW loop is reversed', g['_wbCCW'](list(reversed(sq))), sq)
		check('_wbCCW never changes the point set',
			  sorted(g['_wbCCW'](P['channel']['pts'])), sorted(P['channel']['pts']))

		#the overflow bar is rounded at both ends and exactly symmetric
		ov = P['overflow']['pts']
		mirror = set((round(-12.72 - x, 4), round(y, 4)) for x, y in ov)
		check('overflow is symmetric about x = -6.36',
			  sorted(mirror) == sorted((round(x, 4), round(y, 4)) for x, y in ov), True)

		print('   widening keeps the measured shape')
		for kind, w, back, unmoved in (('channel', 30.0, -23.86, 38),
									   ('flat', 30.0, -23.86, 24),
									   ('overflow', 30.0, -23.86, 8)):
			wide = g['_wbCopingProfile'](kind, w)
			xs = [x for x, _y in wide]
			same = sum(1 for a, b in zip(wide, P[kind]['pts']) if a == b)
			check('%-8s 30cm -> back edge %g' % (kind, back), round(min(xs), 4), back)
			check('%-8s 30cm -> width 30' % kind, round(max(xs) - min(xs), 4), 30.0)
			check('%-8s 30cm -> %d points untouched' % (kind, unmoved), same, unmoved)
			check('%-8s 30cm -> nose stays at 6.14' % kind, round(max(xs), 4), 6.14)

		print('   building each one')
		for kind, npt, ribs in (('flat', 27, True), ('overflow', 16, False), ('channel', 42, False)):
			mc.calls = []
			made = g['wbCoping'](kind)
			w, l = facts[kind][3]
			check('%-8s builds' % kind,
				  made[0].startswith('coping_%s_%s_' % (kind, g['_wbSafe']('%gx%g' % (w, l), fragment=True))), True)
			check('%-8s %d point facet' % (kind, npt),
				  len(mc.find('polyCreateFacet')[0][2]['p']), npt)
			check('%-8s ribs %s by default' % (kind, ribs), bool(mc.find('polyCube')), ribs)
		mc.calls = []
		made = g['wbCoping']('channel', width=30.0)
		check('channel 30x50 name', made, ['coping_channel_30x50_01_geo'])
		check('   its facet is 30cm wide',
			  round(max(p[0] for p in mc.find('polyCreateFacet')[0][2]['p'])
					- min(p[0] for p in mc.find('polyCreateFacet')[0][2]['p']), 4), 30.0)

		#two noses -> two relax calls, one per end
		#the overflow bar defaults to 33 wide, so the stub's verts have to span that or
		#its left nose threshold falls outside them
		mc.uvXMin, mc.uvXSpan = -26.86, 33.0
		mc.calls = []
		g['wbCoping']('overflow')
		check('overflow relaxes both ends',
			  len([c for c in mc.find('polyEditUV') if c[2].get('scaleU') == 2.0]), 2)
		mc.uvXMin, mc.uvXSpan = -18.86, 25.0
		mc.calls = []
		g['wbCoping']('channel')
		check('channel relaxes one end',
			  len([c for c in mc.find('polyEditUV') if c[2].get('scaleU') == 2.0]), 1)

		print('\n[19] ribs belong to the profile, not the tick box')
		#this is the path a BUTTON takes.  the earlier checks all called wbCoping()
		#directly, where ribs defaults to None -> the profile's own flag; with the panel
		#open the tick box answers instead, and it used to win, so every profile got the
		#flat coping's ribs.  only 'flat' has them on the real product.
		g['wbUI']()
		cb = g['_wbFields']['cribs']
		want = {'flat': 8, 'overflow': 0, 'channel': 0}
		mc.checks[cb] = True
		for kind in ('flat', 'overflow', 'channel'):
			mc.calls = []
			g['_wbCopingBtn'](kind, 25.0, 50.0)
			check('button %-8s ticked   -> %d ribs' % (kind, want[kind]),
				  len(mc.find('polyCube')), want[kind])
		mc.checks[cb] = False
		for kind in ('flat', 'overflow', 'channel'):
			mc.calls = []
			g['_wbCopingBtn'](kind, 25.0, 50.0)
			check('button %-8s unticked -> 0 ribs' % kind, len(mc.find('polyCube')), 0)
		mc.checks[cb] = True

		#the tick box can subtract but never add
		for kind, forced, want_n in (('flat', True, 8), ('flat', False, 0),
									 ('channel', True, 0), ('overflow', True, 0)):
			mc.calls = []
			g['wbCoping'](kind, ribs=forced)
			check('wbCoping(%-8s ribs=%-5s) -> %d' % (kind, forced, want_n),
				  len(mc.find('polyCube')), want_n)
		check('and the profile flags still say who has them',
			  {k: v['ribs'] for k, v in sorted(g['WB_COPING_PROFILES'].items())},
			  {'channel': False, 'flat': True, 'overflow': False})

		print('\n[20] a preset button builds the size on its label')
		#the Width / Length fields used to be read through _wbNum, so a leftover 25 in
		#the box beat the preset and "Channel 30 x 50" quietly built a 25.  the fields
		#are gone; the size now comes straight off the preset, as it does for tiles.
		g['wbUI']()
		for lbl, kind, w, l in g['WB_COPINGS']:
			mc.calls = []
			made = g['_wbCopingBtn'](kind, w, l)
			xs = [q[0] for q in mc.find('polyCreateFacet')[0][2]['p']]
			check('%-18s -> %g wide' % (lbl, w), round(max(xs) - min(xs), 4), w)
			check('%-18s -> %g long' % (lbl, l),
				  mc.find('polyExtrudeFacet')[0][2]['localTranslateZ'], l)
			check('%-18s -> named for it' % lbl,
				  ('%s_%s' % (kind, g['_wbSafe']('%gx%g' % (w, l), fragment=True))) in made[0], True)
		check('the two Channel presets differ', g['WB_COPINGS'][2][2] != g['WB_COPINGS'][3][2], True)
		check('no Width / Length fields left to disagree',
			  [k for k in g['_wbFields'] if k in ('cwidth', 'clength')], [])

		#the modifier fields must still reach the build
		mc.fields[g['_wbFields']['ccount']] = '3'
		mc.calls = []
		check('Count field still applies', len(g['_wbCopingBtn']('channel', 30.0, 50.0)), 3)
		mc.fields[g['_wbFields']['ccount']] = '1'

		print('   the Custom dialog picks a profile too')
		mc.promptButton = 'OK'
		for txt, kind, w, l in (('channel 30x50', 'channel', 30.0, 50.0),
								('overflow 25x50', 'overflow', 25.0, 50.0),
								('40x60', 'flat', 40.0, 60.0)):
			mc.promptText = txt
			mc.calls = []
			made = g['wbCopingCustom']()
			xs = [q[0] for q in mc.find('polyCreateFacet')[0][2]['p']]
			check('"%s" -> %s %g wide' % (txt, kind, w), (kind in made[0], round(max(xs) - min(xs), 4)),
				  (True, w))
		for bad, why in (('bogus 30x50', 'unknown profile'), ('channel 30', 'only one number')):
			mc.promptText = bad
			try:
				g['wbCopingCustom']()
				check('"%s" rejected (%s)' % (bad, why), False, True)
			except ValueError:
				check('"%s" rejected (%s)' % (bad, why), True, True)
		mc.promptButton = ''
		mc.promptText = ''

		print('\n[21] the overflow bar at its real 33 x 66')
		#the model was exported on the same 25 x 50 footprint as the other two, but the
		#product is 33 x 66.  widening stretches the flat middle, so the thickness and
		#both R0.9650 arcs survive - scaling the whole profile by 33/25 instead would
		#give 1.584 thick and R1.2738, breaking the radius shared with the flat coping.
		base = g['WB_COPING_PROFILES']['overflow']['pts']
		wide = g['_wbCopingProfile']('overflow', 33.0)
		moved = [(a, b) for a, b in zip(base, wide) if a != b]
		check('half the points move', (len(moved), len(base) - len(moved)), (8, 8))
		check('each moves exactly -8 in X',
			  all(abs((b[0] - a[0]) + 8.0) < 1e-9 for a, b in moved), True)
		check('no Y changes at all', all(a[1] == b[1] for a, b in zip(base, wide)), True)
		check('thickness stays 1.2',
			  round(max(y for _x, y in wide) - min(y for _x, y in wide), 4), 1.2)
		check('width is exactly 33',
			  round(max(x for x, _y in wide) - min(x for x, _y in wide), 4), 33.0)
		for nm, pts in (('right', [q for q in wide if q[0] >= 5.17 and q[1] >= 0.24]),
						('left', [q for q in wide if q[0] <= -25.89 and q[1] >= 0.24])):
			_cx, _cy, r, dev = fitcirc(pts)
			check('%s arc still R0.9650' % nm, round(r, 4), 0.965)
			check('   and still an exact arc', dev < 1e-4, True)
		check('both noses move with the points',
			  g['_wbCopingNoses']('overflow', 33.0), [(1, 5.175), (-1, -25.895)])
		mc.calls = []
		made = g['wbCoping']('overflow')
		check('the default build is 33 x 66',
			  made[0].startswith('coping_overflow_33x66_'), True)
		check('   swept 66 along Z',
			  mc.find('polyExtrudeFacet')[0][2]['localTranslateZ'], 66.0)

		print('\n[22] flex grates - an assembly, not a swept profile')
		check('four presets', [g[0] for g in g['WB_GRATES']],
			  ['Flex 15 x 50', 'Flex 20 x 50', 'Flex 25 x 50', 'Flex 30 x 50'])
		#the drainage slot is held at 0.9 and the slat absorbs the rounding, so the run
		#comes out exact - the source model's 10 x 4.2 + 9 x 0.9 is 50.1, not 50
		for L, n, z in ((50.0, 10, 4.19), (25.0, 5, 4.28), (100.0, 20, 4.145)):
			gn, gz = g['_wbGrateSlats'](L)
			check('%gcm -> %d slats of %g' % (L, n, z), (gn, round(gz, 4)), (n, z))
			check('   run is exactly %g' % L,
				  round(gn * gz + (gn - 1) * g['WB_GRATE_GAP'], 6), L)
		#a column each time the span grows past another pitch
		for w, want in ((15.0, 2), (20.0, 3), (25.0, 3), (30.0, 4)):
			check('%gcm wide -> %d hardware columns' % (w, want), len(g['_wbGrateCols'](w)), want)
		#fed the source model's own width - 24.990, not a round 25 - the rule has to
		#give back the model's own layout: three columns exactly 10.0 apart
		cols = g['_wbGrateCols'](24.99)
		check('the model width reproduces the model layout',
			  [round(c, 3) for c in cols], [-10.0, 0.0, 10.0])
		check('   inset 2.495 from each end',
			  round(24.99 / 2.0 + cols[0], 3), g['WB_GRATE_INSET'])
		check('   a round 25 shifts them by only 0.005',
			  round(g['_wbGrateCols'](25.0)[0], 4), -10.005)
		check('columns stay symmetric',
			  [round(a + b, 6) for a, b in zip(g['_wbGrateCols'](30.0),
											   reversed(g['_wbGrateCols'](30.0)))], [0.0] * 4)

		print('   every preset button builds the size on its label')
		g['wbUI']()
		for lbl, w, l in g['WB_GRATES']:
			mc.calls = []
			made = g['_wbGrateBtn'](w, l)
			slats = mc.find('polyCreateFacet')
			rods = mc.find('polyCylinder')
			n, z = g['_wbGrateSlats'](l)
			check('%-14s %d slats' % (lbl, n), len(slats), n)
			sx = [q[0] for q in slats[0][2]['p']]
			check('%-14s slat %g wide' % (lbl, w), round(max(sx) - min(sx), 4), w)
			check('%-14s slat is swept, not a box' % lbl,
				  mc.find('polyExtrudeFacet')[0][2]['localTranslateZ'], z)
			check('%-14s %d rods' % (lbl, len(g['_wbGrateCols'](w))),
				  len(rods), len(g['_wbGrateCols'](w)))
			check('%-14s rods run the full length' % lbl, rods[0][2]['h'], l)
			check('%-14s named for its size' % lbl,
				  made[0].startswith('grate_flex_%s_' % g['_wbSafe']('%gx%g' % (w, l), fragment=True)), True)
			#the slats must fill the run exactly, centred on the origin
			#the sweep starts at the move position and runs +Z, so the run is
			#first move .. last move + one slat
			zs = sorted(c[1][2] for c in mc.find('move')[:n])
			check('%-14s slats span exactly %g' % (lbl, l),
				  round((zs[-1] + z) - zs[0], 6), l)
			check('%-14s run is centred on Z' % lbl,
				  round(zs[0] + zs[-1] + z, 6), 0.0)

		check('slat ends are chamfered', bool(mc.find('polyBevel3')), True)
		mc.calls = []
		g['wbGrate'](30.0, 50.0, bevel=0)
		check('bevel 0 -> no polyBevel3', mc.find('polyBevel3'), [])
		for kw, why in (({'count': 0}, 'zero count'), ({'width': 0}, 'zero width'),
						({'length': 0}, 'zero length'), ({'bevel': 5.0}, 'bevel past half the slat')):
			try:
				g['wbGrate'](**kw)
				check('%s rejected' % why, False, True)
			except ValueError:
				check('%s rejected' % why, True, True)

		print('\n[23] the slat cross-section - measured, not a box')
		#sliced out of the source model: a cambered top, draughted sides, arc corners
		#and two underside channels.  the earlier build used a bevelled cube, which is
		#what "grates look terrible" was about.
		for w in (15.0, 20.0, 25.0, 30.0):
			pr = g['_wbSlatProfile'](w)
			xs = [q[0] for q in pr]
			check('%gcm profile spans exactly %g' % (w, w), round(max(xs) - min(xs), 6), w)
			check('   it is a real section, not 4 corners', len(pr) > 40, True)
		#the edge detail is fixed: identical at both edges and unchanged by width
		for w in (15.0, 30.0):
			pr = g['_wbSlatProfile'](w)
			half = w / 2.0
			left = [(round(q[0] + half, 4), q[1]) for q in pr[:len(g['WB_SLAT_END'])]]
			check('%gcm left edge is the measured detail' % w,
				  left, [(round(dx, 4), y) for dx, y in g['WB_SLAT_END']])
		pr = g['_wbSlatProfile'](25.0)
		mirrored = sorted((round(-x, 3), round(y, 4)) for x, y in pr)
		check('the section is symmetric',
			  mirrored == sorted((round(x, 3), round(y, 4)) for x, y in pr), True)
		#the top really is an arc of the measured radius
		top = [q for q in pr if q[1] >= g['WB_SLAT_TOP'] - 1e-9]
		_cx, _cy, r, dev = fitcirc(top)
		check('top is a %g camber' % g['WB_SLAT_CAMBER'], round(r, 1), 137.8)
		check('   and a true arc', dev < 1e-6, True)
		check('   crowned upward', round(_cy, 1) < 0, True)
		#the measured slat is 24.99 wide and 2.5158 tall; reproduce that
		m = g['_wbSlatProfile'](24.99)
		check('at the model width the top matches to 0.005',
			  abs(max(q[1] for q in m) - 2.5158) < 0.006, True)
		check('   and the underside matches exactly',
			  round(min(q[1] for q in m), 4), g['WB_SLAT_BOT'])
		#the sides lean in, they are not vertical
		lo = min(pr, key=lambda q: q[1] if q[0] < 0 else 99)
		check('the side draughts inward',
			  round(g['WB_SLAT_END'][-1][0] - g['WB_SLAT_END'][2][0], 4) > 0.5, True)
		#two underside channels, dropped when a slat gets too narrow for them
		u = g['_wbSlatUnder'](12.495)
		check('underside is monotonic in X',
			  all(u[i][0] > u[i + 1][0] for i in range(len(u) - 1)), True)
		check('   with two channels', sum(1 for q in u if abs(q[1] - (g['WB_SLAT_BOT'] + g['WB_SLAT_CH_D'])) < 1e-9), 4)
		for bad, why in ((1.0, 'narrower than its own edge detail'), (400.0, 'wider than the camber radius')):
			try:
				g['_wbSlatProfile'](bad)
				check('%g rejected (%s)' % (bad, why), False, True)
			except ValueError:
				check('%g rejected (%s)' % (bad, why), True, True)

	finally:
		shutil.rmtree(tmp, ignore_errors=True)

	print('\n%s\n' % ('ALL CHECKS PASSED' if not FAIL[0] else '%d CHECK(S) FAILED' % FAIL[0]))
	return 1 if FAIL[0] else 0


if __name__ == '__main__':
	sys.exit(main())
