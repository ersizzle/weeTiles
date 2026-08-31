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
#Shift+Alt+1 opens the panel.  Alt+1/2/3 are already taken in the user's Maya, so
#those are deliberately left alone.

import os
import re

import maya.cmds as mc
import maya.mel as mel

WB_VERSION = '1.0'
WB_UI = 'weeBuild'
WB_SELF_URL = 'https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeBuild.py'
WB_OPT_SET = 'weeBuildSettings'
WB_HOTKEY_SET = 'weeTools'    #Maya_Default is read only, so hotkeys go in here
WB_NAME_CMD = 'weeBuildOpen'
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

#coping presets in panel order: (label, profile key, width cm, length cm).
WB_COPINGS = [
	('Flat 25 x 50', 'flat', 25.0, 50.0),
	('Overflow 25 x 50', 'overflow', 25.0, 50.0),
	('Channel 25 x 50', 'channel', 25.0, 50.0),
	('Channel 30 x 50', 'channel', 30.0, 50.0),
]
#each profile is the real swept cross-section measured off the model in
#tile_models/copings, plus the few facts the build needs about it:
#  pts   (X, Y) points of the loop, in cm, in whatever order they were traced -
#        _wbCCW orients it, so the stored winding does not matter
#  back  points at or behind this X move when the width changes; everything in
#        front keeps the shape it was measured at
#  noses (side, X) ends that a top projection squashes, for _wbRelaxUV.  side 1
#        means X >= that value, -1 means X <= it
#  ribs  whether this profile has the underside ribs
#  size  the (width, length) it was measured at
WB_COPING_PROFILES = {
	#the pool coping measured off flat_coping_natural.gltf.  bullnose is an exact
	#R0.9651 arc and the grip undercut R~1.035 - do not round these decimals off.
	#the top is not flat: 1.56 at the back edge rising to 2.2191 at the nose.
	#the only profile with underside ribs.
	'flat': {
		'pts': [
			(5.1198, 0.0122), (5.0684, 0.263), (5.0147, 0.4942),
			(4.8965, 0.7195), (4.716, 0.9121), (4.49, 1.0486),
			(4.2451, 1.1175), (4.0078, 1.1219), (-0.4046, 0.8465),
			(-1.2334, 0.7948), (-6.3987, 0.5783), (-7.2281, 0.5435),
			(-12.36, 0.4735), (-13.1449, 0.4628), (-18.86, 0.4628),
			(-18.86, 1.56), (-12.36, 1.56), (-6.4432, 1.6408),
			(-0.4485, 1.892), (4.7927, 2.2191), (5.03, 2.2147),
			(5.2749, 2.1458), (5.5009, 2.0093), (5.6814, 1.8167),
			(5.7997, 1.5914), (5.8533, 1.3603), (6.14, -0.04),
		],
		'back': -13.0,
		'noses': [(1, 4.7927)],
		'ribs': True,
		'minw': 20.0,
		'size': (25.0, 50.0),
	},
	#linear_overflow_coping_natural: a 25 x 1.20 bar with BOTH top corners rounded,
	#exactly symmetric about x = -6.36.  both arcs are exact quarter circles of
	#R0.9650 - the same tooling radius as the flat coping's bullnose.  two noses,
	#so the UV relax has to widen each end.
	'overflow': {
		'pts': [
			(-18.86, 0.01), (6.14, 0.01), (6.14, 0.245),
			(6.1108, 0.4805), (6.0167, 0.7169), (5.8574, 0.9274),
			(5.6469, 1.0867), (5.4105, 1.1808), (5.175, 1.21),
			(-17.895, 1.21), (-18.1305, 1.1808), (-18.3669, 1.0867),
			(-18.5774, 0.9274), (-18.7367, 0.7169), (-18.8308, 0.4805),
			(-18.86, 0.245),
		],
		'back': -6.36,
		'noses': [(1, 5.175), (-1, -17.895)],
		'ribs': False,
		'minw': 8.0,
		'size': (25.0, 50.0),
	},
	#coping_natural: 25 x 1.60, with a channel 4.03 wide at the top narrowing to
	#1.97 at the floor, 0.75 deep, S-curve walls symmetric about x = 0.44.  unlike
	#the other two its curves are NOT exact circles (the bullnose fits R0.99 to only
	#6e-03), so it was not generated from a clean radius.
	'channel': {
		'pts': [
			(-18.86, 0.037), (-18.86, 1.483), (-18.783, 1.56),
			(-1.576, 1.56), (-1.4251, 1.5383), (-1.2625, 1.4906),
			(-1.1497, 1.4024), (-1.0989, 1.3155), (-1.06, 1.249),
			(-1.0405, 1.1745), (-1.0234, 1.1088), (-0.9495, 0.9799),
			(-0.8901, 0.9205), (-0.7612, 0.8466), (-0.6955, 0.8295),
			(-0.544, 0.81), (1.424, 0.81), (1.5755, 0.8295),
			(1.6412, 0.8466), (1.7701, 0.9205), (1.8295, 0.9799),
			(1.9034, 1.1088), (1.9205, 1.1745), (1.94, 1.249),
			(1.9789, 1.3155), (2.0297, 1.4024), (2.1425, 1.4906),
			(2.3051, 1.5383), (2.456, 1.56), (5.098, 1.26),
			(5.2506, 1.2456), (5.4546, 1.2067), (5.5946, 1.15),
			(5.793, 1.0196), (5.8996, 0.913), (6.03, 0.7146),
			(6.0867, 0.5746), (6.1256, 0.3706), (6.14, 0.218),
			(6.14, 0.037), (6.063, -0.04), (-18.783, -0.04),
		],
		'back': -2.0,
		'noses': [(1, 5.098)],
		'ribs': False,
		'minw': 10.0,
		'size': (25.0, 50.0),
	},
}
WB_COPING_W = 25.0     #fallback width / length when a profile has no size
WB_COPING_L = 50.0
WB_RIB_W = 1.0         #underside rib: 1.0 wide, 1.3 tall, 3.0 pitch, full length
WB_RIB_H = 1.3
WB_RIB_Y0 = -0.036     #rib underside, level with the nose at -0.04
WB_RIB_PITCH = 3.0
WB_RIB_INSET = 0.04    #first rib sits this far in from the back edge
WB_RIB_LIMIT = 3.18    #ribs stop here, short of the nose
#chamfer on the two end cap perimeters, as a FRACTION of the shortest adjacent edge -
#matches the polyBevel3 the user dialled in by hand: Fraction 0.03, 1 segment, chamfer on
WB_COPING_BEVEL = 0.03
#a top projection squashes the bullnose (2.18x) and the front face (4.99x), because
#from above they are nearly edge on.  this widens just those UVs in U, never in V, so
#the nose gets a bigger share of the square.  1.0 = leave it alone (a plain top
#projection), 2.18 gives the bullnose the share it would have if it were laid flat.
WB_COPING_RELAX = 2.0

#model sections: (settings key, panel label).  drop model files into a section's
#folder and hit Refresh - one button appears per file, no code change needed.
WB_SECTIONS = [('grates', 'Grates'), ('copings', 'Coping models')]
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
def _wbFlag(key, default):
	#read one of the panel's checkboxes, falling back to the default when the
	#panel is closed
	c = _wbFields.get(key)
	if c and mc.checkBox(c, q=True, exists=True):
		return bool(mc.checkBox(c, q=True, value=True))
	return default


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
#  copings - a measured profile swept along Z, with the underside ribs merged in
##############################################################################

def _wbCopingSpec(kind):
	s = WB_COPING_PROFILES.get(kind)
	if not s:
		raise ValueError('unknown coping profile "%s" - have %s.'
						 % (kind, ', '.join(sorted(WB_COPING_PROFILES))))
	return s
def _wbArea(profile):
	#signed area of the closed loop; the sign is its winding
	n = len(profile)
	return sum(profile[i][0] * profile[(i + 1) % n][1] - profile[(i + 1) % n][0] * profile[i][1]
			   for i in range(n)) / 2.0
def _wbCCW(profile):
	#polyCreateFacet takes the face normal from the winding and the sweep runs +Z, so
	#the loop must go counter clockwise or the walls come out facing inward.  which way
	#a stored profile runs depends on how it was traced out of the source file, so this
	#measures rather than assumes - the three stored profiles do not agree.
	return list(profile) if _wbArea(profile) > 0 else list(reversed(profile))
def _wbCopingShift(spec, width):
	#how far the back edge has to move to reach 'width'
	xs = [x for x, _y in spec['pts']]
	return float(width) - (max(xs) - min(xs))
def _wbCopingProfile(kind, width):
	#the stored profile stretched to 'width'.  only the flat run behind spec['back']
	#moves: every nose, lip, channel and undercut keeps the shape it was measured at,
	#which is the whole point of rebuilding these procedurally.
	spec = _wbCopingSpec(kind)
	width = float(width)
	if width < spec['minw']:
		raise ValueError('%s coping width must be at least %gcm.' % (kind, spec['minw']))
	dx = _wbCopingShift(spec, width)
	back = spec['back']
	return [((x - dx) if x <= back else x, y) for x, y in spec['pts']]
def _wbCopingNoses(kind, width):
	#the nose thresholds, moved by the same rule as the points - otherwise widening a
	#profile whose nose sits behind 'back' (the overflow bar's left bullnose) would
	#leave the threshold behind and relax the wrong part of the shell
	spec = _wbCopingSpec(kind)
	dx = _wbCopingShift(spec, float(width))
	back = spec['back']
	return [(side, (x - dx) if x <= back else x) for side, x in spec['noses']]
def _wbCopingRibs(profile):
	#rib centres in X.  they start just inside the back edge and march forward on
	#a fixed pitch, stopping short of the nose - the source model has 8 of them
	#across 25cm and a wider coping simply gets more.
	start = min(x for x, _ in profile) + WB_RIB_INSET
	n = int((WB_RIB_LIMIT - WB_RIB_W - start) / WB_RIB_PITCH) + 1
	return [start + WB_RIB_W / 2.0 + i * WB_RIB_PITCH for i in range(max(n, 0))]
def _wbCapEdges(node, length, tol=1e-4):
	#the edges bounding the two end caps: both of an edge's verts sit at the same
	#end of the sweep, while every wall edge runs along Z from one end to the other
	out = []
	for e in mc.ls(node + '.e[*]', flatten=True):
		zs = [mc.pointPosition(v, world=True)[2]
			  for v in mc.ls(mc.polyListComponentConversion(e, fe=True, tv=True), flatten=True)]
		if not zs or max(zs) - min(zs) >= tol:
			continue
		if abs(min(zs)) < tol or abs(min(zs) - length) < tol:
			out.append(e)
	return out
def _wbRelaxUV(node, noses, factor):
	#widen the squashed ends in U only.  each nose is scaled about whichever end of its
	#own block faces the rest of the shell, so the middle never moves and the shell only
	#grows outward - which also makes this independent of which way round Maya laid U
	#out.  only ends can be treated this way: growing an interior run (the channel
	#profile's walls) would need everything beyond it shifted too, so those are left.
	if factor == 1.0 or not noses:
		return []
	uvs = mc.ls(node + '.map[*]', flatten=True)
	if not uvs:
		return []
	#one pass pairing every UV with the X of the vertex it belongs to
	info = []
	for uv in uvs:
		u = mc.polyEditUV(uv, q=True)[0]
		vtx = mc.ls(mc.polyListComponentConversion(uv, fuv=True, tv=True), flatten=True)
		info.append((uv, u, mc.pointPosition(vtx[0], world=True)[0] if vtx else None))
	allu = [u for _uv, u, _x in info]
	centre = (min(allu) + max(allu)) / 2.0
	moved = []
	for side, xth in noses:
		sel = [(uv, u) for uv, u, x in info if x is not None
			   and (x >= xth - 1e-4 if side > 0 else x <= xth + 1e-4)]
		if not sel:
			continue
		us = [u for _uv, u in sel]
		lo, hi = min(us), max(us)
		pivot = lo if abs(lo - centre) < abs(hi - centre) else hi
		mc.polyEditUV([uv for uv, _u in sel], pivotU=pivot, pivotV=0.0,
					  scaleU=factor, scaleV=1.0)
		moved.append([uv for uv, _u in sel])
	return moved
def _wbFitUV(node):
	#stretch the shell to fill 0-1 in BOTH directions.  the textures are authored to
	#fill the square, so the shell has to fill it too - keeping real world width to
	#length proportions would leave part of the square unused and the texture would
	#not line up.  run this last, so whatever _wbRelaxUV did is normalised with it.
	uvs = mc.polyListComponentConversion(node, tuv=True)
	bb = mc.polyEvaluate(node, boundingBox2d=True)
	u0, u1 = bb[0][0], bb[0][1]
	v0, v1 = bb[1][0], bb[1][1]
	if u1 - u0 <= 0 or v1 - v0 <= 0:
		mc.warning('weeBuild: %s has no UV area to fit.' % node)
		return
	mc.polyEditUV(uvs, pivotU=u0, pivotV=v0, scaleU=1.0 / (u1 - u0), scaleV=1.0 / (v1 - v0))
	mc.polyEditUV(uvs, relative=True, uValue=-u0, vValue=-v0)
def _wbBuildCoping(profile, length, name, offset_x, ribs=True, bevel=WB_COPING_BEVEL,
				   relax=WB_COPING_RELAX, noses=()):
	#one coping: profile facet -> sweep along +Z -> cap the back -> merge the
	#ribs in -> planar-Y UVs -> centre it and drop the pivot to bottom centre.
	length = float(length)
	pts = [(x, y, 0.0) for x, y in _wbCCW(profile)]
	body = mc.polyCreateFacet(p=pts, name=name)[0]
	mc.polyExtrudeFacet(body + '.f[0]', constructionHistory=True, keepFacesTogether=True, localTranslateZ=length)
	mc.delete(body, constructionHistory=True)
	#the facet the sweep started from leaves an open border behind at Z=0
	try:
		mc.polyCloseBorder(body, constructionHistory=False)
	except Exception:
		pass
	if bevel > 0:
		#chamfer both end cap perimeters.  done before the ribs go in, so only the
		#swept body is bevelled - the ribs keep their square ends
		edges = _wbCapEdges(body, length)
		if edges:
			bev = mc.polyBevel3(edges, offset=bevel, offsetAsFraction=True, segments=1, depth=1,
								worldSpace=True, autoFit=True, mergeVertices=True, smoothingAngle=30)
			#the channel box labels this "Fraction" and on some Maya versions that is a
			#separate attribute from offset, so set it directly rather than trust the flag
			if bev:
				try:
					mc.setAttr(bev[0] + '.fraction', bevel)
				except Exception:
					pass
			mc.delete(body, constructionHistory=True)
		else:
			mc.warning('weeBuild: found no end cap edges to bevel on %s.' % name)
	parts = [body]
	if ribs:
		for i, cx in enumerate(_wbCopingRibs(profile)):
			r = mc.polyCube(w=WB_RIB_W, h=WB_RIB_H, d=length, name='%s_rib%02d' % (name, i + 1))[0]
			mc.move(cx, WB_RIB_Y0 + WB_RIB_H / 2.0, length / 2.0, r)
			parts.append(r)
		if len(parts) > 1:
			#the source model merges the ribs without booleaning them, so they
			#interpenetrate the slab exactly as they do in the original
			body = mc.polyUnite(parts, constructionHistory=False, name=name)[0]
	tf = mc.polyListComponentConversion(body, tf=True)
	#no 90 rotation here (unlike the tiles) - the length already runs along Z,
	#so a straight planar-Y projection sends the texture down the coping
	mc.polyProjection(tf, type='Planar', md='y')
	mc.delete(body, constructionHistory=True)
	try:
		#relax first and fit second, so the nose keeps the extra share of U it was
		#given once the shell is stretched out to fill the square
		_wbRelaxUV(body, noses, relax)
	except Exception as e:
		#never lose finished geometry over a UV tweak
		mc.warning('weeBuild: could not relax the nose UVs on %s - %s' % (name, e))
	_wbFitUV(body)
	bb = mc.xform(body, q=True, ws=True, bb=True)
	mc.move(offset_x - (bb[0] + bb[3]) / 2.0, 0, -(bb[2] + bb[5]) / 2.0, body, relative=True)
	_wbBottomPivot(body)
	return body
def wbCoping(kind='flat', width=None, length=None, count=1, ribs=None,
			 bevel=WB_COPING_BEVEL, relax=WB_COPING_RELAX, spacing=WB_SPACE):
	#build 'count' copings of the given profile in a row along X.  width, length and
	#ribs default to whatever the profile itself was measured with.
	spec = _wbCopingSpec(kind)
	size = spec.get('size') or (WB_COPING_W, WB_COPING_L)
	width = float(size[0] if width is None else width)
	length = float(size[1] if length is None else length)
	#ribs belong to the profile, not to the caller: only 'flat' has them on the real
	#product, so the flag can switch them OFF but never conjure them onto a profile
	#that has none.  to give another profile ribs, set it in WB_COPING_PROFILES.
	ribs = spec['ribs'] and (True if ribs is None else bool(ribs))
	count = int(count)
	if length <= 0:
		raise ValueError('coping length must be greater than 0.')
	if count < 1:
		raise ValueError('need at least 1 coping.')
	bevel = float(bevel)
	if bevel < 0 or bevel >= 0.5:
		raise ValueError('coping bevel is a fraction - it must be 0 or more and under 0.5.')
	relax = float(relax)
	if relax < 1.0 or relax > 5.0:
		raise ValueError('coping UV relax must be between 1 (a plain top projection) and 5.')
	token = _wbSafe('%gx%g' % (width, length), fragment=True) or 'coping'
	prof = _wbCopingProfile(kind, width)
	noses = _wbCopingNoses(kind, width)
	made = []
	for i in range(count):
		nm = _wbUnique('coping_' + _wbSafe(kind, fragment=True) + '_' + token + '_%02d_geo')
		made.append(_wbBuildCoping(prof, length, nm, i * (width + spacing), ribs, bevel,
								   relax, noses))
	mc.select(made)
	print('weeBuild: built %d %s coping(s) at %g x %gcm: %s'
		  % (count, kind, width, length, ', '.join(made)))
	return made
def _wbCopingBtn(kind, width, length):
	#a preset button builds the size written on it - the size comes straight from the
	#preset, never through _wbNum, or a leftover panel field would silently override it
	#and every preset would build whatever the Width box happened to say.  the fields
	#carry the modifiers only, which is how the tile buttons work too.
	return wbCoping(kind, width=width, length=length,
					count=_wbNum('ccount', 1, integer=True),
					ribs=_wbFlag('cribs', True),
					bevel=_wbNum('cbevel', WB_COPING_BEVEL),
					relax=_wbNum('crelax', WB_COPING_RELAX))
def wbCopingCustom():
	#any other width x length, typed in
	r = mc.promptDialog(title='Custom coping',
					    message='Profile and size, e.g. channel 30x50:',
					    text='%s %gx%g' % (WB_COPINGS[0][1], WB_COPING_W, WB_COPING_L),
					    button=['OK', 'Cancel'], defaultButton='OK', cancelButton='Cancel',
					    dismissString='Cancel')
	if r != 'OK':
		return []
	txt = (mc.promptDialog(q=True, text=True) or '').strip()
	kind = WB_COPINGS[0][1]
	head = txt.split()[0].lower() if txt.split() else ''
	if head and not head[0].isdigit():
		if head not in WB_COPING_PROFILES:
			raise ValueError('unknown profile "%s" - have %s.'
							 % (head, ', '.join(sorted(WB_COPING_PROFILES))))
		kind = head
	nums = re.findall(r'[\d.]+', txt)
	if len(nums) < 2:
		raise ValueError('enter a width and a length, e.g. channel 30x50.')
	return _wbCopingBtn(kind, float(nums[0]), float(nums[1]))

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
def _wbCheck(parent, key, label, value=True, ann=''):
	#one full width checkbox, remembered in _wbFields like the number fields
	fl = mc.formLayout(parent=parent, numberOfDivisions=100, height=22)
	c = mc.checkBox(parent=fl, label=label, value=value, annotation=ann)
	_wbFields[key] = c
	mc.formLayout(fl, e=True, attachPosition=[(c, 'left', 4, 0), (c, 'right', 2, 100)],
				  attachForm=[(c, 'top', 2), (c, 'bottom', 2)])
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

	f = mc.frameLayout(parent=main, label='  Copings', collapsable=True, collapse=False, marginHeight=2, backgroundColor=[0.2, 0.2, 0.2])
	#no Width / Length fields here: each button names its own size and the Custom
	#dialog asks for one, so a field could only disagree with the button just pressed
	_wbNums(f, [('ccount', 'Count', '1'), ('cbevel', 'Bevel', '%g' % WB_COPING_BEVEL),
				('crelax', 'Relax', '%g' % WB_COPING_RELAX)])
	_wbCheck(f, 'cribs', 'underside ribs', True,
			 'only the flat profile has ribs; unticking drops them, ticking cannot add them')
	for i in range(0, len(WB_COPINGS), 2):
		_wbRow(f, [(lbl.replace(' ', chr(10), 1), (lambda _k=k, _w=w, _l=l: _wbCopingBtn(_k, _w, _l)), 'teal',
					'build the %s coping profile at %g x %gcm' % (k, w, l))
				   for lbl, k, w, l in WB_COPINGS[i:i + 2]])
	_wbRow(f, [('Custom size...', wbCopingCustom, 'amber', 'build a coping at any width x length')])

	for key, label in WB_SECTIONS:
		f = mc.frameLayout(parent=main, label='  ' + label, collapsable=True, collapse=False, marginHeight=2, backgroundColor=[0.2, 0.2, 0.2])
		_wbFolderRow(f, key)
		_wbCols[key] = mc.columnLayout(parent=f, adjustableColumn=True, rowSpacing=1)
		_wbFillModels(key)
	return main


##############################################################################
#  entry point
##############################################################################

def _wbKeyLabel(key, alt, ctl, sht):
	mods = [m for m, on in (('Shift', sht), ('Ctrl', ctl), ('Alt', alt)) if on]
	return '+'.join(mods + [str(key).upper()])
def _wbEditableHotkeySet():
	#Maya_Default is read only, so a hotkey written into it is silently useless.
	#switch to our own set, copied from whatever is current, the first time.
	cur = mc.hotkeySet(q=True, current=True)
	if cur != 'Maya_Default':
		return cur
	if mc.hotkeySet(WB_HOTKEY_SET, exists=True):
		mc.hotkeySet(WB_HOTKEY_SET, e=True, current=True)
	else:
		mc.hotkeySet(WB_HOTKEY_SET, source=cur, current=True)
	return WB_HOTKEY_SET
def wbHotkey(key='1', alt=True, sht=True, ctl=False):
	#bind a key to open the panel.  Maya remembers hotkeys, so this survives a
	#restart - which is why the command bootstraps itself from WB_SELF_URL when
	#weeBuild is not loaded yet, and simply reopens the panel when it is.  it does
	#NOT re-download on every press: nothing is pushed, so that would serve a stale
	#file over the copy the user is actually working on.
	label = _wbKeyLabel(key, alt, ctl, sht)
	cmd = ("import __main__, urllib.request; "
		   "__main__.weeBuild() if hasattr(__main__, 'weeBuild') else "
		   "exec(urllib.request.urlopen('%s').read().decode('utf-8'), __main__.__dict__)" % WB_SELF_URL)
	_wbEditableHotkeySet()
	try:
		taken = mc.hotkey(key, q=True, name=True, altModifier=alt, ctrlModifier=ctl, shiftModifier=sht)
	except Exception:
		taken = ''
	nc = mc.nameCommand(WB_NAME_CMD, annotation='weeBuild: open the panel',
						command=cmd, sourceType='python')
	if taken and taken not in (nc, WB_NAME_CMD):
		mc.warning('weeBuild: %s was bound to "%s" - replacing it.' % (label, taken))
	#no fallback to a modifier we were not asked for: quietly landing on Alt+1 would
	#clobber weeScript
	mc.hotkey(key, altModifier=alt, ctrlModifier=ctl, shiftModifier=sht, name=nc)
	print('weeBuild: %s opens the panel.' % label)
	return label

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


weeBuild()
try:
	wbHotkey()
except Exception as _wbE:
	mc.warning('weeBuild: could not bind Shift+Alt+1 - %s.  '
			   'Set it by hand in the Hotkey Editor, or call wbHotkey().' % _wbE)
