#!/usr/bin/env python3

from envy.section import ImageSection
from envy.isa.falcon import FalconIsa
from envy.deco.world import World, Domain


class FalconBin(World):
    fname_data = None
    suffix = None

    def __init__(self):
        super().__init__()
        print(self.eng + '/' + self.fname_code)
        rsuf = '-' + self.suffix if self.suffix else ''
        pref = self.eng + '/bin-'
        with open(pref + self.fname_code + rsuf, 'rb') as f:
            code = ImageSection(0, f.read())
        if self.fname_data:
            with open(pref + self.fname_data + rsuf, 'rb') as f:
                data = ImageSection(0, f.read())
        else:
            data = None
        isa = FalconIsa(self.version)
        domain = Domain(self, isa)
        self.domains.append(domain)
        self.sections.append(code)
        if data:
            self.sections.append(data)
        domain.add_section(isa.codemem, code)
        domain.add_section(isa.data, data)
        for entry, name in self.funcs:
            func = domain.find_function(entry)
            if name:
                func.name = name
        self.process()
        self.print()


class PGraphHubGF100(FalconBin):
    eng = 'pgraph'
    fname_code = 'hub-code'
    fname_data = 'hub-data'
    suffix = 'gf100'
    version = 3
    funcs = [
        (0, 'entry'),
        (0x3802, 'mul'),
    ]

grfiles = [PGraphHubGF100()]
