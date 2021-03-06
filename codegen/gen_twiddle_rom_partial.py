#!/usr/bin/python
from math import *
import sys

if len(sys.argv) < 3:
	print 'usage: %s SIZE WIDTH0 [WIDTH1...]' % sys.argv[0]
	exit(1)

N = int(sys.argv[1]);
widths = [int(x) for x in sys.argv[2:]];

# this twiddle generator is the minor part of a size M twiddle genenerator;
# currently M = N * (4N)
M = N * (N*4)


reducedBits = False;
# if reducedBits is true, output fits in a twiddleBits bit signed integer.
# if reducedBits is false, output fits in a twiddleBits+1 bit signed integer.

depthOrder = int(ceil(log(N)/log(2.)));
romWidth = 'twBits'
if not reducedBits:
	romWidth = 'twBits + 1'

def printROM(twBits):
	scale = (2**(twBits-1));
	if reducedBits:
		scale -= 1
	else:
		twBits += 1

	fmt = '{0:0' + str(twBits) + 'b}'
	fullScale = M
	for i in xrange(N):
		x = float(i)/fullScale * (2*pi)
		
		re1 = int(round(cos(x)*scale))
		im1 = int(round(sin(x)*scale))
		if re1<0:
			re1 += (2**twBits)
		if im1<0:
			im1 += (2**twBits)
		
		if i != 0:
			print ',',
		if i%6 == 0: print;
		print '"' + fmt.format(im1) + fmt.format(re1) + '"', 

name = 'twiddleGeneratorPartial'+str(N)

print '''
library ieee;
library work;
use ieee.numeric_std.all;
use ieee.std_logic_1164.all;
use work.fft_types.all;
-- read delay is 2 cycles

entity {1:s} is
	generic(twBits: integer := 17);
	port(clk: in std_logic;
			twAddr: in unsigned({0:d}-1 downto 0);
			twData: out complex
			);
end entity;
architecture a of {1:s} is
	constant romDepthOrder: integer := {0:d};
	constant romDepth: integer := 2**romDepthOrder;
	constant romWidth: integer := ({2:s})*2;
	--ram
	type ram1t is array(0 to romDepth-1) of
		std_logic_vector(romWidth-1 downto 0);
	signal rom: ram1t;
	signal addr1: unsigned(romDepthOrder-1 downto 0) := (others=>'0');
	signal data0,data1: std_logic_vector(romWidth-1 downto 0) := (others=>'0');
begin
	addr1 <= twAddr when rising_edge(clk);
	data0 <= rom(to_integer(addr1));
	data1 <= data0 when rising_edge(clk);
	twData <= complex_unpack(data1);
'''.format(depthOrder, name, romWidth),

for twBits in widths:
	print '''
g{twBits:d}:
	if twBits = {twBits:d} generate
		rom <= ('''.format(**locals()), 
	printROM(twBits)
	print ''');
	end generate;'''

print;
print '''
end a;
'''
