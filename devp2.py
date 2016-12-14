#!/usr/bin/env python3

from envy.section import Section
from envy.isa.vp2macro import isa as vp2macroisa
from envy.deco import DecodeError
from envy.deco.block import Block


class Vp2Bin:
    macro_tab = None

    def __init__(self):
        print(self.fname)
        with open('vp2/bin-' + self.fname, 'rb') as f:
            self.bin = f.read()
        self.code = Section(0xd0000000, self.bin)
        data_base = self.code.get(0xd000000c, 4)
        self.data = Section(0xb0000000, self.bin[data_base - 0xd0000000:])
        self.macros = []
        if self.macro_tab is not None:
            for entry in range(self.macro_tab.start, self.macro_tab.stop, 0xc):
                code = self.code.get(entry, 4)
                len_ = self.code.get(entry + 4, 4)
                ptr = self.code.get(entry + 8, 4)
                self.macros.append((code, len_, ptr))
                print("    {:08x} {:08x} {:08x}".format(code, len_, ptr))
                if len_:
                    try:
                        block = Block('macro_{:x}'.format(code), vp2macroisa, self.code, code, code + len_)
                        block.print()
                    except DecodeError as err:
                        print("    Decode error: {}".format(err))
        print()


class Vp2Scaler(Vp2Bin):
    fname = 'scaler'
    macro_tab = slice(0xd0003628, 0xd0003730)


class Vp2Scrambler(Vp2Bin):
    fname = 'histogram'


class Vp2Histogram(Vp2Bin):
    fname = 'histogram'


class Vp2Deblock(Vp2Bin):
    fname = 'deblock'


class Vp2Mpeg(Vp2Bin):
    fname = 'mpeg2'
    macro_tab = slice(0xd0005c70, 0xd0005d3c)


class Vp2H264(Vp2Bin):
    fname = 'h264-dec'
    macro_tab = slice(0xd0006038, 0xd0006110)


class Vp2H264Deblock(Vp2Bin):
    fname = 'h264-deblock'
    macro_tab = slice(0xd00070a0, 0xd0007238)


class Vp2VC1(Vp2Bin):
    fname = 'vc1-dec'
    macro_tab = slice(0xd0009520, 0xd0009778)


class Vp2VC1IDCT(Vp2Bin):
    fname = 'vc1-idct'


class Vp2VC1Deblock(Vp2Bin):
    fname = 'vc1-deblock'
    macro_tab = slice(0xd0002948, 0xd00029c0)


class Vp2VC1PP(Vp2Bin):
    fname = 'vc1-pp'
    macro_tab = slice(0xd0000958, 0xd0000988)

vp2files = [
    Vp2Scaler(), Vp2Scrambler(), Vp2Histogram(),
    Vp2Mpeg(),
    Vp2H264(), Vp2H264Deblock(),
    Vp2VC1(), Vp2VC1IDCT(), Vp2VC1Deblock(), Vp2VC1PP()
]
