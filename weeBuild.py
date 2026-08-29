#weeBuild - a weeScript style button panel for building / importing the pool
#elements: tiles, grates and copings.
#
#It lives in the weeTiles repo but shares no code with weeTiles.py or with
#weeScript - every global here is prefixed wb/_wb/WB_ so all three tools can
#sit in Maya's __main__ namespace together without clobbering each other.
#
#Load into Maya (Python script editor):
#	import urllib.request, __main__
#	exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeBuild.py').read().decode('utf-8'), __main__.__dict__)
#
#Alt+3 re-pulls this file from that address and reopens the panel.
#(weeTiles takes Alt+2, so weeBuild takes Alt+3.)

import os
import re

import maya.cmds as mc
import maya.mel as mel

WB_VERSION = '1.0'
WB_UI = 'weeBuild'
WB_SELF_URL = 'https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeBuild.py'
WB_OPT_SET = 'weeBuildSettings'
WB_WIDTH = 230

#tile presets in panel order: (label, short cm, long cm).  the long edge goes
#along X, the short one along Z - same convention as weeScript's buildTiles.
WB_TILES = [
	('33 x 66', 33.0, 66.0),
	('33 x 33', 33.0, 33.0),
	('16.5 x 66', 16.5, 66.0),
	('16.5 x 16.5', 16.5, 16.5),
	('11 x 33', 11.0, 33.0),
	('10 x 10', 10.0, 10.0),
	('5 x 5', 5.0, 5.0),
	('12.5 x 25', 12.5, 25.0),
]
WB_THICK = 0.76      #tile thickness (Y) in cm
WB_GROUT = 0.15      #chamfer per top edge -> a 0.3cm grout valley between two tiles
WB_SPACE = 5.0       #gap between tiles when several are built at once

#model sections: (settings key, panel label).  drop model files into a section's
#folder and hit Refresh - one button appears per file, no code change needed.
WB_SECTIONS = [('grates', 'Grates'), ('copings', 'Copings')]
WB_EXT = ('.ma', '.mb', '.fbx', '.obj')
WB_FTYPE = {'.ma': 'mayaAscii', '.mb': 'mayaBinary', '.fbx': 'FBX', '.obj': 'OBJ'}

WB_COL = {
	'gray':   [0.29, 0.29, 0.28],
	'coral':  [0.40, 0.24, 0.21],
	'purple': [0.31, 0.26, 0.42],
	'amber':  [0.42, 0.34, 0.16],
	'blue':   [0.18, 0.27, 0.42],
	'teal':   [0.13, 0.34, 0.29],
	'indigo': [0.25, 0.25, 0.46],
}

_wbFields = {}   #field key -> textField, filled in by wbUI()
_wbCols = {}     #section key -> the columnLayout holding that section's buttons


##############################################################################
#  settings
##############################################################################

def _wbGetSettings():
	import json
	if mc.optionVar(exists=WB_OPT_SET):
		try:
			return json.loads(mc.optionVar(q=WB_OPT_SET) or '{}')
		except Exception:
			pass
	return {}
def _wbSaveSettings(d):
	import json
	mc.optionVar(sv=(WB_OPT_SET, json.dumps(d)))
def _wbFolder(kind):
	#the model folder remembered for one section (forward slashes, no trailing /)
	p = (_wbGetSettings().get(kind) or '').strip().replace('\\', '/')
	return p.rstrip('/') if len(p) > 1 else p
def _wbSetFolder(kind, path):
	s = _wbGetSettings()
	s[kind] = (path or '').strip().replace('\\', '/').rstrip('/')
	_wbSaveSettings(s)


##############################################################################
#  helpers
##############################################################################

def _wbGuard(fn, *a, **kw):
	#run a button command, turning a bad selection / bad number into a friendly
	#warning instead of a raw traceback in the script editor
	try:
		return fn(*a, **kw)
	except Exception as e:
		mc.warning('weeBuild: %s' % e)
def _wbSafe(name, fragment=False):
	#Maya node names take letters, digits and _ only, and a dot would be read as
	#an attribute separator - so a decimal point becomes p (16.5 -> 16p5) and any
	#other stray character becomes _.  weeScript never hit this: all of its
	#presets were whole numbers.  a fragment sits inside a longer name, so it is
	#allowed to start with a digit.
	n = re.sub(r'(?<=\d)\.(?=\d)', 'p', str(name))
	n = re.sub(r'[^0-9A-Za-z_]', '_', n)
	n = re.sub(r'_+', '_', n).strip('_')
	if not n:
		return '' if fragment else 'wbNode'
	if n[0].isdigit() and not fragment:
		n = '_' + n
	return n
def _wbToken(short, long_):
	#'16p5x66' for a 16.5 x 66 tile
	return _wbSafe('%gx%g' % (short, long_), fragment=True) or 'tile'
def _wbUnique(pattern):
	#pattern holds one %02d - return it filled with the lowest free number
	i = 1
	while mc.objExists(pattern % i):
		i += 1
	return pattern % i
def _wbBottomPivot(node):
	#pivot to bottom centre, same as weeScript's bPiv
	bb = mc.xform(node, q=True, ws=True, bb=True)
	mc.xform(node, ws=True, piv=((bb[0] + bb[3]) / 2.0, bb[1], (bb[2] + bb[5]) / 2.0))
	return bb
def _wbWrap(text, width=12):
	#split a model name over two button lines so it stays readable at 230px
	t = str(text).replace('_', ' ').strip()
	if len(t) <= width:
		return t
	cut = t.rfind(' ', 0, width + 1)
	if cut < 1:
		cut = width
	return t[:cut].strip() + '\n' + t[cut:].strip()
def _wbNum(key, default, integer=False):
	#read one of the panel's number fields, falling back to the default when the
	#panel is closed or the field is empty
	f = _wbFields.get(key)
	txt = ''
	if f and mc.textField(f, q=True, exists=True):
		txt = (mc.textField(f, q=True, text=True) or '').strip()
	if not txt:
		return default
	try:
		v = float(txt)
	except ValueError:
		raise ValueError('"%s" is not a number (%s field).' % (txt, key))
	return int(round(v)) if integer else v


##############################################################################
#  tiles - the geometry recipe is weeScript's _buildTile, unchanged
##############################################################################

def _wbFaceCenterY(f):
	#average world Y of a face's verts, used to pick the top / bottom face
	verts = mc.ls(mc.polyListComponentConversion(f, ff=True, tv=True), flatten=True)
	ys = [mc.pointPosition(v, world=True)[1] for v in verts]
	return sum(ys) / len(ys)
def _wbBuildTile(x, z, name, offset_x, thick=WB_THICK, grout=WB_GROUT):
	#one master tile: box -> chamfer the four top edges (that chamfer is half the
	#grout valley) -> delete the hidden bottom face -> planar-Y UVs rotated 90
	#-> pivot down to bottom centre.  returns the transform name.
	cube = mc.polyCube(w=x, h=thick, d=z, name=name)[0]
	if grout > 0:
		faces = mc.ls(cube + '.f[*]', flatten=True)
		top_face = max(faces, key=_wbFaceCenterY)
		top_edges = mc.ls(mc.polyListComponentConversion(top_face, ff=True, te=True), flatten=True)
		mc.polyBevel3(top_edges, offset=grout, offsetAsFraction=False, segments=1, depth=1, worldSpace=True, autoFit=True, mergeVertices=True, smoothingAngle=30)
		mc.delete(cube, constructionHistory=True)
	#the bottom face sits against the floor - dropping it saves tessellation
	faces = mc.ls(cube + '.f[*]', flatten=True)
	mc.delete(min(faces, key=_wbFaceCenterY))
	tf = mc.polyListComponentConversion(cube, tf=True)
	mc.polyProjection(tf, type='Planar', md='y')
	#rotate the UVs 90 so the texture runs along the tile's long edge
	bb2 = mc.polyEvaluate(cube, boundingBox2d=True)
	mc.polyEditUV(mc.polyListComponentConversion(cube, tuv=True), pivotU=(bb2[0][0] + bb2[0][1]) / 2.0, pivotV=(bb2[1][0] + bb2[1][1]) / 2.0, angle=90)
	mc.delete(cube, constructionHistory=True)
	mc.move(offset_x, 0, 0, cube)
	_wbBottomPivot(cube)
	return cube
def wbTile(short, long_, count=1, thick=WB_THICK, grout=WB_GROUT, spacing=WB_SPACE):
	#build 'count' master tiles of (short x long) cm in a row along X
	short, long_ = float(short), float(long_)
	x, z = long_, short
	count = int(count)
	thick, grout = float(thick), float(grout)
	if x <= 0 or z <= 0:
		raise ValueError('tile size must be greater than 0.')
	if count < 1:
		raise ValueError('need at least 1 tile.')
	if thick <= 0:
		raise ValueError('thickness must be greater than 0.')
	if grout < 0 or grout * 2.0 >= min(x, z):
		raise ValueError('grout must be between 0 and half the short edge.')
	token = _wbToken(short, long_)
	made = []
	for i in range(count):
		nm = _wbUnique('tile_' + token + '_%02d_geo')
		made.append(_wbBuildTile(x, z, nm, i * (x + spacing), thick, grout))
	mc.select(made)
	print('weeBuild: built %d tile(s) at %g x %gcm: %s' % (count, short, long_, ', '.join(made)))
	return made
def _wbTileBtn(short, long_):
	#a preset button: take count / thickness / grout from the panel fields
	return wbTile(short, long_, count=_wbNum('count', 1, integer=True),
				  thick=_wbNum('thick', WB_THICK), grout=_wbNum('grout', WB_GROUT))
def wbTileCustom():
	#any other size, typed in
	r = mc.promptDialog(title='Custom tile', message='Short x Long in cm (e.g. 20x40):', text='20x40', button=['OK', 'Cancel'], defaultButton='OK', cancelButton='Cancel', dismissString='Cancel')
	if r != 'OK':
		return []
	nums = re.findall(r'[\d.]+', mc.promptDialog(q=True, text=True) or '')
	if len(nums) < 2:
		raise ValueError('enter two numbers, e.g. 20x40.')
	return _wbTileBtn(float(nums[0]), float(nums[1]))


##############################################################################
#  models - grates, copings, and whatever gets added to WB_SECTIONS later
##############################################################################

def _wbModelFiles(kind):
	#every model file in that section's folder, sorted, full forward-slash paths
	d = _wbFolder(kind)
	if not d or not os.path.isdir(d):
		return []
	out = []
	for f in sorted(os.listdir(d), key=lambda s: s.lower()):
		p = os.path.join(d, f)
		if os.path.splitext(f)[1].lower() in WB_EXT and os.path.isfile(p):
			out.append(p.replace('\\', '/'))
	return out
def wbImport(path):
	#import one model file, keep the roots that carry a mesh, rename them
	#<file>_geo and drop their pivots to bottom centre.  returns those roots.
	path = (path or '').replace('\\', '/')
	if not os.path.isfile(path):
		raise ValueError('no such file: %s' % path)
	ext = os.path.splitext(path)[1].lower()
	if ext == '.fbx':
		mc.loadPlugin('fbxmaya', quiet=True)
	elif ext == '.obj':
		mc.loadPlugin('objExport', quiet=True)
	kw = {'ignoreVersion': True, 'options': 'v=0;'}
	if WB_FTYPE.get(ext):
		kw['type'] = WB_FTYPE[ext]
	before = set(mc.ls(assemblies=True))
	mc.file(path, i=True, mergeNamespacesOnClash=True, namespace=':', preserveReferences=True, **kw)
	new = [n for n in mc.ls(assemblies=True) if n not in before]
	new = [n for n in new if mc.listRelatives(n, allDescendents=True, type='mesh') or mc.listRelatives(n, shapes=True, type='mesh')]
	if not new:
		mc.warning('weeBuild: %s imported but produced no mesh.' % os.path.basename(path))
		return []
	stem = _wbSafe(os.path.splitext(os.path.basename(path))[0])
	if stem.endswith('_geo'):
		stem = stem[:-4]
	out = []
	for n in new:
		nm = stem + '_geo'
		if mc.objExists(nm):
			nm = _wbUnique(stem + '_%02d_geo')
		try:
			n = mc.rename(n, nm)
		except Exception:
			pass
		_wbBottomPivot(n)
		out.append(n)
	mc.select(out)
	print('weeBuild: imported %s -> %s' % (os.path.basename(path), ', '.join(out)))
	return out
def wbSetFolder(kind, path=None):
	#point a section at its model folder.  no path -> browse for one.
	if path is None:
		kw = {'fileMode': 3, 'caption': 'weeBuild: %s model folder' % kind, 'okCaption': 'Use folder'}
		start = _wbFolder(kind)
		if start and os.path.isdir(start):
			kw['dir'] = start
		r = mc.fileDialog2(**kw)
		if not r:
			return
		path = r[0]
	_wbSetFolder(kind, path)
	f = _wbFields.get(kind + 'Dir')
	if f and mc.textField(f, q=True, exists=True):
		mc.textField(f, e=True, text=_wbFolder(kind))
	_wbFillModels(kind)
def wbRefresh(kind=None):
	#re-scan the model folder(s) and rebuild the buttons
	for k in ([kind] if kind else [s[0] for s in WB_SECTIONS]):
		_wbFillModels(k)


##############################################################################
#  UI
##############################################################################

def _wbRow(parent, items):
	#a row of equal width buttons.  items: (label, callable, colour[, tooltip])
	n = len(items)
	if not n:
		return None
	h = 34 if any('\n' in it[0] for it in items) else 26
	fl = mc.formLayout(parent=parent, numberOfDivisions=100, height=h + 2)
	bs = []
	for it in items:
		label, fn, c = it[0], it[1], it[2]
		kw = {'annotation': it[3]} if len(it) > 3 else {}
		bs.append(mc.button(parent=fl, label=label, height=h, bgc=WB_COL[c],
							command=(lambda *a, _f=fn: _wbGuard(_f)), **kw))
	att, form = [], []
	for i, b in enumerate(bs):
		lp = int(round(i * 100.0 / n))
		rp = int(round((i + 1) * 100.0 / n))
		att += [(b, 'left', 1, lp), (b, 'right', 1, rp)]
		form += [(b, 'top', 1), (b, 'bottom', 1)]
	mc.formLayout(fl, e=True, attachPosition=att, attachForm=form)
	return fl
def _wbNums(parent, specs):
	#a row of label + number field pairs.  specs: (key, label, default text)
	n = len(specs)
	fl = mc.formLayout(parent=parent, numberOfDivisions=100, height=24)
	att, form = [], []
	for i, (key, label, default) in enumerate(specs):
		lp = int(round(i * 100.0 / n))
		rp = int(round((i + 1) * 100.0 / n))
		mid = lp + int(round((rp - lp) * 0.46))
		t = mc.text(parent=fl, label=label, align='right', font='smallPlainLabelFont')
		f = mc.textField(parent=fl, text=default)
		_wbFields[key] = f
		att += [(t, 'left', 2, lp), (t, 'right', 3, mid), (f, 'left', 0, mid), (f, 'right', 3, rp)]
		form += [(t, 'top', 4), (t, 'bottom', 2), (f, 'top', 1), (f, 'bottom', 1)]
	mc.formLayout(fl, e=True, attachPosition=att, attachForm=form)
	return fl
def _wbLabel(parent, text):
	return mc.text(parent=parent, label=text, height=16, align='left', font='smallObliqueLabelFont')
def _wbFolderRow(parent, kind):
	#[ folder path ][ ... ][ Refresh ]
	fl = mc.formLayout(parent=parent, numberOfDivisions=100, height=26)
	t = mc.textField(parent=fl, text=_wbFolder(kind), annotation='folder holding the %s model files' % kind,
					 changeCommand=(lambda *a, _k=kind: _wbGuard(wbSetFolder, _k, a[0] if a else '')))
	b = mc.button(parent=fl, label='...', height=22, bgc=WB_COL['gray'], annotation='browse for the %s folder' % kind,
				  command=(lambda *a, _k=kind: _wbGuard(wbSetFolder, _k)))
	r = mc.button(parent=fl, label='Refresh', height=22, bgc=WB_COL['gray'], annotation='re-scan the folder for new model files',
				  command=(lambda *a, _k=kind: _wbGuard(wbRefresh, _k)))
	_wbFields[kind + 'Dir'] = t
	mc.formLayout(fl, e=True,
		attachPosition=[(t, 'left', 2, 0), (t, 'right', 2, 62), (b, 'left', 0, 62), (b, 'right', 2, 74), (r, 'left', 0, 74), (r, 'right', 2, 100)],
		attachForm=[(t, 'top', 2), (t, 'bottom', 2), (b, 'top', 2), (b, 'bottom', 2), (r, 'top', 2), (r, 'bottom', 2)])
	return fl
def _wbFillModels(kind):
	#(re)build one section's model buttons from what is in its folder right now
	c = _wbCols.get(kind)
	if not c or not mc.columnLayout(c, q=True, exists=True):
		return
	for k in (mc.layout(c, q=True, childArray=True) or []):
		mc.deleteUI(c + '|' + k)
	d = _wbFolder(kind)
	if not d:
		_wbLabel(c, '  no folder set - pick one with ...')
		return
	if not os.path.isdir(d):
		_wbLabel(c, '  folder not found')
		return
	files = _wbModelFiles(kind)
	if not files:
		_wbLabel(c, '  no %s files here yet' % ' / '.join(e[1:] for e in WB_EXT))
		return
	items = []
	for p in files:
		stem = os.path.splitext(os.path.basename(p))[0]
		items.append((_wbWrap(stem), (lambda _p=p: wbImport(_p)), 'blue', p))
	for i in range(0, len(items), 3):
		_wbRow(c, items[i:i + 3])
def wbUI():
	#built by the workspaceControl's uiScript, and again whenever Maya restores it
	global _wbFields, _wbCols
	_wbFields = {}
	_wbCols = {}
	main = mc.columnLayout(adjustableColumn=True, rowSpacing=1, width=WB_WIDTH)

	f = mc.frameLayout(parent=main, label='  Tiles', collapsable=True, collapse=False, marginHeight=2, backgroundColor=[0.2, 0.2, 0.2])
	_wbNums(f, [('count', 'Count', '1'), ('thick', 'Thick', '%g' % WB_THICK), ('grout', 'Grout', '%g' % WB_GROUT)])
	for i in range(0, len(WB_TILES), 4):
		_wbRow(f, [(lbl.replace(' x ', '\nx '), (lambda _s=s, _l=l: _wbTileBtn(_s, _l)), 'gray',
					'build a %g x %gcm tile' % (s, l)) for lbl, s, l in WB_TILES[i:i + 4]])
	_wbRow(f, [('Custom size...', wbTileCustom, 'amber', 'build any other short x long size')])

	for key, label in WB_SECTIONS:
		f = mc.frameLayout(parent=main, label='  ' + label, collapsable=True, collapse=False, marginHeight=2, backgroundColor=[0.2, 0.2, 0.2])
		_wbFolderRow(f, key)
		_wbCols[key] = mc.columnLayout(parent=f, adjustableColumn=True, rowSpacing=1)
		_wbFillModels(key)
	return main


##############################################################################
#  entry point
##############################################################################

def weeBuild():
	#open (or re-open) the panel
	if mc.workspaceControl(WB_UI, q=True, exists=True):
		mc.deleteUI(WB_UI, control=True)
	if mc.window(WB_UI, exists=True):
		mc.deleteUI(WB_UI)
	mc.workspaceControl(WB_UI, retain=True, floating=True, label='weeBuild', uiScript='wbUI()',
						initialWidth=WB_WIDTH, initialHeight=560)
	mc.workspaceControl(WB_UI, e=True, resizeWidth=WB_WIDTH)
	return WB_UI
def _wbRegisterHotkey(key='3', alt=True, ctl=False):
	#Alt+3 re-pulls this file from GitHub and reopens the panel
	cmd = ("import urllib.request, __main__\n"
		   "exec(urllib.request.urlopen('%s?t='+str(__import__('time').time())).read().decode('utf-8'), __main__.__dict__)" % WB_SELF_URL)
	nc = mc.nameCommand('weeBuildReload', annotation='weeBuild: reload from GitHub',
						command='python("%s")' % cmd.replace('\n', r'\n').replace('"', r'\"'), sourceType='python')
	mc.hotkey(k=key, alt=alt, ctl=ctl, name=nc)


weeBuild()
try:
	_wbRegisterHotkey()
except Exception as _wbE:
	mc.warning('weeBuild: could not register the Alt+3 hotkey - %s' % _wbE)
