"""第二个程序：让机器打印字符——不给 CPU 增加任何东西。

两个经典概念：
1. 内存映射 I/O：约定某个地址（0xFE）是"控制台端口"，往它写字节
   就显示一个字符。CPU 完全不知道设备的存在——它只是在做普通的 ST。
2. 自修改代码：本机 LD/ST 只有直接地址（没有寄存器间接寻址），
   无法用"指针"遍历字符串。早期程序员的解法：让程序在运行中改写
   自己那条 LD 指令的地址字节（代码与数据同住一片内存——冯·诺依曼结构）。
"""
from CPU import isa
from CPU.cpu import CPU
from MEM.ram import RAM

PORT = 0xFE          # 控制台端口（约定，机器不知道）
TEXT = "HELLO, MOCK_CPU!"
TEXT_BASE = 0x80     # 字符串放这里


class ConsoleRAM(RAM):
    """带控制台的内存：写普通地址照常存储，写端口就把字节显示为字符。"""

    def write(self, addr, value):
        super().write(addr, value)              # 照常登记写请求
        if (addr & 0xFF) == PORT:
            print(chr(value & 0xFF), end="", flush=True)


prog = (
    isa.I_LDI(1, TEXT_BASE + len(TEXT)) +   # 0x00: R1 = 结束地址
    isa.I_LDI(2, TEXT_BASE) +               # 0x02: R2 = 当前字符地址
    isa.I_LD(0, TEXT_BASE) +                # 0x04: R0 = 当前字符 ← 这条指令会被自己改写
    isa.I_ST(0, PORT) +                     # 0x06: 往端口写 R0 = 打印
    isa.I_UN("INC", 2) +                    # 0x08: 指针 +1
    isa.I_ST(2, 0x05) +                     # 0x0A: 把指针写回 0x05（正是上面 LD 的地址字节！）
    isa.I_ALU("CMP", 2, 1) +                # 0x0C: 到末尾了吗
    isa.I_JMP("JNZ", 0x04) +                # 0x0E: 没到则回 0x04
    isa.I_HALT()                            # 0x10
)
prog += [0] * (TEXT_BASE - len(prog))       # 填充到 0x80
prog += [ord(c) for c in TEXT]              # 字符串本体（ASCII 码）

cpu = CPU()                                 # 先造 CPU（用默认内存）
cpu.ram = ConsoleRAM()                      # 换上"带控制台"的内存——设备挂在总线上，CPU 不知情
cpu.ram.load_program(prog)                  # 烧写程序与字符串
cpu.clk.attach(cpu.ram)                     # 挂时钟线（原内存从此再无写声明，空转无害）

n, halted = cpu.run()
print(f"\n[执行 {n} 条指令，停机={halted}]")
