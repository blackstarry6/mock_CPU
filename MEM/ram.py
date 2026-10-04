"""256 字节同步 RAM：读组合、写打拍。

与 SEQ 的时序纪律一致：
- read() 是导线直通，随时可读，读到当前存储值（写打拍前为旧值）
- write() 只是登记写请求，tick() 时钟沿统一提交（一次性消费，
  多次登记以最后一次为准——单写端口的导线语义）
真实 CPU 的片上 RAM 也多为同步写，与该模型吻合。

load_program() 用于初始化批量装载（相当于烧写 ROM）：
直接写入存储阵列，不经时钟，仅限初始化时使用。
"""


class RAM:
    def __init__(self, size=256, width=8):
        assert size & (size - 1) == 0, "容量必须是 2 的幂"
        self.size = size
        self.addr_mask = size - 1
        self.value_mask = (1 << width) - 1
        self.data = [0] * size
        self._we = 0
        self._addr = 0
        self._value = 0

    def read(self, addr):
        """读端口（组合）：按地址读一个字节，地址自动截断。"""
        return self.data[addr & self.addr_mask]

    def write(self, addr, value):
        """写端口（登记）：请求在下一个时钟沿写入。"""
        self._addr = addr & self.addr_mask
        self._value = value & self.value_mask
        self._we = 1

    def tick(self):
        """时钟沿：提交登记的写请求。"""
        if self._we:
            self.data[self._addr] = self._value
            self._we = 0

    def load_program(self, program, base=0):
        """烧写：把字节序列写入以 base 起始的单元，直接生效。"""
        for i, byte in enumerate(program):
            self.data[(base + i) & self.addr_mask] = byte & self.value_mask
