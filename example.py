#!/usr/bin/env python3

from envy.section import ImageSection
from envy.isa.falcon import FalconIsa
from envy.deco.world import World, Domain


class ExampleBin(World):
    def __init__(self):
        super().__init__()
        with open('example.bin', 'rb') as f:
            code = ImageSection(0, f.read())
        isa = FalconIsa(3)
        domain = Domain(self, isa)
        self.domains.append(domain)
        self.sections.append(code)
        domain.add_section(isa.codemem, code)
        func = domain.find_function(0)
        func.name = 'entry'
        func.want_reg(isa.r[0], 0xffffffff)

world = ExampleBin()
world.process()
world.print()
