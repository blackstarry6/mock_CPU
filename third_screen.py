"""第三个程序：真·模拟屏幕——帧缓冲（framebuffer）+ 输出端口三件套。

与 second_hello.py 的流式打印（teletype：写一个打一个）相对，本程序演示
C64 式的显存模型：内存里的一片区域（0x90~0x9F 共 16 字节）"就是"屏幕，
程序随便写、随便改，渲染器读这片内存画出当前内容——屏幕显示的是
"存着什么"，而不是"来过什么"。

设备约定（CPU 一概不知情）：
  0x90~0x9F  帧缓冲：16 个单元格，各存一个字符
  0xFE       字符流端口：写字节 = 打印该字符（second_hello 的机制）
  0xFD       回车端口：写任意字节 = 换行

程序流程：先流式打印标题 "DEMO:" 并回车，再用自修改代码逐格填充帧缓冲
（'·' → '#'），驱动端每圈渲染一次——可以看到屏幕被"就地"更新，这是
帧缓冲相对流式输出的本质能力（能改写历史，而不只是往下追加）。
"""
import time

from CPU import isa
from CPU.cpu import CPU
from MEM.ram import RAM


class ScreenRAM(RAM):
    FB_BASE, FB_SIZE = 0x90, 16
    PORT_CHAR, PORT_NEWLINE = 0xFE, 0xFD

    def write(self, addr, value):
        super().write(addr, value)
        a = addr & 0xFF
        if a == self.PORT_CHAR:
            print(chr(value & 0xFF), end="", flush=True)
        elif a == self.PORT_NEWLINE:
            print()


def render(ram):
    """渲染器：把帧缓冲的 16 个字节画成一个带边框的"屏幕行"。"""
    row = "".join(chr(b) if 32 <= b < 127 else "·"
                  for b in (ram.read(ScreenRAM.FB_BASE + i)
                            for i in range(ScreenRAM.FB_SIZE)))
    print("+" + "-" * ScreenRAM.FB_SIZE + "+")
    print("|" + row + "|")
    print("+" + "-" * ScreenRAM.FB_SIZE + "+")


prog = (
    # ---- 流式打印标题（teletype 模型）----
    isa.I_LDI(0, ord("D")) + isa.I_ST(0, 0xFE) +     # 0x00/0x02
    isa.I_LDI(0, ord("E")) + isa.I_ST(0, 0xFE) +     # 0x04/0x06
    isa.I_LDI(0, ord("M")) + isa.I_ST(0, 0xFE) +     # 0x08/0x0A
    isa.I_LDI(0, ord("O")) + isa.I_ST(0, 0xFE) +     # 0x0C/0x0E
    isa.I_LDI(0, ord(":")) + isa.I_ST(0, 0xFE) +     # 0x10/0x12
    isa.I_LDI(0, 0) + isa.I_ST(0, 0xFD) +            # 0x14/0x16 回车端口
    # ---- 帧缓冲动画（framebuffer 模型）----
    isa.I_LDI(1, 0x90 + 16) +        # 0x18: R1 = 结束地址 0xA0
    isa.I_LDI(2, 0x90) +             # 0x1A: R2 = 当前格地址
    isa.I_LDI(0, ord("#")) +         # 0x1C: R0 = '#'
    isa.I_ST(0, 0x90) +              # 0x1E: 写当前格 ← 这条指令被自改写
    isa.I_UN("INC", 2) +             # 0x20: 指针 +1
    isa.I_ST(2, 0x1F) +              # 0x22: 指针写回 0x1F（上面 ST 的地址字节）
    isa.I_ALU("CMP", 2, 1) +         # 0x24: 填满了吗
    isa.I_JMP("JNZ", 0x1E) +         # 0x26
    isa.I_HALT()                     # 0x28
)

cpu = CPU()
cpu.ram = ScreenRAM()
cpu.ram.load_program(prog)
cpu.clk.attach(cpu.ram)

for _ in range(15):                  # 流式 12 条 + 帧缓冲初始化 3 条
    cpu.step()
render(cpu.ram)                      # 初始画面：16 格全 '·'
while not cpu.halted:
    for _ in range(5):               # 循环体恰好 5 条指令一圈
        if not cpu.step():
            break
    render(cpu.ram)
    time.sleep(0.1)
