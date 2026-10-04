"""8 x 8 位寄存器堆：双读端口（MUX）+ 单写端口（译码器）。

结构对应真实寄存器堆：
- 读端口是纯组合逻辑——mux_word 内部"译码器产 one-hot + AND-OR 阵列选择"，
  不经过时钟，随时可读，读到的永远是当前值（打拍前的旧值）
- 写端口：write() 用译码器的 one-hot 只让被寻址的寄存器收到 d()，
  其余保持；实际写入发生在 tick() 时钟沿
- 同拍读旧写新：先 write() 再 read() 同一地址，读到的仍是旧值
"""
from COMB.decoder import decode
from COMB.mux import mux_word
from .register import Register


class RegisterFile:
    """count 个 width 位寄存器（count 需为 2 的幂）。"""

    def __init__(self, count=8, width=8):
        assert count & (count - 1) == 0, "寄存器数量必须是 2 的幂"
        self.count = count
        self.width = width
        self.sel_bits = count.bit_length() - 1
        self.regs = [Register(f"R{i}", width=width) for i in range(count)]

    def read(self, addr):
        """读端口（组合）：译码 + 选择阵列，从 count 个寄存器中选出当前值。"""
        return mux_word([r.value for r in self.regs],
                        addr & (self.count - 1), self.width)

    def write(self, addr, value):
        """写端口（声明）：仅被寻址的寄存器收到数据，时钟沿才生效。"""
        onehot = decode(addr & (self.count - 1), self.sel_bits)
        for reg, sel in zip(self.regs, onehot):
            if sel:
                reg.d(value)

    def tick(self):
        for reg in self.regs:
            reg.tick()
