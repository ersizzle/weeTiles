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

import math
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

#Infinity Karo, from serapool.com (Fossil Mix serisi, grup urunleri).  a 33x66 tile
#with a full bullnose on its long edges: 'cift bitis' finishes both, 'tek bitis' one.
#stock codes FM3366IT-CIFT / FM3366OIT-CIFT and FM3366IT-TEK / FM3366OIT-TEK.
#the two thicknesses are the site's own; the bullnose radius is NOT published, so it
#is taken as half the thickness - a true half round - which the user confirmed.
WB_INFINITY = [
	('Infinity Cift 0.76', 2, 0.76),
	('Infinity Cift 1.80', 2, 1.80),
	('Infinity Tek 0.76', 1, 0.76),
	('Infinity Tek 1.80', 1, 1.80),
]
WB_INF_SIZE = (33.0, 66.0)     #(short, long) in cm, as the site lists it
WB_INF_THICK = (0.76, 1.80)
WB_INF_SEG = 8                 #segments in the bullnose half round

#coping presets in panel order: (label, profile key, width cm, length cm).
WB_COPINGS = [
	('Flat 25 x 50', 'flat', 25.0, 50.0),
	('Overflow 33 x 66', 'overflow', 33.0, 66.0),
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
#  size  the (width, length) to build by default.  usually the size the model was
#        measured at, but not always - see 'overflow'
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
	#linear_overflow_coping_natural: a bar with BOTH top corners rounded, exactly
	#symmetric about x = -6.36.  both arcs are exact quarter circles of R0.9650 - the
	#same tooling radius as the flat coping's bullnose.  two noses, so the UV relax
	#has to widen each end.
	#the MODEL measures 25 x 50 x 1.20, but the real product is 33 x 66: all three
	#source models were exported on a shared 25 x 50 footprint.  so 'size' here is the
	#product size, not the measured one, and the build stretches the flat middle to
	#reach it.  that keeps the thickness at 1.20 and the arcs at R0.9650 - scaling the
	#whole profile by 33/25 instead would give 1.584 thick and R1.2738, which would
	#break the radius it shares with the flat coping.
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
		'size': (33.0, 66.0),
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

#flex grate presets: (label, width cm, length cm).  the source model is
#tile_models/grates/flex_grate_30_50 - an assembly of identical slats, not a swept
#profile, so unlike the copings these constants are the design it is built from
#rather than a measured cross-section.
WB_GRATES = [
	('Flex 15 x 50', 15.0, 50.0),
	('Flex 20 x 50', 20.0, 50.0),
	('Flex 25 x 50', 25.0, 50.0),
	('Flex 30 x 50', 30.0, 50.0),
]
WB_GRATE_SIZE = (30.0, 50.0)  #default, and what the source model is
WB_GRATE_SLAT = 4.2      #nominal slat length along the run
WB_GRATE_GAP = 0.9       #drainage slot between slats - fixed at every size
WB_GRATE_THICK = 2.532   #slat height
WB_GRATE_Y0 = -0.02      #slat underside, so it sits on the floor like the copings
WB_GRATE_INSET = 2.495   #hardware column inset from each end of a slat
WB_GRATE_COLPITCH = 13.0 #the FURTHEST apart two connectors are allowed to be
#the source model has TWO concentric cylinders on this axis: a 2.060 connector and a
#0.404 core hidden inside it.  the core alone read far too thin and the 2.060 too
#heavy, so this sits at the midpoint of the pair - the user's call, by eye in the
#viewport, not a measurement.  the core is not modelled at all: nothing of it shows.
WB_GRATE_ROD = 1.232     #connector diameter, midway between the model's 0.404 and 2.060
WB_GRATE_RODY = 1.301    #its axis height, measured
WB_GRATE_ROD_OVER = 0.45 #how far it runs past the slats at each end, as the model does
WB_GRATE_BEVEL = 0.08    #chamfer on the slat ends, where the sweep is cut

#monoblock grate presets: (label, width cm, length cm).  measured off
#tile_models/grates/monoblock_hidden_grate.  this one has NO slots through it: the slab is
#solid and the water goes round the block, through the open ladder frame it stands on,
#which is why the frame is wider than the slab.  the model's slab is exactly 25 x 65,
#so the preset sizes are the slab and the frame comes out 2 wider and 1 longer.
WB_MONOH = [
	('Hidden 25 x 65', 25.0, 65.0),
	('Hidden 30 x 65', 30.0, 65.0),
]
WB_MONOH_SIZE = (25.0, 65.0)  #default, and what the model measures
WB_MONOH_H = 1.6          #slab thickness
WB_MONOH_Y = 0.8          #slab underside, so it sits 0.2 into the frame
WB_MONOH_BASE_H = 1.0     #frame height
WB_MONOH_OVER_X = 1.0     #how far the frame stands proud of the slab, each side
WB_MONOH_OVER_Z = 0.5     #and at each end
WB_MONOH_RAIL_W = 2.0     #the two rails running the length of the frame
WB_MONOH_RAIL_IN = 1.35   #their outer face, in from the frame edge
WB_MONOH_RIB = 1.0        #cross rib thickness
WB_MONOH_RIB_PITCH = 16.0 #nominal spacing between ribs
WB_MONOH_RIB_GAP = 5.0    #the gap down the middle of the inner ribs
WB_MONOH_BEVEL = 0.06     #the frame's edge rounding, measured at 0.061

#monoblock grate presets: (label, width cm, length cm).  measured off
#tile_models/grates/monoblock_grate - the slotted one.  its slab is exactly 25 x 65
#and carries 11 slots of 1.500 x 12.000 in three columns, the middle column staggered
#half a pitch against the outer two.  it stands on the same kind of frame as the
#hidden version, so those constants are shared rather than duplicated.
WB_MONO = [
	('Mono 25 x 65', 25.0, 65.0),
	('Mono 30 x 65', 30.0, 65.0),
]
WB_MONO_SIZE = (25.0, 65.0)  #default, and what the model measures
WB_MONO_H = WB_MONOH_H       #slab thickness, same 1.6
WB_MONO_Y = WB_MONOH_Y
WB_MONO_SLOT_W = 1.5     #slot width, across the slab
WB_MONO_SLOT_L = 12.0    #slot length, down the slab
WB_MONO_SLOT_PITCH = 15.0#Z pitch within a column; the stagger is half of this
WB_MONO_MARGIN = 4.0     #solid margin between the outermost slot and the slab edge
WB_MONO_COL_MAX = 10.5   #the furthest apart two slot columns may sit
WB_MONO_BEVEL = 0.06     #the frame's edge rounding
#the slab's twelve outer edges are ROUNDED, not chamfered: all four fillets measure
#R0.116 over four segments, in plan as well as in section.  a 1-segment chamfer at
#half that size is what made it read as a plain box.  the slot walls are sharp, so
#this is applied before the slots are cut.
WB_MONO_ROUND = 0.116
WB_MONO_ROUND_SEG = 4
WB_MONO_SLOT_SEG = 12    #segments in each semicircular slot end

#the slat cross-section, sliced out of the source model.  it is NOT a box: the top is a
#shallow camber, the sides draught inward, the top corners are arcs and the underside
#carries two channels.  the edge detail below is measured as (inset from the edge, Y) and
#never changes with width - same idea as a coping nose - while the camber and the
#underside span whatever width is asked for.
WB_SLAT_END = [
	(0.0152, 0.0), (0.0076, 0.0097), (0.0, 0.0194),
	(0.1226, 0.5097), (0.2452, 1.0), (0.4013, 1.4153), (0.5574, 1.8306),
	(0.5848, 1.8756), (0.6122, 1.9207), (0.6559, 1.9535), (0.6997, 1.9863),
	(0.7506, 2.0), (0.8015, 2.0138),
]
#the camber holds its RISE, not its radius, so every slat is the same height whatever
#the width.  it has to be: the connector is fixed hardware sitting at a fixed Y, and
#holding the radius instead shrinks a narrow slat until the connector pokes out
#through the top - at 15cm wide it stood 0.154 proud.  the radius therefore falls out
#of the width (about 45 at 15cm, 136 at 25, 201 at 30) rather than being fixed.
WB_SLAT_RISE = 0.502      #camber height above the edge, measured off the model
WB_SLAT_TOP = 2.0138      #Y where the corner arc hands over to the camber
WB_SLAT_BOT = -0.0197     #underside, between the channels
WB_SLAT_SEG = 16          #segments the camber is drawn with
WB_SLAT_CH_OFF = 0.4891   #channel centres as a fraction of the half width (6.111/12.495)
WB_SLAT_CH_W = 1.398
WB_SLAT_CH_D = 0.312
WB_SLAT_CH_RAMP = 2.36

#model sections: (settings key, panel label).  drop model files into a section's
#folder and hit Refresh - one button appears per file, no code change needed.
WB_SECTIONS = [('grates', 'Grate models'), ('copings', 'Coping models')]
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

def _wbInfProfile(short, thick, ends, seg=WB_INF_SEG):
	#cross-section of an infinity tile, in (X, Y): a slab 'short' across and 'thick' deep
	#with a full bullnose - radius half the thickness - on one or both of its long edges.
	#with both ends finished this is a stadium, the same shape as a monoblock slot.
	short, thick = float(short), float(thick)
	ends = int(ends)
	if ends not in (1, 2):
		raise ValueError('an infinity tile is finished on 1 or 2 edges.')
	r = thick / 2.0
	hx = short / 2.0
	if r <= 0 or short <= ends * r:
		raise ValueError('the tile is too narrow to carry its bullnose.')
	seg = max(2, int(seg))
	left = -hx + (r if ends == 2 else 0.0)
	pts = [(left, -r), (hx - r, -r)]
	#the near long edge is always bullnosed: a half round from the underside to the top
	for i in range(1, seg):
		a = -math.pi / 2.0 + math.pi * i / float(seg)
		pts.append((hx - r + r * math.cos(a), r * math.sin(a)))
	pts += [(hx - r, r), (left, r)]
	if ends == 2:
		for i in range(1, seg):
			a = math.pi / 2.0 + math.pi * i / float(seg)
			pts.append((-hx + r + r * math.cos(a), r * math.sin(a)))
	#with one end finished there is nothing more to add: the loop closes from (-hx, r)
	#straight down to (-hx, -r), and that closing edge IS the square end.  appending
	#those two points explicitly just duplicates ones already in the list.
	return pts
def _wbBuildInf(short, long_, thick, ends, name, offset_x):
	#swept exactly like a coping, then turned so the long edge lies along X the way every
	#other tile in this file does.  geometry straddles Y=0, as weeScript's tiles do; only
	#the pivot goes to the bottom.
	short, long_, thick = float(short), float(long_), float(thick)
	pts = [(x, y, 0.0) for x, y in _wbCCW(_wbInfProfile(short, thick, ends))]
	body = mc.polyCreateFacet(p=pts, name=name)[0]
	mc.polyExtrudeFacet(body + '.f[0]', constructionHistory=True, keepFacesTogether=True,
						localTranslateZ=long_)
	mc.delete(body, constructionHistory=True)
	try:
		mc.polyCloseBorder(body, constructionHistory=False)
	except Exception:
		pass
	#the sweep runs along Z; turn it a quarter so the 66 lies along X, then bake it in
	mc.rotate(0, 90, 0, body)
	mc.makeIdentity(body, apply=True, rotate=True)
	tf = mc.polyListComponentConversion(body, tf=True)
	mc.polyProjection(tf, type='Planar', md='y')
	#same UV recipe as the flat tiles: planar from the top, then turned 90 so the texture
	#runs along the long edge.  NOT the copings' fill-the-square fit - these are tiles and
	#have to sit in the same texture grid as the rest of the deck.
	bb2 = mc.polyEvaluate(body, boundingBox2d=True)
	mc.polyEditUV(mc.polyListComponentConversion(body, tuv=True),
				  pivotU=(bb2[0][0] + bb2[0][1]) / 2.0, pivotV=(bb2[1][0] + bb2[1][1]) / 2.0,
				  angle=90)
	mc.delete(body, constructionHistory=True)
	bb = mc.xform(body, q=True, ws=True, bb=True)
	mc.move(offset_x - (bb[0] + bb[3]) / 2.0, 0.0, -(bb[2] + bb[5]) / 2.0, body, relative=True)
	_wbBottomPivot(body)
	return body
def wbInfinity(ends=2, thick=None, short=None, long_=None, count=1, spacing=WB_SPACE):
	#build 'count' infinity tiles in a row along X
	short = float(WB_INF_SIZE[0] if short is None else short)
	long_ = float(WB_INF_SIZE[1] if long_ is None else long_)
	thick = float(WB_INF_THICK[0] if thick is None else thick)
	ends = int(ends)
	count = int(count)
	if count < 1:
		raise ValueError('need at least 1 tile.')
	if long_ <= 0:
		raise ValueError('tile length must be greater than 0.')
	_wbInfProfile(short, thick, ends)      #validates ends and the bullnose fit
	token = '%s_%s_%s' % ('cift' if ends == 2 else 'tek',
						  _wbSafe('%gx%g' % (short, long_), fragment=True),
						  _wbSafe('%g' % thick, fragment=True))
	made = []
	for i in range(count):
		nm = _wbUnique('tile_infinity_' + token + '_%02d_geo')
		made.append(_wbBuildInf(short, long_, thick, ends, nm, i * (long_ + spacing)))
	mc.select(made)
	print('weeBuild: built %d infinity tile(s), %s bitis, %g x %g x %gcm: %s'
		  % (count, 'cift' if ends == 2 else 'tek', short, long_, thick, ', '.join(made)))
	return made
def _wbInfBtn(ends, thick):
	#a preset button builds the size written on it - never through _wbNum
	return wbInfinity(ends, thick, count=_wbNum('count', 1, integer=True))
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
#  grates - a slat array.  NOT a swept profile like the copings
##############################################################################

def _wbSlatUnder(half):
	#the underside, right to left: a channel either side of centre with a long ramp
	#into each.  breakpoints that a narrow slat has squeezed past are dropped, so the
	#run stays monotonic in X instead of folding back on itself.
	b, dpt = WB_SLAT_BOT, WB_SLAT_BOT + WB_SLAT_CH_D
	off = WB_SLAT_CH_OFF * half
	w, r = WB_SLAT_CH_W / 2.0, WB_SLAT_CH_RAMP
	edge = half - WB_SLAT_END[0][0]
	pts = [(edge, 0.0)]
	for c in (off, -off):
		pts += [(c + w + r, b), (c + w, dpt), (c - w, dpt), (c - w - r, b)]
	pts.append((-edge, 0.0))
	out = []
	for p in pts:
		if not out or p[0] < out[-1][0] - 1e-6:
			out.append(p)
	return out
def _wbSlatProfile(width, seg=WB_SLAT_SEG):
	#the whole cross-section: up the left edge, across the camber, down the right edge,
	#back along the underside.  pure maths, no Maya.
	half = float(width) / 2.0
	inset = WB_SLAT_END[-1][0]
	if half <= inset + 0.5:
		raise ValueError('grate slat is too narrow to carry its edge profile.')
	pts = [(-half + dx, y) for dx, y in WB_SLAT_END]
	hs = half - inset
	rise = WB_SLAT_RISE
	if rise <= 0:
		raise ValueError('grate slat camber rise must be greater than 0.')
	#the arc through (+-hs, 0) and (0, rise)
	R = (hs * hs + rise * rise) / (2.0 * rise)
	base = R - rise
	for i in range(1, int(seg)):
		x = -hs + 2.0 * hs * i / float(seg)
		pts.append((x, WB_SLAT_TOP + math.sqrt(max(R * R - x * x, 0.0)) - base))
	pts += [(half - dx, y) for dx, y in reversed(WB_SLAT_END)]
	pts += _wbSlatUnder(half)
	return pts
def _wbBuildSlat(profile, length, name):
	#one slat, swept along Z exactly the way a coping is
	pts = [(x, y, 0.0) for x, y in _wbCCW(profile)]
	s = mc.polyCreateFacet(p=pts, name=name)[0]
	mc.polyExtrudeFacet(s + '.f[0]', constructionHistory=True, keepFacesTogether=True,
						localTranslateZ=float(length))
	mc.delete(s, constructionHistory=True)
	try:
		mc.polyCloseBorder(s, constructionHistory=False)
	except Exception:
		pass
	return s
def _wbStadium(width, length, seg=WB_MONO_SLOT_SEG):
	#a stadium outline in (x, z): straight sides with a semicircular cap at each end.
	#the model's slots are this shape, not rectangles - one measures 17.4720 in area
	#against 18.0000 for a rectangle and 17.5171 for a true stadium.
	r = float(width) / 2.0
	h = float(length) / 2.0 - r
	if r <= 0 or h < 0:
		raise ValueError('a slot must be at least as long as it is wide.')
	seg = max(2, int(seg))
	pts = [(r, -h), (r, h)]
	for i in range(1, seg):
		a = math.pi * i / float(seg)
		pts.append((r * math.cos(a), h + r * math.sin(a)))
	pts += [(-r, h), (-r, -h)]
	for i in range(1, seg):
		a = math.pi * (1.0 + i / float(seg))
		pts.append((r * math.cos(a), -h + r * math.sin(a)))
	return pts
def _wbFacetUp(pts):
	#order an (x, z) loop so polyCreateFacet gives it a +Y normal.  a loop running
	#counter clockwise in (x, z) faces -Y, so that one gets reversed.
	n = len(pts)
	a = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
			for i in range(n)) / 2.0
	return list(pts) if a < 0 else list(reversed(pts))
def _wbSlotCutter(cx, cz, name):
	#one slot cutter: the stadium profile swept up through the slab.  it starts below the
	#slab and runs well past the top, so the cut goes clean through both faces.
	prof = _wbFacetUp(_wbStadium(WB_MONO_SLOT_W, WB_MONO_SLOT_L))
	y0 = WB_MONO_Y - WB_MONO_H
	c = mc.polyCreateFacet(p=[(cx + x, y0, cz + z) for x, z in prof], name=name)[0]
	mc.polyExtrudeFacet(c + '.f[0]', constructionHistory=True, keepFacesTogether=True,
						localTranslateZ=WB_MONO_H * 3.0)
	mc.delete(c, constructionHistory=True)
	try:
		mc.polyCloseBorder(c, constructionHistory=False)
	except Exception:
		pass
	return c
def _wbBool(a, b, op, name):
	#Maya has had two boolean entry points; use the cmds one and fall back to the MEL
	#action weeScript has always driven.  op: 1 union, 2 difference, 3 intersection.
	try:
		out = mc.polyCBoolOp(a, b, op=op, constructionHistory=False, name=name)[0]
	except Exception:
		mc.select(a)
		mc.select(b, add=True)
		mel.eval('polyPerformBooleanAction %d o 0;' % op)
		sel = mc.ls(selection=True) or []
		out = sel[0] if sel else a
	if mc.objExists(out) and out != name and not mc.objExists(name):
		out = mc.rename(out, name)
	return out
def _wbMonoSlotCols(width, pitch=WB_MONO_COL_MAX):
	#slot column X centres.  the count is always ODD, which is what keeps the stagger
	#symmetric: every other column is offset half a pitch, so an even count would leave
	#the two middle columns matching and break the pattern.
	span = float(width) - 2.0 * WB_MONO_MARGIN - WB_MONO_SLOT_W
	if span <= 0:
		return [0.0]
	n = 3
	while span / (n - 1) > float(pitch):
		n += 2
	return [-span / 2.0 + span * i / (n - 1) for i in range(n)]
def _wbMonoSlotRows(length):
	#Z centres of the slots: one run for the columns that carry a full set, and one
	#offset half a pitch for the columns between them.  the model has 4 and 3 at 65cm.
	span = float(length) - 2.0 * WB_MONO_MARGIN - WB_MONO_SLOT_L
	if span < 0:
		return [], []
	n = int(span // WB_MONO_SLOT_PITCH) + 1
	ext = (n - 1) * WB_MONO_SLOT_PITCH / 2.0
	full = [-ext + WB_MONO_SLOT_PITCH * i for i in range(n)]
	return full, [z + WB_MONO_SLOT_PITCH / 2.0 for z in full[:-1]]
def _wbMonoSlots(width, length):
	#the slots themselves, as (x, z) centres - only used for reporting and testing
	cols = _wbMonoSlotCols(float(width))
	full, half = _wbMonoSlotRows(float(length))
	out = []
	for k, c in enumerate(cols):
		for z in (full if k % 2 == 0 else half):
			out.append((c, z))
	return out
def _wbBuildMono(width, length, name, offset_x, bevel=WB_MONO_BEVEL):
	#a monoblock grate: a slotted slab on the same frame as the hidden one.
	width, length, bevel = float(width), float(length), float(bevel)
	#the slab is ONE box with the slots cut out of it.  building it as a jigsaw of solid
	#pieces instead leaves coincident internal faces wherever two pieces meet, which
	#z-fights and shades badly - the source is a single watertight shell, every edge used
	#exactly twice, so it was cut and this has to be too.
	slab = mc.polyCube(w=width, h=WB_MONO_H, d=length, name=name + '_slab')[0]
	mc.move(0.0, WB_MONO_Y + WB_MONO_H / 2.0, 0.0, slab)
	#round the slab's twelve outer edges BEFORE cutting.  order matters: the model has
	#R0.116 rounds right round the slab but dead sharp slot walls, and bevelling after the
	#boolean would round the slots too.  this is also what stops it reading as a plain box.
	if WB_MONO_ROUND > 0:
		mc.polyBevel3(mc.ls(slab + '.e[*]', flatten=True), offset=WB_MONO_ROUND,
					  offsetAsFraction=False, segments=int(WB_MONO_ROUND_SEG), depth=1,
					  worldSpace=True, autoFit=True, mergeVertices=True, smoothingAngle=30)
		mc.delete(slab, constructionHistory=True)
	#the slots are stadiums - straight sides with a semicircular cap at each end - so
	#the cutter is that profile swept up, not a box
	cutters = [_wbSlotCutter(cx, cz, '%s_slot%02d' % (name, i + 1))
			   for i, (cx, cz) in enumerate(_wbMonoSlots(width, length))]
	if cutters:
		cut = cutters[0]
		if len(cutters) > 1:
			cut = mc.polyUnite(cutters, constructionHistory=False, name=name + '_cut')[0]
		slab = _wbBool(slab, cut, 2, name + '_slab')
	#the frame, which keeps its own smaller rounding
	frame = []
	bw = width + 2.0 * WB_MONOH_OVER_X
	bl = length + 2.0 * WB_MONOH_OVER_Z
	rx = bw / 2.0 - WB_MONOH_RAIL_IN - WB_MONOH_RAIL_W / 2.0
	for i, x in enumerate((-rx, rx)):
		r = mc.polyCube(w=WB_MONOH_RAIL_W, h=WB_MONOH_BASE_H, d=bl,
						name='%s_rail%02d' % (name, i + 1))[0]
		mc.move(x, WB_MONOH_BASE_H / 2.0, 0.0, r)
		frame.append(r)
	zs = _wbMonoHRibs(length)
	for i, z in enumerate(zs):
		if i in (0, len(zs) - 1):
			b = mc.polyCube(w=bw, h=WB_MONOH_BASE_H, d=WB_MONOH_RIB,
							name='%s_rib%02d' % (name, i + 1))[0]
			mc.move(0.0, WB_MONOH_BASE_H / 2.0, z, b)
			frame.append(b)
			continue
		hw = (bw - WB_MONOH_RIB_GAP) / 2.0
		if hw <= 0:
			continue
		for s in (-1.0, 1.0):
			b = mc.polyCube(w=hw, h=WB_MONOH_BASE_H, d=WB_MONOH_RIB,
							name='%s_rib%02d%s' % (name, i + 1, 'lr'[s > 0]))[0]
			mc.move(s * (WB_MONOH_RIB_GAP + hw) / 2.0, WB_MONOH_BASE_H / 2.0, z, b)
			frame.append(b)
	if bevel > 0:
		for q in frame:
			mc.polyBevel3(mc.ls(q + '.e[*]', flatten=True), offset=bevel, offsetAsFraction=False,
						  segments=1, depth=1, worldSpace=True, autoFit=True,
						  mergeVertices=True, smoothingAngle=30)
			mc.delete(q, constructionHistory=True)
	parts = [slab] + frame
	out = parts[0]
	if len(parts) > 1:
		out = mc.polyUnite(parts, constructionHistory=False, name=name)[0]
	tf = mc.polyListComponentConversion(out, tf=True)
	mc.polyProjection(tf, type='Planar', md='y')
	mc.delete(out, constructionHistory=True)
	_wbFitUV(out)
	mc.move(offset_x, 0.0, 0.0, out, relative=True)
	_wbBottomPivot(out)
	return out
def wbMono(width=None, length=None, count=1, bevel=WB_MONO_BEVEL, spacing=WB_SPACE):
	#build 'count' monoblock grates in a row along X
	width = float(WB_MONO_SIZE[0] if width is None else width)
	length = float(WB_MONO_SIZE[1] if length is None else length)
	count = int(count)
	if width <= 2.0 * WB_MONO_MARGIN + WB_MONO_SLOT_W or length <= 0:
		raise ValueError('monoblock is too small to carry a slot.')
	if count < 1:
		raise ValueError('need at least 1 monoblock.')
	bevel = float(bevel)
	if bevel < 0 or bevel * 2.0 >= WB_MONO_SLOT_W:
		raise ValueError('monoblock bevel must be between 0 and half the slot width.')
	token = _wbSafe('%gx%g' % (width, length), fragment=True) or 'mono'
	made = []
	for i in range(count):
		nm = _wbUnique('grate_mono_' + token + '_%02d_geo')
		made.append(_wbBuildMono(width, length, nm, i * (width + spacing), bevel))
	mc.select(made)
	print('weeBuild: built %d monoblock(s) at %g x %gcm, %d slots: %s'
		  % (count, width, length, len(_wbMonoSlots(width, length)), ', '.join(made)))
	return made
def _wbMonoBtn(width, length):
	#a preset button builds the size written on it - never through _wbNum
	return wbMono(width, length, count=_wbNum('gcount', 1, integer=True),
				  bevel=_wbNum('mbevel', WB_MONO_BEVEL))
def _wbMonoHRibs(length):
	#Z centres of the cross ribs.  the outer pair sit one rib in from the base ends and
	#the rest spread evenly between, keeping the pitch near WB_MONOH_RIB_PITCH: five ribs
	#at exactly 16.0 apart for the 65 the model was measured at.
	ext = (float(length) + 2.0 * WB_MONOH_OVER_Z) / 2.0 - WB_MONOH_RIB
	if ext <= 0:
		return [0.0]
	n = max(2, int(round(2.0 * ext / WB_MONOH_RIB_PITCH)) + 1)
	return [-ext + 2.0 * ext * i / (n - 1) for i in range(n)]
def _wbBuildMonoH(width, length, name, offset_x, bevel=WB_MONOH_BEVEL):
	#a monoblock: a solid slab on a ladder frame.  no slots through it - the water goes
	#round the block, not through it, which is why the frame is wider than the slab and
	#is open between its ribs.
	width, length, bevel = float(width), float(length), float(bevel)
	bw = width + 2.0 * WB_MONOH_OVER_X
	bl = length + 2.0 * WB_MONOH_OVER_Z
	parts = []
	#the slab.  the model's own section reduces to four points, so this really is a plain
	#box - no chamfer, no camber, unlike the flex slat.
	body = mc.polyCube(w=width, h=WB_MONOH_H, d=length, name=name + '_slab')[0]
	mc.move(0.0, WB_MONOH_Y + WB_MONOH_H / 2.0, 0.0, body)
	parts.append(body)
	#two rails down the full length of the frame
	rx = bw / 2.0 - WB_MONOH_RAIL_IN - WB_MONOH_RAIL_W / 2.0
	for i, x in enumerate((-rx, rx)):
		r = mc.polyCube(w=WB_MONOH_RAIL_W, h=WB_MONOH_BASE_H, d=bl,
						name='%s_rail%02d' % (name, i + 1))[0]
		mc.move(x, WB_MONOH_BASE_H / 2.0, 0.0, r)
		parts.append(r)
	#cross ribs.  the end pair run the full width; the ones between have a gap down the
	#middle for the water, so each is built as two pieces
	zs = _wbMonoHRibs(length)
	for i, z in enumerate(zs):
		if i in (0, len(zs) - 1):
			b = mc.polyCube(w=bw, h=WB_MONOH_BASE_H, d=WB_MONOH_RIB,
							name='%s_rib%02d' % (name, i + 1))[0]
			mc.move(0.0, WB_MONOH_BASE_H / 2.0, z, b)
			parts.append(b)
			continue
		hw = (bw - WB_MONOH_RIB_GAP) / 2.0
		if hw <= 0:
			continue
		for s in (-1.0, 1.0):
			b = mc.polyCube(w=hw, h=WB_MONOH_BASE_H, d=WB_MONOH_RIB,
							name='%s_rib%02d%s' % (name, i + 1, 'lr'[s > 0]))[0]
			mc.move(s * (WB_MONOH_RIB_GAP + hw) / 2.0, WB_MONOH_BASE_H / 2.0, z, b)
			parts.append(b)
	if bevel > 0:
		for q in parts:
			mc.polyBevel3(mc.ls(q + '.e[*]', flatten=True), offset=bevel,
						  offsetAsFraction=False, segments=1, depth=1, worldSpace=True,
						  autoFit=True, mergeVertices=True, smoothingAngle=30)
			mc.delete(q, constructionHistory=True)
	out = parts[0]
	if len(parts) > 1:
		out = mc.polyUnite(parts, constructionHistory=False, name=name)[0]
	tf = mc.polyListComponentConversion(out, tf=True)
	mc.polyProjection(tf, type='Planar', md='y')
	mc.delete(out, constructionHistory=True)
	_wbFitUV(out)
	mc.move(offset_x, 0.0, 0.0, out, relative=True)
	_wbBottomPivot(out)
	return out
def wbMonoH(width=None, length=None, count=1, bevel=WB_MONOH_BEVEL, spacing=WB_SPACE):
	#build 'count' monoblock grates in a row along X
	width = float(WB_MONOH_SIZE[0] if width is None else width)
	length = float(WB_MONOH_SIZE[1] if length is None else length)
	count = int(count)
	if width <= 0 or length <= 0:
		raise ValueError('monoblock size must be greater than 0.')
	if count < 1:
		raise ValueError('need at least 1 monoblock.')
	bevel = float(bevel)
	if bevel < 0 or bevel * 2.0 >= WB_MONOH_BASE_H:
		raise ValueError('monoblock bevel must be between 0 and half the frame height.')
	token = _wbSafe('%gx%g' % (width, length), fragment=True) or 'mono'
	made = []
	for i in range(count):
		nm = _wbUnique('grate_monohidden_' + token + '_%02d_geo')
		made.append(_wbBuildMonoH(width, length, nm, i * (width + spacing), bevel))
	mc.select(made)
	print('weeBuild: built %d hidden monoblock(s) at %g x %gcm, %d ribs: %s'
		  % (count, width, length, len(_wbMonoHRibs(length)), ', '.join(made)))
	return made
def _wbMonoHBtn(width, length):
	#a preset button builds the size written on it - never through _wbNum
	return wbMonoH(width, length, count=_wbNum('gcount', 1, integer=True),
				  bevel=_wbNum('hbevel', WB_MONOH_BEVEL))
def _wbGrateSlats(length, slat=WB_GRATE_SLAT, gap=WB_GRATE_GAP):
	#how many slats fit in 'length', and how long each has to be for the run to come
	#out at exactly that.  the gap is the drainage slot and is held constant across
	#every size, so the slat absorbs the rounding instead: the source model's
	#10 x 4.2 + 9 x 0.9 comes to 50.1, this gives a true 50 with slats of 4.19.
	slat, gap, length = float(slat), float(gap), float(length)
	if length <= 0:
		raise ValueError('grate length must be greater than 0.')
	n = max(1, int(round((length + gap) / (slat + gap))))
	z = (length - (n - 1) * gap) / n
	if z <= 0:
		raise ValueError('grate is too short to fit a slat.')
	return n, z
def _wbGrateCols(width, inset=WB_GRATE_INSET, pitch=WB_GRATE_COLPITCH):
	#X positions of the hardware columns.  the outer two sit 'inset' in from each end
	#and the rest spread evenly between them, using the fewest columns that keeps every
	#spacing at or under 'pitch'.  a maximum rather than a nominal spacing, so adding a
	#column is a decision about how far apart connectors may sit rather than a rounding
	#accident: 2 / 3 / 3 / 3 across the four presets, and fed the model's own 24.990 it
	#gives back the model's layout, three columns exactly 10.0 apart.
	width = float(width)
	span = width - 2.0 * float(inset)
	if span <= 0:
		return [0.0]
	n = max(2, int(math.ceil(span / float(pitch))) + 1)
	return [-width / 2.0 + float(inset) + span * i / (n - 1) for i in range(n)]
def _wbBuildGrate(width, length, name, offset_x, bevel=WB_GRATE_BEVEL):
	#one grate: a row of slats down Z with a fixed drainage slot between them, then
	#a rod through each hardware column running the whole length, all merged.
	#unlike a coping this is an assembly, not a swept profile - the source model's
	#slats carry a sculpted surface relief (faces up to 3 degrees off flat) that no
	#cross-section can express, so the slats here are clean bevelled boxes and the
	#stone character has to come from the texture.
	width, length, bevel = float(width), float(length), float(bevel)
	n, sz = _wbGrateSlats(length)
	prof = _wbSlatProfile(width)
	parts = []
	for i in range(n):
		s = _wbBuildSlat(prof, sz, '%s_slat%02d' % (name, i + 1))
		if bevel > 0:
			#chamfer where the sweep was cut, exactly as the copings do
			edges = _wbCapEdges(s, sz)
			if edges:
				mc.polyBevel3(edges, offset=bevel, offsetAsFraction=True, segments=1, depth=1,
							  worldSpace=True, autoFit=True, mergeVertices=True, smoothingAngle=30)
				mc.delete(s, constructionHistory=True)
		mc.move(0.0, 0.0, -length / 2.0 + i * (sz + WB_GRATE_GAP), s)
		parts.append(s)
	for j, cx in enumerate(_wbGrateCols(width)):
		r = mc.polyCylinder(r=WB_GRATE_ROD / 2.0, h=length + 2.0 * WB_GRATE_ROD_OVER,
							axis=(0, 0, 1), subdivisionsAxis=16,
							name='%s_rod%02d' % (name, j + 1))[0]
		mc.move(cx, WB_GRATE_RODY, 0.0, r)
		parts.append(r)
	body = parts[0]
	if len(parts) > 1:
		body = mc.polyUnite(parts, constructionHistory=False, name=name)[0]
	tf = mc.polyListComponentConversion(body, tf=True)
	mc.polyProjection(tf, type='Planar', md='y')
	mc.delete(body, constructionHistory=True)
	#same rule as the copings: the shell fills 0-1 so the texture registers
	_wbFitUV(body)
	mc.move(offset_x, 0.0, 0.0, body, relative=True)
	_wbBottomPivot(body)
	return body
def wbGrate(width=None, length=None, count=1, bevel=WB_GRATE_BEVEL, spacing=WB_SPACE):
	#build 'count' flex grates in a row along X
	width = float(WB_GRATE_SIZE[0] if width is None else width)
	length = float(WB_GRATE_SIZE[1] if length is None else length)
	count = int(count)
	if width <= 0:
		raise ValueError('grate width must be greater than 0.')
	if count < 1:
		raise ValueError('need at least 1 grate.')
	bevel = float(bevel)
	if bevel < 0 or bevel * 2.0 >= WB_GRATE_THICK:
		raise ValueError('grate bevel must be between 0 and half the slat thickness.')
	token = _wbSafe('%gx%g' % (width, length), fragment=True) or 'grate'
	made = []
	for i in range(count):
		nm = _wbUnique('grate_flex_' + token + '_%02d_geo')
		made.append(_wbBuildGrate(width, length, nm, i * (width + spacing), bevel))
	mc.select(made)
	n, sz = _wbGrateSlats(length)
	print('weeBuild: built %d grate(s) at %g x %gcm, %d slats of %.3f: %s'
		  % (count, width, length, n, sz, ', '.join(made)))
	return made
def _wbGrateBtn(width, length):
	#a preset button builds the size written on it - never through _wbNum
	return wbGrate(width, length, count=_wbNum('gcount', 1, integer=True),
				   bevel=_wbNum('gbevel', WB_GRATE_BEVEL))
def wbGrateCustom():
	#any other width x length, typed in
	r = mc.promptDialog(title='Custom grate', message='Width x Length in cm (e.g. 40x50):',
						text='%gx%g' % (WB_GRATE_SIZE[0], WB_GRATE_SIZE[1]),
						button=['OK', 'Cancel'], defaultButton='OK', cancelButton='Cancel',
						dismissString='Cancel')
	if r != 'OK':
		return []
	nums = re.findall(r'[\d.]+', (mc.promptDialog(q=True, text=True) or ''))
	if len(nums) < 2:
		raise ValueError('enter two numbers, e.g. 40x50.')
	return _wbGrateBtn(float(nums[0]), float(nums[1]))

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
	for i in range(0, len(WB_INFINITY), 2):
		_wbRow(f, [(_wbWrap(lbl), (lambda _e=e, _t=t: _wbInfBtn(_e, _t)), 'indigo',
					'Infinity Karo %s bitis, %g x %g x %gcm - bullnosed on %d long edge%s'
					% ('cift' if e == 2 else 'tek', WB_INF_SIZE[0], WB_INF_SIZE[1], t, e,
					   's' if e == 2 else ''))
				   for lbl, e, t in WB_INFINITY[i:i + 2]])

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

	f = mc.frameLayout(parent=main, label='  Grates', collapsable=True, collapse=False, marginHeight=2, backgroundColor=[0.2, 0.2, 0.2])
	_wbNums(f, [('gcount', 'Count', '1'), ('gbevel', 'Bevel', '%g' % WB_GRATE_BEVEL),
				('mbevel', 'SlotBev', '%g' % WB_MONO_BEVEL)])
	_wbNums(f, [('hbevel', 'HiddenBevel', '%g' % WB_MONOH_BEVEL)])
	for i in range(0, len(WB_GRATES), 2):
		_wbRow(f, [(_wbWrap(lbl), (lambda _w=w, _l=l: _wbGrateBtn(_w, _l)), 'indigo',
					'build a %g x %gcm flex grate' % (w, l)) for lbl, w, l in WB_GRATES[i:i + 2]])
	_wbRow(f, [('Custom size...', wbGrateCustom, 'amber', 'build a flex grate at any width x length')])
	_wbRow(f, [(_wbWrap(lbl), (lambda _w=w, _l=l: _wbMonoBtn(_w, _l)), 'purple',
				'build a %g x %gcm monoblock grate - a slotted slab' % (w, l))
			   for lbl, w, l in WB_MONO])
	_wbRow(f, [(_wbWrap(lbl), (lambda _w=w, _l=l: _wbMonoHBtn(_w, _l)), 'coral',
				'build a %g x %gcm monoblock grate - solid slab, water goes round it'
				% (w, l)) for lbl, w, l in WB_MONOH])

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
