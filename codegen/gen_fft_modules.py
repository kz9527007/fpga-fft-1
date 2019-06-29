
# This file contains the object models of FFT core constructions.
# Use these classes to build a FFT core layout, and use the functions in
# gen_fft_generators.py to generate HDL code for your layout.


from math import *
from gen_fft_utils import *

def recursiveCall(obj, fn, *args, **kwargs):
	func = None
	try:
		func = getattr(obj, 'children')
	except AttributeError:
		func = None

	if func != None:
		children = func()
		for ch in children:
			recursiveCall(ch, fn, *args, **kwargs)

	try:
		func = getattr(obj, fn)
	except AttributeError:
		func = None

	if func != None:
		func(*args, **kwargs)


class BitPermutation:
	def __init__(self, bitOrder):
		self.bitOrder = bitOrder
		self.N = len(bitOrder)
		self.repLen = bitOrderConstraintLength(bitOrder)
		self.stateBits = int(ceil(log(self.repLen)/log(2)))
	
	def genConstants(self, id):
		return ''
	
	def genDeclarations(self, id):
		fmt = id + 'rP%d'
		signals = [(fmt % i) for i in range(self.stateBits+1)]
		
		fmt = 'signal %s: unsigned(%d-1 downto 0);'
		decls = [(fmt % (x, self.N)) for x in signals]
		
		decls.append('signal %srCnt: unsigned(%d-1 downto 0);' % (id, self.stateBits))
		
		return '\n'.join(decls)

	def sigIn(self, id):
		return id + 'rP0'
	
	def sigOut(self, id):
		return '%srP%d' % (id, self.stateBits)
	
	def sigCount(self, id):
		return id + 'rCnt'
	

	def genBody(self, id):
		buf = ''
		bOrder = self.bitOrder
		for i in xrange(self.stateBits):
			option0 = id + 'rP%d' % i
			option1 = bitOrderToVHDL(bOrder, option0)
			#          0  1   2      3       4
			params = [id, i, i+1, option0, option1]
			buf += \
'''{0:s}rP{2:d} <= {4:s} when {0:s}rCnt({1:d})='1' else {3:s};
'''.format(*params)
			
			bOrder = bitOrderNTimes(bOrder, 2)
		return buf
	
	def delay(self):
		return 0

class Multiplier:
	def __init__(self, entity, delay):
		self.isStub = True
		self.entity = entity
		self.delay1 = delay
		self.imports = [entity]

	def configurationStr(self):
		clsName = self.__class__.__name__
		res = "%s('%s', %d)" % (clsName, self.entity, self.delay1)
		return res

	def descriptionStr(self):
		return "'%s', delay=%d" % (self.entity, self.delay1)

	def getImports(self):
		return self.imports

	def delay(self):
		return self.delay1

defaultMult = Multiplier('complexMultiply2', 6)
largeMult = Multiplier('dsp48e1_complexMultiply', 9)


class FFTBase:
	def __init__(self, N, entity, scale, delay1):
		self.N = N
		self.isBase = True
		self.isStub = True
		self.entity = entity
		self.scale = scale
		self.delay1 = delay1
		self.dataBits = 'dataBits'
		self.imports = [entity]
		self.iBitOrder = range(myLog2(self.N))
		self.oBitOrder = range(myLog2(self.N))

	def setInputBitOrder(self, bitOrder):
		assert len(bitOrder) == myLog2(self.N)
		self.iBitOrder = bitOrder
	
	def setOutputBitOrder(self, bitOrder):
		assert len(bitOrder) == myLog2(self.N)
		self.oBitOrder = bitOrder

	def configurationStr(self):
		clsName = self.__class__.__name__
		res = "%s(%d, '%s', '%s', %d)" % (clsName, self.N, self.entity, self.scale, self.delay1)
		return res
	
	def descriptionStr(self):
		return "%d: base, '%s', scale='%s', delay=%d" % (self.N, self.entity, self.scale, self.delay1)
	
	# returns the mapping from temporal order to natural order; 
	# inputBitOrder()[0] is the source address of bit 0 in the output of the mapping.
	# e.g. bitOrder of [1,2,3,0] will transform 0b0001 to 0b1000
	def inputBitOrder(self):
		return self.iBitOrder

	# see inputBitOrder
	def outputBitOrder(self):
		return self.oBitOrder
	
	def sigIn(self, id):
		return id + 'din'
	def sigOut(self, id):
		return id + 'dout'
	def sigPhase(self, id):
		return id + 'phase'

	def getImports(self):
		return self.imports

	def genConstants(self, id):
		constantsArr = ['N', self.N,
					'order', myLog2(self.N),
					'delay', self.delay()]
		constants = ''
		for i in xrange(0, len(constantsArr), 2):
			name = constantsArr[i]
			val = str(constantsArr[i+1])
			constants += 'constant %s%s: integer := %s;\n' % (id, name,val)
		return constants

	def genDeclarations(self, id):
		return '''
signal {0:s}din, {0:s}dout: complex;
signal {0:s}phase: unsigned({1:d}-1 downto 0);'''.format(id, myLog2(self.N))

	def genBody(self, id):
		template = '''%sinst: entity %s
	generic map(dataBits=>%s, scale=>%s)
	port map(clk=>clk, din=>%sdin, phase=>%sphase, dout=>%sdout);'''
		return template % (id, self.entity,
					self.dataBits, self.scale,
					id, id, id);

	def delay(self):
		return self.delay1

class FFT4Step:
	def __init__(self, N, sub1, sub2, multiplier=defaultMult, twiddleBits='twBits'):
		assert N == (sub1.N*sub2.N)
		self.N = N
		self.isBase = False
		self.isStub = False
		self.sub1 = sub1
		self.sub2 = sub2
		self.twiddleBits = twiddleBits
		self.reorderAdditiveDelay = 0
		self.multiplier = multiplier
		self.multDelay = multiplier.delay()
		self.imports = ['twiddleAddrGen', 'transposer']
		
		if N > 32:
			self.simpleTwiddleRom = False
			self.twiddleDelay = 7
			self.imports.extend(['twiddleGenerator', 'twiddleRom%d' % N])
		else:
			self.simpleTwiddleRom = True
			self.twiddleDelay = 2
			self.imports.append('twiddleGenerator%d' % N)
		
		if not bitOrderIsNatural(sub2.inputBitOrder()):
			self.sub2Transposer = True
			self.reorderPerm = BitPermutation(sub2.inputBitOrder())
			self.reorderDelay = sub2.N + self.reorderAdditiveDelay
			self.imports.append('reorderBuffer')
		else:
			self.sub2Transposer = False

	def setMultiplier(self, multiplier, recursive=True):
		self.multiplier = multiplier
		self.multDelay = multiplier.delay()
		if recursive:
			if not self.sub1.isBase: self.sub1.setMultiplier(multiplier, True)
			if not self.sub2.isBase: self.sub2.setMultiplier(multiplier, True)

	def isStub(self):
		return False

	def children(self):
		return [self.sub1, self.sub2]

	def configurationStr(self):
		clsName = self.__class__.__name__
		
		res = '%s(%d, \n' % (clsName, self.N)
		res += addIndent(self.sub1.configurationStr()) + ',\n'
		res += addIndent(self.sub2.configurationStr()) + ',\n'
		res += '\ttwiddleBits=%s)' % serializeSymbol(self.twiddleBits)
		return res
	
	def descriptionStr(self):
		res = '%d: twiddleBits=%s, delay=%d\n' % (self.N, str(self.twiddleBits), self.delay())
		res += addIndent(self.sub1.descriptionStr()) + '\n'
		res += addIndent(self.sub2.descriptionStr())
		return res
	
	def delay(self):
		d = self.sub1.delay() + self.N + self.multDelay + self.sub2.delay()
		if self.sub2Transposer:
			d += self.reorderDelay
		return d
	
	def inputBitOrder(self):
		O1 = myLog2(self.sub1.N)
		O2 = myLog2(self.sub2.N)
		
		# sub2 must accept data in natural order
		tmp = range(O1,O1+O2)
		tmp += self.sub1.inputBitOrder()
		return tmp

	def outputBitOrder(self):
		O1 = myLog2(self.sub1.N)
		O2 = myLog2(self.sub2.N)
		
		tmp = [x+O2 for x in self.sub1.outputBitOrder()]
		tmp += self.sub2.outputBitOrder()
		return tmp
	
	def sigIn(self, id):
		return id + 'din'
	def sigOut(self, id):
		return id + 'dout'
	def sigPhase(self, id):
		return id + 'phase'
	
	def getImports(self, recursive=True):
		ret = self.imports
		ret.append(self.multiplier.entity)
		if recursive:
			ret.extend(self.sub1.getImports())
			ret.extend(self.sub2.getImports())
		return ret

	def genConstants(self, id):
		constantsArr = ['N', self.N,
					'twiddleBits', self.twiddleBits,
					'twiddleDelay', self.twiddleDelay,
					'order', myLog2(self.N),
					'delay', self.delay()]
		constants = ''
		for i in xrange(0, len(constantsArr), 2):
			name = constantsArr[i]
			val = str(constantsArr[i+1])
			constants += 'constant %s%s: integer := %s;\n' % (id, name,val)
		
		if self.sub2Transposer:
			constants += self.reorderPerm.genConstants(id)
		
		return constants
	
	def genDeclarations(self, id, sub1, sub2, includePorts=True):
		sub1Order = myLog2(self.sub1.N)
		sub2Order = myLog2(self.sub2.N)
		signals = ''
		if includePorts:
			signals = '''
signal {0:s}din, {0:s}dout: complex;
signal {0:s}phase: unsigned({0:s}order-1 downto 0);
'''

		signals += '''
signal {0:s}ph1, {0:s}ph2, {0:s}ph3: unsigned({0:s}order-1 downto 0);
signal {0:s}rbIn, {0:s}transpOut: complex;
signal {0:s}bitPermIn,{0:s}bitPermOut: unsigned({1:d}-1 downto 0);

-- twiddle generator
signal {0:s}twAddr: unsigned({0:s}order-1 downto 0);
signal {0:s}twData: complex;

signal {0:s}romAddr: unsigned({0:s}order-4 downto 0);
signal {0:s}romData: std_logic_vector({0:s}twiddleBits*2-3 downto 0);
'''
		signals = signals.format(id, sub1Order, sub2Order)
		
		if self.sub2Transposer:
			signals += self.reorderPerm.genDeclarations(id)
			signals += '''
signal {0:s}rbInPhase: unsigned({2:d}-1 downto 0);
'''.format(id, sub1Order, sub2Order)
		
		return signals
	
	def genBody(self, id, subId1, subId2):
		bOrder1 = bitOrderToVHDL(self.sub1.outputBitOrder(), id + 'bitPermIn')
		
		sub1order = myLog2(self.sub1.N)
		sub2order = myLog2(self.sub2.N)
		sub1delay = self.sub1.delay()
		sub2delay = self.sub1.delay()
		
		sub2in = self.sub2.sigIn(subId2)
		sub2phase = self.sub2.sigPhase(subId2)
		
		if self.sub2Transposer:
			sub2in = id + 'rbIn'
			sub2phase = id + 'rbInPhase'
			sub2delay += self.reorderDelay
		
		#         0     1       2       3       4             5       6     
		params = [id, subId1, subId2, sub2in, sub2delay, sub2phase, bOrder1,
		#              7          8         9   10
					self.N, self.multDelay, '', '',
		#              11         12         13         14              15
					sub1order, sub2order, sub1delay, sub2delay, self.multiplier.entity
					]
		body = '''
{1:s}din <= {0:s}din;
{1:s}phase <= {0:s}phase({11:d}-1 downto 0);

{0:s}ph1 <= {0:s}phase-{13:d}+1 when rising_edge(clk);

{0:s}transp: entity transposer
	generic map(N1=>{12:d}, N2=>{11:d}, dataBits=>dataBits)
	port map(clk=>clk, din=>{1:s}dout, phase=>{0:s}ph1, dout=>{0:s}transpOut);

{0:s}ph2 <= {0:s}ph1;

{0:s}twAG: entity twiddleAddrGen
	generic map(
		subOrder1=>{11:d},
		subOrder2=>{12:d},
		twiddleDelay=>{0:s}twiddleDelay,
		customSubOrder=>true)
	port map(
		clk=>clk,
		phase=>{0:s}ph2,
		twAddr=>{0:s}twAddr,
		bitPermIn=>{0:s}bitPermIn,
		bitPermOut=>{0:s}bitPermOut);

{0:s}twMult: entity {15:s}
	generic map(in1Bits=>{0:s}twiddleBits+1,
				in2Bits=>dataBits,
				outBits=>dataBits)
	port map(clk=>clk, in1=>{0:s}twData, in2=>{0:s}transpOut, out1=>{3:s});

{0:s}ph3 <= {0:s}ph2-{8:d}+1 when rising_edge(clk);
{5:s} <= {0:s}ph3({12:d}-1 downto 0);
{0:s}dout <= {2:s}dout;
{0:s}bitPermOut <= {6:s};
'''
		
		if self.simpleTwiddleRom:
			body += '''
{0:s}tw: entity twiddleGenerator{7:d} port map(clk, {0:s}twAddr, {0:s}twData);
'''
		else:
			body += '''
{0:s}tw: entity twiddleGenerator generic map({0:s}twiddleBits, {0:s}order)
	port map(clk, {0:s}twAddr, {0:s}twData, {0:s}romAddr, {0:s}romData);
{0:s}rom: entity twiddleRom{7:d} port map(clk, {0:s}romAddr,{0:s}romData);
'''
		
		body = body.format(*params)
		if self.sub2Transposer:
			params = [id, myLog2(self.sub2.N),
						self.reorderPerm.sigIn(id),
						self.reorderPerm.sigCount(id),
						self.reorderPerm.sigOut(id),
						subId2,
						self.reorderAdditiveDelay,
						self.reorderPerm.repLen]
			body += self.reorderPerm.genBody(id)
			body += '''
	
{0:s}rb: entity reorderBuffer
	generic map(N=>{1:d}, dataBits=>dataBits, repPeriod=>{7:d}, bitPermDelay=>0, dataPathDelay=>{6:d})
	port map(clk, din=>{0:s}rbIn, phase=>{0:s}rbInPhase, dout=>{5:s}din,
		bitPermIn=>{2:s}, bitPermCount=>{3:s}, bitPermOut=>{4:s});
	
{5:s}phase <= {0:s}rbInPhase-{6:d};
	
'''.format(*params)
		return body
	
	def _genSubInst(self, instanceName, entityName, obj):
		if isinstance(obj, FFTBase):
			return obj.genBody(instanceName)
		
		line1 = '{0:s}: entity {1:s} generic map(dataBits=>dataBits, twBits=>twBits)'.format(instanceName, entityName)
		line2 = '	port map(clk=>clk, din=>{0:s}din, phase=>{0:s}phase, dout=>{0:s}dout);'.format(instanceName)
		return line1 + '\n' + line2
	
	def genEntity(self, entityName, sub1Name, sub2Name):
		code = '''
library ieee;
library work;
use ieee.numeric_std.all;
use ieee.std_logic_1164.all;
USE ieee.math_real.log2;
USE ieee.math_real.ceil;
use work.fft_types.all;
'''
		imports = self.getImports(False)
		imports.extend([sub1Name, sub2Name])
		importsSet = set()
		for imp in imports:
			if not imp in importsSet:
				importsSet.add(imp)
				code += 'use work.%s;\n' % imp
		
		params = [bitOrderDescription(self.inputBitOrder()),
				bitOrderDescription(self.outputBitOrder()),
				self.delay(),
				entityName,
				myLog2(self.N),
				myLog2(self.sub1.N),
				myLog2(self.sub2.N)]
		code += '''
-- data input bit order: {0:s}
-- data output bit order: {1:s}
-- phase should be 0,1,2,3,4,5,6,...
-- delay is {2:d}
entity {3:s} is
	generic(dataBits: integer := 24;
			twBits: integer := 12);
	port(clk: in std_logic;
		din: in complex;
		phase: in unsigned({4:d}-1 downto 0);
		dout: out complex
		);
end entity;
architecture ar of {3:s} is
	signal sub1din, sub1dout, sub2din, sub2dout: complex;
	signal sub1phase: unsigned({5:d}-1 downto 0);
	signal sub2phase: unsigned({6:d}-1 downto 0);
'''.format(*params)
		
		code += indent(self.genConstants(''), 1)
		code += '\n\n\t--=======================================\n\n'
		code += indent(self.genDeclarations('', 'sub1', 'sub2', False), 1)
		code += '''
begin
'''
		code += indent(self.genBody('', 'sub1', 'sub2'), 1)
		code += indent(self._genSubInst('sub1', sub1Name, self.sub1), 1)
		code += indent(self._genSubInst('sub2', sub2Name, self.sub2), 1)
		code += '''
end ar;
'''
		return code


class FFTSPDF:
	def __init__(self, N, sub1, multiplier=defaultMult, twiddleBits='twBits'):
		assert N == (sub1.N*4)
		self.N = N
		self.isBase = False
		self.isStub = False
		self.sub1 = sub1
		self.multiplier = multiplier
		self.multDelay = multiplier.delay()
		self.twiddleBits = twiddleBits
		self.reorderAdditiveDelay = 0
		self.spdf_delay = N/2 + 3 + N/4 + 3
		self.imports = ['twiddleAddrGen', 'fft_spdf_stage']
		
		if N > 32:
			self.simpleTwiddleRom = False
			self.twiddleDelay = 7
			self.imports.append('twiddleRom%d' % N)
			self.imports.append('twiddleGenerator')
		else:
			self.simpleTwiddleRom = True
			self.twiddleDelay = 2
			self.imports.append('twiddleGenerator%d' % N)
		
		if not bitOrderIsNatural(sub1.inputBitOrder()):
			self.sub1Transposer = True
			self.reorderPerm = BitPermutation(sub1.inputBitOrder())
			self.reorderDelay = sub1.N + self.reorderAdditiveDelay
			self.imports.append('reorderBuffer')
		else:
			self.sub1Transposer = False

	def setMultiplier(self, multiplier, recursive=True):
		self.multiplier = multiplier
		self.multDelay = multiplier.delay()
		if recursive:
			if not self.sub1.isBase: self.sub1.setMultiplier(multiplier, True)

	def children(self):
		return [self.sub1]
	
	def configurationStr(self):
		clsName = self.__class__.__name__
		
		res = '%s(%d, \n' % (clsName, self.N)
		res += addIndent(self.sub1.configurationStr()) + ',\n'
		res += '\tmultiplier=' + self.multiplier.configurationStr() + ',\n'
		res += '\ttwiddleBits=%s)' % serializeSymbol(self.twiddleBits)
		return res
	
	def descriptionStr(self):
		res = '%d: twiddleBits=%s, delay=%d\n' % (self.N, str(self.twiddleBits), self.delay())
		res += '\t4: (spdf stage), delay=%d\n' % (self.spdf_delay,)
		res += addIndent(self.sub1.descriptionStr())
		return res
	
	def delay(self):
		d = self.spdf_delay + self.sub1.delay() + self.multDelay
		if self.sub1Transposer:
			d += self.reorderDelay
		return d
	
	def inputBitOrder(self):
		return range(0, myLog2(self.N))

	def outputBitOrder(self):
		O1 = myLog2(self.sub1.N)
		
		tmp = [x+O1 for x in [1,0]]
		tmp += self.sub1.outputBitOrder()
		return tmp
	
	def sigIn(self, id):
		return id + 'din'
	def sigOut(self, id):
		return id + 'dout'
	def sigPhase(self, id):
		return id + 'phase'
	
	def getImports(self, recursive=True):
		ret = self.imports
		ret.append(self.multiplier.entity)
		if recursive:
			ret.extend(self.sub1.getImports())
		return ret
	
	def genConstants(self, id):
		constantsArr = ['N', self.N,
					'twiddleBits', self.twiddleBits,
					'twiddleDelay', self.twiddleDelay,
					'order', myLog2(self.N),
					'delay', self.delay()]
		constants = ''
		for i in xrange(0, len(constantsArr), 2):
			name = constantsArr[i]
			val = str(constantsArr[i+1])
			constants += 'constant %s%s: integer := %s;\n' % (id, name,val)
		
		if self.sub1Transposer:
			constants += self.reorderPerm.genConstants(id)
		
		return constants
	
	def genDeclarations(self, id, includePorts=True):
		sub1Order = myLog2(self.sub1.N)
		signals = ''
		if includePorts:
			signals = '''
signal {0:s}din, {0:s}dout: complex;
signal {0:s}phase: unsigned({0:s}order-1 downto 0);
'''

		signals += '''
signal {0:s}rbIn, {0:s}spdfOut: complex;
signal {0:s}ph1, {0:s}ph2: unsigned({0:s}order-1 downto 0);

-- twiddle generator
signal {0:s}bitPermIn,{0:s}bitPermOut: unsigned(1 downto 0);
signal {0:s}twAddr: unsigned({0:s}order-1 downto 0);
signal {0:s}twData: complex;

signal {0:s}romAddr: unsigned({0:s}order-4 downto 0);
signal {0:s}romData: std_logic_vector({0:s}twiddleBits*2-3 downto 0);
'''
		signals = signals.format(id, sub1Order)
		
		if self.sub1Transposer:
			signals += self.reorderPerm.genDeclarations(id)
			signals += '''
signal {0:s}rbInPhase: unsigned({1:d}-1 downto 0);
'''.format(id, sub1Order)
		
		return signals
	
	def genBody(self, id, subId1):
		sub1order = myLog2(self.sub1.N)
		sub1delay = self.sub1.delay()
		
		sub1in = self.sub1.sigIn(subId1)
		sub1phase = self.sub1.sigPhase(subId1)
		
		order = myLog2(self.N)
		
		if self.sub1Transposer:
			sub1in = id + 'rbIn'
			sub1phase = id + 'rbInPhase'
			sub1delay += self.reorderDelay
		
		#         0     1       2      3       4           5        6     
		params = [id, subId1, order, sub1in, sub1delay, sub1phase, '',
		#              7          8          9  10
					self.N, self.multDelay, '', '',
		#              11         12           13                  14
					sub1order, sub1delay, self.spdf_delay, self.multiplier.entity
					]
		body = '''
{0:s}spdfStage: entity fft_spdf_stage
	generic map(N=>{2:d}, dataBits=>dataBits)
	port map(clk=>clk, din=>{0:s}din, phase=>{0:s}phase, dout=>{0:s}spdfOut);

{0:s}ph1 <= {0:s}phase-{13:d}+1 when rising_edge(clk);

{0:s}twAG: entity twiddleAddrGen
	generic map(
		subOrder1=>2,
		subOrder2=>{11:d},
		twiddleDelay=>{0:s}twiddleDelay,
		customSubOrder=>true)
	port map(
		clk=>clk,
		phase=>{0:s}ph1,
		twAddr=>{0:s}twAddr,
		bitPermIn=>{0:s}bitPermIn,
		bitPermOut=>{0:s}bitPermOut);

{0:s}twMult: entity {14:s}
	generic map(in1Bits=>{0:s}twiddleBits+1,
				in2Bits=>dataBits,
				outBits=>dataBits)
	port map(clk=>clk, in1=>{0:s}twData, in2=>{0:s}spdfOut, out1=>{3:s});

{0:s}ph2 <= {0:s}ph1-{8:d}+1 when rising_edge(clk);
{5:s} <= {0:s}ph2({11:d}-1 downto 0);

{0:s}dout <= {1:s}dout;

{0:s}bitPermOut <= {0:s}bitPermIn(0) & {0:s}bitPermIn(1);
'''
		
		if self.simpleTwiddleRom:
			body += '''
{0:s}tw: entity twiddleGenerator{7:d} port map(clk, {0:s}twAddr, {0:s}twData);
'''
		else:
			body += '''
{0:s}tw: entity twiddleGenerator generic map({0:s}twiddleBits, {0:s}order)
	port map(clk, {0:s}twAddr, {0:s}twData, {0:s}romAddr, {0:s}romData);
{0:s}rom: entity twiddleRom{7:d} port map(clk, {0:s}romAddr,{0:s}romData);
'''
		
		body = body.format(*params)
		if self.sub1Transposer:
			params = [id, myLog2(self.sub1.N),
						self.reorderPerm.sigIn(id),
						self.reorderPerm.sigCount(id),
						self.reorderPerm.sigOut(id),
						subId1,
						self.reorderAdditiveDelay,
						self.reorderPerm.repLen]
			body += self.reorderPerm.genBody(id)
			body += '''
	
{0:s}rb: entity reorderBuffer
	generic map(N=>{1:d}, dataBits=>dataBits, repPeriod=>{7:d}, bitPermDelay=>0, dataPathDelay=>{6:d})
	port map(clk, din=>{0:s}rbIn, phase=>{0:s}rbInPhase, dout=>{5:s}din,
		bitPermIn=>{2:s}, bitPermCount=>{3:s}, bitPermOut=>{4:s});

{5:s}phase <= {0:s}rbInPhase-{6:d};

'''.format(*params)
		return body
	
	def _genSubInst(self, instanceName, entityName, obj):
		if obj.isStub:
			return obj.genBody(instanceName)
		
		line1 = '{0:s}: entity {1:s} generic map(dataBits=>dataBits, twBits=>twBits)'.format(instanceName, entityName)
		line2 = '	port map(clk=>clk, din=>{0:s}din, phase=>{0:s}phase, dout=>{0:s}dout);'.format(instanceName)
		return line1 + '\n' + line2
	
	def genEntity(self, entityName, sub1Name):
		code = '''
library ieee;
library work;
use ieee.numeric_std.all;
use ieee.std_logic_1164.all;
USE ieee.math_real.log2;
USE ieee.math_real.ceil;
use work.fft_types.all;
'''
		imports = self.getImports(False)
		imports.append(sub1Name)
		importsSet = set()
		for imp in imports:
			if not imp in importsSet:
				importsSet.add(imp)
				code += 'use work.%s;\n' % imp
		
		params = [bitOrderDescription(self.inputBitOrder()),
				bitOrderDescription(self.outputBitOrder()),
				self.delay(),
				entityName,
				myLog2(self.N),
				myLog2(self.sub1.N)]
		code += '''
-- data input bit order: {0:s}
-- data output bit order: {1:s}
-- phase should be 0,1,2,3,4,5,6,...
-- delay is {2:d}
entity {3:s} is
	generic(dataBits: integer := 24;
			twBits: integer := 12);
	port(clk: in std_logic;
		din: in complex;
		phase: in unsigned({4:d}-1 downto 0);
		dout: out complex
		);
end entity;
architecture ar of {3:s} is
	signal sub1din, sub1dout: complex;
	signal sub1phase: unsigned({5:d}-1 downto 0);
'''.format(*params)
		
		code += indent(self.genConstants(''), 1)
		code += '\n\t--=======================================\n\n'
		code += indent(self.genDeclarations('', False), 1)
		code += '''
begin
'''
		code += indent(self.genBody('', 'sub1'), 1)
		code += '\n'
		code += indent(self._genSubInst('sub1', sub1Name, self.sub1), 1)
		code += '''
end ar;
'''
		return code
