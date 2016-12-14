class ImageSection:
    def __init__(self, base, data):
        self.base = base
        self.data = data
        self.end = base + len(data)
        self.range = range(self.base, self.end)
        self.objects = {}

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            assert idx.step is None
            return self.data[idx.start - self.base:idx.stop - self.base]
        else:
            assert 0

    def get(self, addr, blen):
        offs = addr - self.base
        return int.from_bytes(self.data[offs:offs + blen], 'little')

    def lookup(self, addr):
        if addr not in self.range:
            raise IndexError()
        if addr not in self.objects:
            return []
        return self.objects[addr]

    def attach(self, addr, obj):
        if addr not in self.range:
            raise IndexError()
        if addr not in self.objects:
            self.objects[addr] = []
        self.objects[addr].append(obj)

    def print(self):
        for addr, objects in sorted(self.objects.items()):
            for obj in objects:
                obj.print()
