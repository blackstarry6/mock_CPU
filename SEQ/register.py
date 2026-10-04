"""8 位寄存器：由 8 个 D 触发器共享时钟组成（结构级组合）。

真实寄存器就是"一排 D 触发器 + 共用时钟线"，因此这里不自建状态变量，
而是直接组合 DFlipFlop——沿用本项目"下层部件搭上层部件"的原则。

写使能语义：调用 d() 即声明本拍写入，不调用即保持（对应真实寄存器堆
的 WE 控制信号：译码器每拍决定哪个寄存器的 WE 为 1）。
"""
from .dff import DFlipFlop


class Register:
    """width 位寄存器，低位在前的 DFlipFlop 列表。"""

    def __init__(self, name="REG", width=8, init=0):
        self.name = name
        self.width = width
        self.bits = [DFlipFlop(init=(init >> i) & 1) for i in range(width)]

    @property
    def value(self):
        """当前输出：各触发器 q 的组装。打拍前永远读到旧值。"""
        return sum(b.q << i for i, b in enumerate(self.bits))

    def d(self, value):
        """数据输入：声明下一个时钟沿写入 value（自动截断到位宽）。"""
        for i, b in enumerate(self.bits):
            b.d((value >> i) & 1)

    def tick(self):
        """时钟上边沿：8 个触发器同时采样。"""
        for b in self.bits:
            b.tick()


if __name__ == "__main__":
    r = Register("R0", init=0x0F)
    print(f"初始值       value = 0b{r.value:08b}")
    r.d(0xA5)
    print(f"d 后打拍前   value = 0b{r.value:08b}（旧值）")
    r.tick()
    print(f"打拍后       value = 0b{r.value:08b}")
    r.tick()
    print(f"无写入再打拍 value = 0b{r.value:08b}（保持）")
