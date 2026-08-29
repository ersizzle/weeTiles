def buildTiles():
	import re
	presets = {'33 x 66': (66.0, 33.0), '33 x 33': (33.0, 33.0), '15 x 15': (15.0, 15.0)}
	size = mc.confirmDialog(title='Tile size', message='Choose tile dimensions (cm):', button=['33 x 66', '33 x 33', '15 x 15', 'Custom', 'Cancel'], defaultButton='33 x 66', cancelButton='Cancel', dismissString='Cancel')
	if size in (None, 'Cancel', ''):
		return
	if size == 'Custom':
		r = mc.promptDialog(title='Custom size', message='Short x Long in cm (e.g. 20x40):', button=['OK', 'Cancel'], defaultButton='OK', cancelButton='Cancel', dismissString='Cancel')
		if r != 'OK':
			return
		nums = re.findall(r'[\d.]+', mc.promptDialog(q=True, text=True))
		if len(nums) < 2:
			mc.warning('weeTools: enter two numbers, e.g. 20x40.')
			return
		short, long_ = float(nums[0]), float(nums[1])
		x, z = long_, short
		token = '%gx%g' % (short, long_)
	else:
		x, z = presets[size]
		token = size.replace(' ', '')
	r = mc.promptDialog(title='Tile count', message='How many tiles do you need?', text='4', button=['OK', 'Cancel'], defaultButton='OK', cancelButton='Cancel', dismissString='Cancel')
	if r != 'OK':
		return
	try:
		count = int(float(mc.promptDialog(q=True, text=True)))
	except ValueError:
		mc.warning('weeTools: tile count must be a number.')
		return
	if count < 1:
		mc.warning('weeTools: need at least 1 tile.')
		return
	made = []
	for i in range(count):
		nm = 'tile_%s_%02d_geo' % (token, i + 1)
		made.append(_buildTile(x, z, nm, i * (x + 5.0)))
	mc.select(made)
	print('weeTools: created %d x %scm tile(s).' % (count, token))