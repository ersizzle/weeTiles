#weeTiles - tile library browser for Maya.  Standalone: it shares no code with
#weeScript and every global is prefixed wt/_wt so the two can live side by side
#in Maya's __main__ namespace.
#
#Load into Maya (Python script editor):
#	import urllib.request, __main__
#	exec(urllib.request.urlopen('https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py').read().decode('utf-8'), __main__.__dict__)
#
#Alt+2 re-pulls this file from that address and reopens the browser.
#The tile models themselves come from a library.json manifest - see TILELIB.md.

import math
import os
import random

import maya.cmds as mc
import maya.mel as mel
import maya.OpenMayaUI as omui

#--------------------------------------------------------------------- Qt shim
#PySide6 in Maya 2025+, PySide2 in 2022-2024.  Both ship inside Maya.
try:
	from PySide6 import QtCore, QtGui, QtWidgets
	from shiboken6 import wrapInstance
except ImportError:
	from PySide2 import QtCore, QtGui, QtWidgets
	from shiboken2 import wrapInstance

WT_VERSION = '1.0'
WT_SELF_URL = 'https://raw.githubusercontent.com/ersizzle/weeTiles/master/weeTiles.py'
#where the tile MODELS live - the models are not in this repo.  Point this at
#your own address, or just type it into the browser's Library field once.
WT_LIB_DEFAULT = 'https://www.serapool.com/3d/tiles/library.json'
WT_MIME = 'application/x-weetiles'
WT_OPT_SRC = 'weeTilesSource'
WT_OPT_SET = 'weeTilesSettings'

_wtLib = {}          #cached manifest {'src':..., 'name':..., 'tiles':[...]}
_wtWin = None        #the open browser


##############################################################################
#  settings
##############################################################################

def _wtSrc():
	#the library source, remembered per Maya user
	if mc.optionVar(exists=WT_OPT_SRC):
		s = (mc.optionVar(q=WT_OPT_SRC) or '').strip()
		if s:
			return s.replace('\\', '/')
	return WT_LIB_DEFAULT
def _wtSetSrc(src):
	mc.optionVar(sv=(WT_OPT_SRC, (src or '').strip().replace('\\', '/')))
def _wtGetSettings():
	import json
	if mc.optionVar(exists=WT_OPT_SET):
		try:
			return json.loads(mc.optionVar(q=WT_OPT_SET) or '{}')
		except Exception:
			pass
	return {}
def _wtSaveSettings(d):
	import json
	try:
		mc.optionVar(sv=(WT_OPT_SET, json.dumps(d)))
	except Exception:
		pass
def _wtCacheDir():
	d = os.path.join(mc.internalVar(userAppDir=True), 'weeTiles', 'cache')
	if not os.path.isdir(d):
		os.makedirs(d)
	return d
def _wtCacheSize():
	total = 0
	for dirpath, _dirs, names in os.walk(_wtCacheDir()):
		for n in names:
			try:
				total += os.path.getsize(os.path.join(dirpath, n))
			except OSError:
				pass
	return total


##############################################################################
#  library:  manifest, download, cache
##############################################################################

def _wtIsUrl(p):
	p = (p or '').lower()
	return p.startswith('http://') or p.startswith('https://')
def _wtManifestUrl(src):
	#accept the manifest file itself or the folder holding it
	src = (src or '').replace('\\', '/').rstrip('/')
	return src if src.lower().endswith('.json') else src + '/library.json'
def _wtBase(src):
	#the folder every library-relative path hangs off
	return _wtManifestUrl(src).rsplit('/', 1)[0]
def _wtRead(url, timeout=30):
	#raw bytes from an http(s) address or a local path.  thread safe: no mc calls.
	if _wtIsUrl(url):
		import urllib.request
		req = urllib.request.Request(url, headers={'User-Agent': 'weeTiles/' + WT_VERSION})
		return urllib.request.urlopen(req, timeout=timeout).read()
	h = open(url, 'rb')
	try:
		return h.read()
	finally:
		h.close()
def _wtFetch(rel, rev='', base=None, cache=None, force=False):
	#local path for a library-relative file, downloading it when the library is
	#on a web host.  'base'/'cache' must be passed in from a worker thread -
	#resolving them touches maya.cmds, which is main-thread only.
	import hashlib
	from urllib.parse import quote
	base = base if base is not None else _wtBase(_wtSrc())
	rel = (rel or '').replace('\\', '/').lstrip('/')
	if not rel:
		raise ValueError('weeTiles: empty file path.')
	if not _wtIsUrl(base):
		p = base + '/' + rel
		if not os.path.isfile(p):
			raise IOError('weeTiles: file not found - ' + p)
		return p
	cache = cache if cache is not None else _wtCacheDir()
	slug = hashlib.md5(base.encode('utf-8')).hexdigest()[:10]
	dst = os.path.join(cache, slug, *rel.split('/'))
	revf = dst + '.rev'
	ok = os.path.isfile(dst) and not force
	if ok and rev:
		try:
			h = open(revf)
			ok = h.read().strip() == str(rev)
			h.close()
		except Exception:
			ok = False
	if ok:
		return dst
	d = os.path.dirname(dst)
	if not os.path.isdir(d):
		os.makedirs(d)
	data = _wtRead(base + '/' + '/'.join(quote(s) for s in rel.split('/')))
	h = open(dst, 'wb')
	h.write(data)
	h.close()
	if rev:
		h = open(revf, 'w')
		h.write(str(rev))
		h.close()
	return dst
def _wtLoad(force=False):
	#read (and cache) the manifest for the current source
	global _wtLib
	import json
	src = _wtSrc()
	if (not force) and _wtLib.get('src') == src and _wtLib.get('tiles'):
		return _wtLib
	url = _wtManifestUrl(src)
	if _wtIsUrl(url):
		import time
		url += ('&' if '?' in url else '?') + 't=%d' % int(time.time())   #skip CDN caching
	data = json.loads(_wtRead(url).decode('utf-8'))
	tiles = data.get('tiles') or []
	for i, t in enumerate(tiles):
		if not t.get('id'):
			t['id'] = (t.get('file') or 'tile%03d' % i).replace('\\', '/').rsplit('/', 1)[-1].rsplit('.', 1)[0]
		t.setdefault('name', t['id'])
		t.setdefault('category', 'Other')
		t.setdefault('size', '')
	_wtLib = {'src': src, 'name': data.get('name', 'Tile library'), 'tiles': tiles}
	return _wtLib
def _wtSize(t):
	#(long, short) edge in cm from the entry's w/d, or parsed from its size text
	import re
	if t.get('w') and t.get('d'):
		a, b = float(t['w']), float(t['d'])
		return (max(a, b), min(a, b))
	n = re.findall(r'[\d.]+', str(t.get('size') or ''))
	if len(n) >= 2:
		a, b = float(n[0]), float(n[1])
		return (max(a, b), min(a, b))
	if len(n) == 1:
		return (float(n[0]), float(n[0]))
	return (None, None)
def _wtHaystack(t):
	return ' '.join([str(t.get(k, '')) for k in ('id', 'name', 'category', 'size', 'code')] + [str(x) for x in (t.get('tags') or [])]).lower()


##############################################################################
#  pattern maths  (pure - no Maya, so it can be unit tested)
##############################################################################

def _wtLayout(pattern, tile_l, tile_w, area_w, area_l, grout=0.3, rotate=True):
	#Return [(x, z, ry), ...] tile CENTRES covering area_w x area_l from the
	#origin.  tile_l = long edge (along X at ry 0), tile_w = short edge.
	#Overshoots the area on purpose - the boolean trim cuts it back.
	out = []
	if not tile_l or not tile_w or tile_l <= 0 or tile_w <= 0:
		return out
	square = abs(tile_l - tile_w) < 1e-6
	lu = tile_l + grout
	wu = tile_w + grout
	if pattern == 'herringbone':
		#the interlocking L-pair only tiles the plane when long = 2 x short
		rows = int(math.ceil(area_l / wu)) + 2
		span = int(math.ceil(area_w / (2.0 * lu))) + 2
		for n in range(-2, rows + 2):
			for m in range(-span, span + 1):
				ox = 2.0 * lu * m + wu * n
				oz = wu * n
				for cx, cz, ry in ((lu / 2.0, wu / 2.0, 0.0),
								   (lu + wu / 2.0, (2.0 * wu - lu) / 2.0, 90.0)):
					x, z = ox + cx, oz + cz
					if -tile_l <= x <= area_w + tile_l and -tile_l <= z <= area_l + tile_l:
						out.append((x, z, ry))
		return out
	if pattern == 'bond':
		cols = int(math.ceil(area_w / lu)) + 2
		rows = int(math.ceil(area_l / wu)) + 1
		for r in range(rows):
			off = (lu / 2.0) if (r % 2) else 0.0
			for c in range(cols):
				x = c * lu - off + lu / 2.0
				z = r * wu + wu / 2.0
				ry = random.choice([0.0, 180.0]) if rotate else 0.0
				out.append((x, z, ry))
		return out
	#'grid' - straight stack
	cols = int(math.ceil(area_w / lu)) + 1
	rows = int(math.ceil(area_l / wu)) + 1
	spins = [0.0, 90.0, 180.0, 270.0] if square else [0.0, 180.0]
	for r in range(rows):
		for c in range(cols):
			out.append((c * lu + lu / 2.0, r * wu + wu / 2.0,
						random.choice(spins) if rotate else 0.0))
	return out


##############################################################################
#  Maya side:  import, scatter, trim
##############################################################################

def _wtBottomPivot(node):
	bb = mc.xform(node, q=True, ws=True, bb=True)
	mc.xform(node, ws=True, piv=((bb[0] + bb[3]) / 2.0, bb[1], (bb[2] + bb[5]) / 2.0))
	return bb
def _wtImportOne(t, asRef=False):
	#download + import one library entry.  returns its new top level node(s).
	rel = t.get('file')
	if not rel:
		raise ValueError('weeTiles: "%s" has no file.' % t.get('id'))
	rev = t.get('rev', '')
	for extra in (t.get('assets') or []):            #textures shipped alongside
		try:
			_wtFetch(extra, rev)
		except Exception as e:
			mc.warning('weeTiles: asset %s - %s' % (extra, e))
	path = _wtFetch(rel, rev)
	ext = os.path.splitext(path)[1].lower()
	ftype = {'.ma': 'mayaAscii', '.mb': 'mayaBinary', '.fbx': 'FBX', '.obj': 'OBJ'}.get(ext)
	if ext == '.fbx':
		mc.loadPlugin('fbxmaya', quiet=True)
	elif ext == '.obj':
		mc.loadPlugin('objExport', quiet=True)
	before = set(mc.ls(assemblies=True))
	kw = {'ignoreVersion': True, 'options': 'v=0;'}
	if ftype:
		kw['type'] = ftype
	if asRef:
		mc.file(path, reference=True, namespace=t['id'], **kw)
	else:
		mc.file(path, i=True, mergeNamespacesOnClash=True, namespace=':', preserveReferences=True, **kw)
	new = [n for n in mc.ls(assemblies=True) if n not in before]
	new = [n for n in new if mc.listRelatives(n, allDescendents=True, type='mesh') or mc.listRelatives(n, shapes=True, type='mesh')]
	if not new:
		mc.warning('weeTiles: %s imported but produced no mesh.' % t['id'])
		return []
	out = []
	for n in new:
		if not asRef:
			nm = t['id'] if t['id'].endswith('_geo') else t['id'] + '_geo'
			nm = nm.replace(' ', '_').replace('-', '_')
			try:
				n = mc.rename(n, nm)
			except Exception:
				pass
		_wtBottomPivot(n)
		out.append(n)
	return out
def wtImport(ids, asRef=False, at=None):
	#import library entries.  'at' = (x, z) drops the first one there, otherwise
	#they are laid out side by side along X starting at the origin.
	lib = _wtLoad()
	byId = dict((t['id'], t) for t in lib['tiles'])
	made = []
	x = 0.0
	for tid in (ids or []):
		t = byId.get(tid)
		if not t:
			mc.warning('weeTiles: "%s" is not in the library.' % tid)
			continue
		try:
			nodes = _wtImportOne(t, asRef=asRef)
		except Exception as e:
			mc.warning('weeTiles: could not import %s - %s' % (tid, e))
			continue
		for n in nodes:
			if at:
				mc.move(at[0], 0, at[1], n, absolute=True)
			else:
				mc.move(x, 0, 0, n, absolute=True)
				bb = mc.xform(n, q=True, ws=True, bb=True)
				x = bb[3] + 5.0
		made += nodes
	if made:
		mc.select(made)
	print('weeTiles: imported %d tile(s).' % len(made))
	return made
def wtReplace(tid):
	#swap every selected object for a library tile, keeping its transform
	sel = mc.ls(selection=True, long=True, type='transform') or []
	if not sel:
		mc.warning('weeTiles: select the tile object(s) you want to replace first.')
		return []
	lib = _wtLoad()
	t = dict((e['id'], e) for e in lib['tiles']).get(tid)
	if not t:
		mc.warning('weeTiles: "%s" is not in the library.' % tid)
		return []
	made = []
	for old in sel:
		if not mc.objExists(old):
			continue
		xf = mc.xform(old, q=True, ws=True, matrix=True)
		parent = (mc.listRelatives(old, parent=True, fullPath=True) or [None])[0]
		try:
			nodes = _wtImportOne(t)
		except Exception as e:
			mc.warning('weeTiles: could not import %s - %s' % (tid, e))
			break
		for n in nodes:
			mc.xform(n, ws=True, matrix=xf)
			if parent:
				n = mc.parent(n, parent)[0]
			made.append(n)
		mc.delete(old)
	if made:
		mc.select(made)
	print('weeTiles: replaced %d object(s).' % len(sel))
	return made
def _wtTrim(made, area_w, area_l):
	#instances -> objects, combine a duplicate, then live boolean intersect it
	#with a box the size of the area so the edge tiles are cut flush.
	if not made:
		return
	mc.select(made)
	mel.eval('ConvertInstanceToObject;')
	tiles = [t for t in made if mc.objExists(t)]
	mc.delete(tiles, constructionHistory=True)
	mc.makeIdentity(tiles, apply=True, translate=True, rotate=True, scale=True)
	grp = mc.group(tiles, name='wtTiles_grp#')
	dup = mc.duplicate(grp)[0]
	mc.hide(grp)
	kids = mc.listRelatives(dup, children=True, fullPath=True)
	combined = mc.polyUnite(kids, constructionHistory=False, name='wtTiles_combined#')[0]
	tb = mc.xform(combined, q=True, ws=True, bb=True)
	box = mc.polyCube(w=area_w, h=10.0, d=area_l, name='wtTrim_box#')[0]
	mc.move(area_w / 2.0, tb[1] + 5.0, area_l / 2.0, box, absolute=True)
	bb = mc.xform(box, q=True, ws=True, bb=True)
	mc.xform(box, ws=True, piv=((bb[0] + bb[3]) / 2.0, bb[1], (bb[2] + bb[5]) / 2.0))
	mc.select(box)
	mc.select(combined, add=True)
	mel.eval('polyPerformBooleanAction 3 o 0;')
	keep = [n for n in (box, combined) if mc.objExists(n)]
	if keep:
		mc.select(mc.group(keep, name='wtTrim_grp#'))
def wtScatter(pattern='grid', area_w=600.0, area_l=600.0, grout=0.3, rotate=True, trim=True, tile_l=None, tile_w=None):
	#fill an area with instances of the SELECTED tile object(s), picking among
	#them at random so a floor made of 4-6 variations looks natural.
	sel = mc.ls(selection=True, type='transform') or []
	if not sel:
		mc.warning('weeTiles: select one or more tile objects to scatter first.')
		return []
	if not tile_l or not tile_w:
		bb = mc.xform(sel[0], q=True, ws=True, bb=True)
		a, b = abs(bb[3] - bb[0]), abs(bb[5] - bb[2])
		tile_l, tile_w = max(a, b), min(a, b)
	if pattern == 'herringbone' and abs(tile_l - 2.0 * tile_w) > 0.02 * tile_l:
		mc.warning('weeTiles: herringbone needs a 2:1 tile (like 33x66) - this one is %gx%g, using running bond instead.' % (tile_w, tile_l))
		pattern = 'bond'
	for s in sel:
		_wtBottomPivot(s)
	spots = _wtLayout(pattern, tile_l, tile_w, area_w, area_l, grout, rotate)
	if not spots:
		mc.warning('weeTiles: nothing to place - check the tile size and area.')
		return []
	made = []
	pool = []
	for i, (x, z, ry) in enumerate(spots):
		if not pool:
			pool = list(sel)
			random.shuffle(pool)
		src = pool.pop()
		inst = mc.instance(src, name='%s_i%04d' % (src.split('|')[-1].split(':')[-1], i))
		mc.move(x, 0, z, inst, absolute=True)
		mc.rotate(0, ry, 0, inst, absolute=True)
		made += inst
	print('weeTiles: placed %d tile(s) in a %s pattern over %g x %g cm.' % (len(made), pattern, area_w, area_l))
	if trim:
		_wtTrim(made, area_w, area_l)
	else:
		mc.select(made)
	return made
def wtImportScatter(ids, pattern='grid', area_w=600.0, area_l=600.0, grout=0.3, rotate=True, trim=True):
	#import the given tiles, then immediately fill the area with them
	lib = _wtLoad()
	byId = dict((t['id'], t) for t in lib['tiles'])
	made = wtImport(ids)
	if not made:
		return []
	l, w = (None, None)
	for tid in (ids or []):
		if tid in byId:
			l, w = _wtSize(byId[tid])
			break
	return wtScatter(pattern, area_w, area_l, grout, rotate, trim, tile_l=l, tile_w=w)


##############################################################################
#  viewport drag + drop
##############################################################################

def _wtGroundPoint(pos):
	#screen point -> where it hits the Y=0 ground plane.  (0,0) if that fails.
	try:
		import maya.OpenMaya as om
		view = omui.M3dView.active3dView()
		pnt = om.MPoint()
		vec = om.MVector()
		view.viewToWorld(int(pos.x()), int(view.portHeight() - pos.y()), pnt, vec)
		if abs(vec.y) < 1e-9:
			return (0.0, 0.0)
		t = -pnt.y / vec.y
		return (pnt.x + vec.x * t, pnt.z + vec.z * t)
	except Exception:
		return (0.0, 0.0)
class WtDropFilter(QtCore.QObject):
	#accepts weeTiles drags dropped onto a model panel and imports there
	def eventFilter(self, obj, ev):
		et = ev.type()
		if et in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove):
			try:
				if ev.mimeData().hasFormat(WT_MIME):
					ev.acceptProposedAction()
					return True
			except Exception:
				pass
		elif et == QtCore.QEvent.Drop:
			try:
				md = ev.mimeData()
				if not md.hasFormat(WT_MIME):
					return False
				ids = bytes(md.data(WT_MIME)).decode('utf-8').split('\n')
				pos = ev.position().toPoint() if hasattr(ev, 'position') else ev.pos()
				x, z = _wtGroundPoint(pos)
				ev.acceptProposedAction()
				wtImport([i for i in ids if i], at=(x, z))
				return True
			except Exception as e:
				mc.warning('weeTiles: drop failed - %s' % e)
		return False
def _wtHookViewports(filt):
	#let every model panel accept our drags.  harmless if it fails.
	n = 0
	for p in (mc.getPanel(type='modelPanel') or []):
		try:
			ptr = omui.MQtUtil.findControl(p)
			if not ptr:
				continue
			w = wrapInstance(int(ptr), QtWidgets.QWidget)
			w.setAcceptDrops(True)
			w.removeEventFilter(filt)
			w.installEventFilter(filt)
			n += 1
		except Exception:
			pass
	return n


##############################################################################
#  UI
##############################################################################

class WtThumbSignals(QtCore.QObject):
	done = QtCore.Signal(str, str)
class WtThumbJob(QtCore.QRunnable):
	#downloads one thumbnail off the main thread.  it only touches the network
	#and the disk - never maya.cmds, and never QPixmap.
	def __init__(self, tid, rel, rev, base, cache):
		super(WtThumbJob, self).__init__()
		self.tid, self.rel, self.rev, self.base, self.cache = tid, rel, rev, base, cache
		self.signals = WtThumbSignals()
	def run(self):
		path = ''
		try:
			path = _wtFetch(self.rel, self.rev, base=self.base, cache=self.cache)
		except Exception:
			path = ''
		try:
			self.signals.done.emit(self.tid, path)
		except Exception:
			pass
class WtFilterProxy(QtCore.QSortFilterProxyModel):
	def __init__(self, parent=None):
		super(WtFilterProxy, self).__init__(parent)
		self.terms = []
		self.cat = 'All'
	def setQuery(self, text, cat):
		self.terms = [w for w in (text or '').lower().split() if w]
		self.cat = cat or 'All'
		self.invalidateFilter()
	def filterAcceptsRow(self, row, parent):
		idx = self.sourceModel().index(row, 0, parent)
		t = idx.data(QtCore.Qt.UserRole) or {}
		if self.cat != 'All' and t.get('category') != self.cat:
			return False
		if not self.terms:
			return True
		hay = idx.data(QtCore.Qt.UserRole + 1) or ''
		return all(term in hay for term in self.terms)
class WtListView(QtWidgets.QListView):
	#icon grid that starts a drag carrying the ticked tile ids
	imported = QtCore.Signal()
	def startDrag(self, actions):
		ids = []
		for idx in self.selectedIndexes():
			t = idx.data(QtCore.Qt.UserRole) or {}
			if t.get('id'):
				ids.append(t['id'])
		if not ids:
			return
		md = QtCore.QMimeData()
		md.setData(WT_MIME, QtCore.QByteArray('\n'.join(ids).encode('utf-8')))
		md.setText(', '.join(ids))
		drag = QtGui.QDrag(self)
		drag.setMimeData(md)
		first = self.selectedIndexes()[0]
		ic = first.data(QtCore.Qt.DecorationRole)
		if isinstance(ic, QtGui.QIcon):
			pm = ic.pixmap(72, 72)
			if not pm.isNull():
				drag.setPixmap(pm)
		drag.exec_(QtCore.Qt.CopyAction) if hasattr(drag, 'exec_') else drag.exec(QtCore.Qt.CopyAction)
class WtBrowser(QtWidgets.QWidget):
	def __init__(self, parent=None):
		super(WtBrowser, self).__init__(parent)
		self.setWindowFlags(QtCore.Qt.Window)
		self.setObjectName('weeTilesBrowser')
		self.setWindowTitle('weeTiles  -  Tile Library  v' + WT_VERSION)
		self.resize(980, 640)
		self._items = {}
		self._pool = QtCore.QThreadPool()
		self._pool.setMaxThreadCount(6)
		self._dropFilter = WtDropFilter()
		self._build()
		self._restore()
		QtCore.QTimer.singleShot(0, self.reload)
		QtCore.QTimer.singleShot(0, lambda: _wtHookViewports(self._dropFilter))

	#--------------------------------------------------------------- building
	def _build(self):
		root = QtWidgets.QHBoxLayout(self)
		root.setContentsMargins(6, 6, 6, 6)
		root.setSpacing(6)
		left = QtWidgets.QVBoxLayout()
		left.setSpacing(4)
		root.addLayout(left, 1)

		bar = QtWidgets.QHBoxLayout()
		self.search = QtWidgets.QLineEdit()
		self.search.setPlaceholderText('search  -  name, code, size, tag...')
		self.search.setClearButtonEnabled(True)
		self.search.textChanged.connect(self._filter)
		self.cat = QtWidgets.QComboBox()
		self.cat.setMinimumWidth(150)
		self.cat.currentIndexChanged.connect(self._filter)
		bar.addWidget(self.search, 1)
		bar.addWidget(self.cat)
		left.addLayout(bar)

		self.model = QtGui.QStandardItemModel(self)
		self.proxy = WtFilterProxy(self)
		self.proxy.setSourceModel(self.model)
		self.view = WtListView()
		self.view.setModel(self.proxy)
		self.view.setViewMode(QtWidgets.QListView.IconMode)
		self.view.setResizeMode(QtWidgets.QListView.Adjust)
		self.view.setMovement(QtWidgets.QListView.Static)
		self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
		self.view.setIconSize(QtCore.QSize(96, 96))
		self.view.setGridSize(QtCore.QSize(120, 140))
		self.view.setUniformItemSizes(True)
		self.view.setWordWrap(True)
		self.view.setSpacing(4)
		self.view.setDragEnabled(True)
		self.view.doubleClicked.connect(lambda *a: self.doImport())
		left.addWidget(self.view, 1)

		self.status = QtWidgets.QLabel('')
		self.status.setStyleSheet('color: #999;')
		left.addWidget(self.status)

		side = QtWidgets.QVBoxLayout()
		side.setSpacing(6)
		root.addLayout(side, 0)
		w = QtWidgets.QWidget()
		w.setFixedWidth(250)
		side.addWidget(w)
		col = QtWidgets.QVBoxLayout(w)
		col.setContentsMargins(0, 0, 0, 0)
		col.setSpacing(6)

		#--- import
		g = QtWidgets.QGroupBox('Import')
		v = QtWidgets.QVBoxLayout(g)
		self.asRef = QtWidgets.QCheckBox('as reference (live link)')
		v.addWidget(self.asRef)
		b = QtWidgets.QPushButton('Import Selected')
		b.setMinimumHeight(30)
		b.clicked.connect(self.doImport)
		v.addWidget(b)
		b = QtWidgets.QPushButton('Replace Scene Objects')
		b.setToolTip('Select objects in the scene, pick ONE tile here, then press this.')
		b.clicked.connect(self.doReplace)
		v.addWidget(b)
		v.addWidget(QtWidgets.QLabel('<i>or drag a tile into the viewport</i>'))
		col.addWidget(g)

		#--- pattern
		g = QtWidgets.QGroupBox('Fill area')
		f = QtWidgets.QFormLayout(g)
		self.pattern = QtWidgets.QComboBox()
		self.pattern.addItems(['Grid', 'Running bond', 'Herringbone'])
		f.addRow('Pattern', self.pattern)
		self.areaW = QtWidgets.QDoubleSpinBox()
		self.areaL = QtWidgets.QDoubleSpinBox()
		self.grout = QtWidgets.QDoubleSpinBox()
		for s, lo, hi, dec, val in ((self.areaW, 1, 100000, 1, 600.0), (self.areaL, 1, 100000, 1, 600.0), (self.grout, 0, 10, 2, 0.3)):
			s.setRange(lo, hi)
			s.setDecimals(dec)
			s.setValue(val)
			s.setSingleStep(1.0 if dec == 1 else 0.05)
		f.addRow('Width cm', self.areaW)
		f.addRow('Length cm', self.areaL)
		f.addRow('Grout cm', self.grout)
		self.spin = QtWidgets.QCheckBox('random rotation')
		self.spin.setChecked(True)
		f.addRow('', self.spin)
		self.trim = QtWidgets.QCheckBox('trim to area (boolean)')
		self.trim.setChecked(True)
		f.addRow('', self.trim)
		b = QtWidgets.QPushButton('Import + Fill')
		b.setMinimumHeight(30)
		b.clicked.connect(self.doImportFill)
		f.addRow(b)
		b = QtWidgets.QPushButton('Fill with Selected Objects')
		b.setToolTip('Uses the tiles already selected in the scene instead of importing.')
		b.clicked.connect(self.doFill)
		f.addRow(b)
		col.addWidget(g)

		#--- library
		g = QtWidgets.QGroupBox('Library')
		v = QtWidgets.QVBoxLayout(g)
		self.src = QtWidgets.QLineEdit()
		self.src.setToolTip('A web address (your website, GitHub raw) or a local / network folder.')
		self.src.returnPressed.connect(self.applySource)
		v.addWidget(self.src)
		h = QtWidgets.QHBoxLayout()
		b = QtWidgets.QPushButton('Set / Reload')
		b.clicked.connect(self.applySource)
		h.addWidget(b)
		b = QtWidgets.QPushButton('Browse...')
		b.clicked.connect(self.browseFolder)
		h.addWidget(b)
		v.addLayout(h)
		self.cacheLbl = QtWidgets.QLabel('')
		self.cacheLbl.setStyleSheet('color: #999;')
		v.addWidget(self.cacheLbl)
		b = QtWidgets.QPushButton('Clear Cache')
		b.clicked.connect(self.clearCache)
		v.addWidget(b)
		col.addWidget(g)
		col.addStretch(1)

	#--------------------------------------------------------------- settings
	def _restore(self):
		s = _wtGetSettings()
		self.src.setText(_wtSrc())
		try:
			self.pattern.setCurrentIndex(int(s.get('pattern', 0)))
			self.areaW.setValue(float(s.get('areaW', 600.0)))
			self.areaL.setValue(float(s.get('areaL', 600.0)))
			self.grout.setValue(float(s.get('grout', 0.3)))
			self.spin.setChecked(bool(s.get('spin', True)))
			self.trim.setChecked(bool(s.get('trim', True)))
		except Exception:
			pass
	def _store(self):
		_wtSaveSettings({'pattern': self.pattern.currentIndex(), 'areaW': self.areaW.value(),
						 'areaL': self.areaL.value(), 'grout': self.grout.value(),
						 'spin': self.spin.isChecked(), 'trim': self.trim.isChecked()})
	def closeEvent(self, ev):
		try:
			self._store()
		except Exception:
			pass
		super(WtBrowser, self).closeEvent(ev)

	#--------------------------------------------------------------- library
	def applySource(self):
		_wtSetSrc(self.src.text())
		self.reload()
	def browseFolder(self):
		d = QtWidgets.QFileDialog.getExistingDirectory(self, 'Pick the tile library folder')
		if d:
			self.src.setText(d.replace('\\', '/'))
			self.applySource()
	def clearCache(self):
		import shutil
		try:
			shutil.rmtree(_wtCacheDir())
		except Exception as e:
			mc.warning('weeTiles: could not clear the cache - %s' % e)
		self._cacheLabel()
		self.reload()
	def _cacheLabel(self):
		try:
			self.cacheLbl.setText('cache: %.1f MB' % (_wtCacheSize() / 1048576.0))
		except Exception:
			self.cacheLbl.setText('')
	def reload(self):
		self.status.setText('loading library...')
		QtWidgets.QApplication.processEvents()
		try:
			lib = _wtLoad(force=True)
		except Exception as e:
			self.model.clear()
			self.status.setText('could not read the library - %s' % e)
			mc.warning('weeTiles: %s' % e)
			return
		self.model.clear()
		self._items = {}
		base = _wtBase(_wtSrc())
		cache = _wtCacheDir()
		blank = QtGui.QPixmap(96, 96)
		blank.fill(QtGui.QColor(58, 58, 58))
		for t in lib['tiles']:
			it = QtGui.QStandardItem()
			label = t.get('name') or t['id']
			if t.get('size'):
				label += '\n%s cm' % t['size']
			it.setText(label)
			it.setEditable(False)
			it.setTextAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
			it.setToolTip('%s\n%s   %s\n%s' % (t['id'], t.get('category', ''), t.get('size', ''), t.get('file', '')))
			it.setData(t, QtCore.Qt.UserRole)
			it.setData(_wtHaystack(t), QtCore.Qt.UserRole + 1)
			it.setIcon(QtGui.QIcon(blank))
			self.model.appendRow(it)
			self._items[t['id']] = it
			if t.get('thumb'):
				job = WtThumbJob(t['id'], t['thumb'], t.get('rev', ''), base, cache)
				job.signals.done.connect(self._thumb)
				self._pool.start(job)
		cats = sorted(set(t.get('category', 'Other') for t in lib['tiles']))
		cur = self.cat.currentText()
		self.cat.blockSignals(True)
		self.cat.clear()
		self.cat.addItems(['All'] + cats)
		if cur in ['All'] + cats:
			self.cat.setCurrentText(cur)
		self.cat.blockSignals(False)
		self._cacheLabel()
		self._filter()
	def _thumb(self, tid, path):
		#main thread: turn a downloaded file into the item's icon
		it = self._items.get(tid)
		if not it or not path or not os.path.isfile(path):
			return
		pm = QtGui.QPixmap(path)
		if pm.isNull():
			return
		it.setIcon(QtGui.QIcon(pm.scaled(96, 96, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)))
	def _filter(self, *a):
		self.proxy.setQuery(self.search.text(), self.cat.currentText())
		self.status.setText('%d of %d tiles   -   %s' % (self.proxy.rowCount(), self.model.rowCount(), _wtLib.get('name', '')))

	#--------------------------------------------------------------- actions
	def selectedIds(self):
		out = []
		for idx in self.view.selectedIndexes():
			t = idx.data(QtCore.Qt.UserRole) or {}
			if t.get('id') and t['id'] not in out:
				out.append(t['id'])
		return out
	def _need(self, one=False):
		ids = self.selectedIds()
		if not ids:
			mc.warning('weeTiles: pick a tile in the browser first.')
			return None
		if one and len(ids) > 1:
			mc.warning('weeTiles: pick just one tile for this.')
			return None
		return ids
	def doImport(self):
		ids = self._need()
		if ids:
			wtImport(ids, asRef=self.asRef.isChecked())
			self._cacheLabel()
	def doReplace(self):
		ids = self._need(one=True)
		if ids:
			wtReplace(ids[0])
			self._cacheLabel()
	def _fillArgs(self):
		self._store()
		return {'pattern': ['grid', 'bond', 'herringbone'][self.pattern.currentIndex()],
				'area_w': self.areaW.value(), 'area_l': self.areaL.value(),
				'grout': self.grout.value(), 'rotate': self.spin.isChecked(),
				'trim': self.trim.isChecked()}
	def doImportFill(self):
		ids = self._need()
		if ids:
			wtImportScatter(ids, **self._fillArgs())
			self._cacheLabel()
	def doFill(self):
		wtScatter(**self._fillArgs())


##############################################################################
#  entry point
##############################################################################

def _wtMayaWindow():
	try:
		return wrapInstance(int(omui.MQtUtil.mainWindow()), QtWidgets.QWidget)
	except Exception:
		return None
def weeTiles():
	#open (or re-open) the tile browser
	global _wtWin
	try:
		if _wtWin:
			_wtWin.close()
			_wtWin.deleteLater()
	except Exception:
		pass
	_wtWin = WtBrowser(parent=_wtMayaWindow())
	_wtWin.show()
	_wtWin.raise_()
	return _wtWin
def _wtRegisterHotkey(key='2', alt=True, ctl=False):
	#Alt+2 re-pulls this file from GitHub and reopens the browser
	cmd = ("import urllib.request, __main__\n"
		   "exec(urllib.request.urlopen('%s?t='+str(__import__('time').time())).read().decode('utf-8'), __main__.__dict__)" % WT_SELF_URL)
	nc = mc.nameCommand('weeTilesReload', annotation='weeTiles: reload from GitHub',
						command='python("%s")' % cmd.replace('\n', r'\n').replace('"', r'\"'), sourceType='python')
	mc.hotkey(k=key, alt=alt, ctl=ctl, name=nc)


weeTiles()
try:
	_wtRegisterHotkey()
except Exception as _e:
	mc.warning('weeTiles: could not register the Alt+2 hotkey - %s' % _e)
