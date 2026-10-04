"""程序计数器（PC）：控制取指位置的专用寄存器。

下一拍来源有两种（对应数据通路上的一个 MUX）：
- incr()：顺序执行，PC+1——刻意经 add8 加法器实现（真实 CPU 的 PC 自增
  也走加法器），8 位自然回绕 255→0
- load(target)：跳转，装载目标地址
同一拍两者都调用时后调覆盖先调（DFF 导线语义）；约定控制器每拍只调一个。
"""
from ALU.full_adder import add8
from .register import Register


class ProgramCounter:
    def __init__(self, width=8, init=0):
        self.reg = Register("PC", width=width, init=init)

    @property
    def value(self):
        """当前取指地址（组合读）。"""
        return self.reg.value

    def incr(self):
        """声明下一拍 PC+1（经 8 位加法器，进位丢弃实现回绕）。"""
        nxt, _carry, _c6 = add8(self.reg.value, 1)
        self.reg.d(nxt)

    def load(self, target):
        """声明下一拍装载跳转目标地址。"""
        self.reg.d(target)

    def tick(self):
        self.reg.tick()
