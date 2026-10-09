"""第四个程序：16 位多字节加减法——在没有 ADC/SBB 的机器上手工传进位。

核心难题：进位要跨字节传递，但每条 ADD/SUB 都会覆盖 C 标志。
解法：进位不放标志里，放寄存器 R2 里传递。每个字节的带进位加法：

    ADD R0, R1            ; 第一步：a+b，C=c0（立即分支存进 R2）
    再把 cin（R4 暂存）加上：R0==255 时会再进位（回绕），否则安全 +1
    进位输出 = c0 OR (cin 且 回绕)

减法对偶：SUB 的 C 是"借位取反"（C=0 表示借位），借位放 R2 传递，
再减 bin 时 R0==0 会再借位（回绕成 255）。

写完这个程序就会由衷理解：真实 CPU 为什么都有 ADC/SBB 指令——
每字节 14 条指令的活，一条 ADC 就是 2 条。

内存布局：A=0xA0~A1，B=0xA2~A3（低字节在前）
          和=0xB0~B1（最高进位在 0xB2），差=0xB4~B5（借位在 0xB6）
寄存器：R0/R1 当前字节，R2 进/借位，R4 暂存 cin，R5/R6/R7 = 0/1/255
"""
from CPU import isa
from CPU.cpu import CPU

A, B = 0xA0, 0xA2
SUM, DIFF = 0xB0, 0xB4

prog = (
    isa.I_LDI(5, 0) +                # 0x00: R5 = 常数 0
    isa.I_LDI(6, 1) +                # 0x02: R6 = 常数 1
    isa.I_LDI(7, 255) +              # 0x04: R7 = 常数 255
    # ================= 16 位加法 =================
    isa.I_LDI(2, 0) +                # 0x06: 进位 cin = 0
    isa.I_LD(0, A) +                 # 0x08: R0 = a 低字节
    isa.I_LD(1, B) +                 # 0x0A: R1 = b 低字节
    isa.I_MOV(4, 2) +                # 0x0C: R4 = cin（暂存）
    isa.I_ALU("ADD", 0, 1) +         # 0x0E: R0 = (a+b)&255，C=c0
    isa.I_LDI(2, 0) +                # 0x10: cout 默认 0
    isa.I_JMP("JC", 0x16) +          # 0x12: c0=1 → 置 1
    isa.I_JMP("JMP", 0x18) +         # 0x14
    isa.I_LDI(2, 1) +                # 0x16
    isa.I_ALU("CMP", 4, 5) +         # 0x18: cin==0？→ 本字节完成
    isa.I_JMP("JZ", 0x28) +          # 0x1A
    isa.I_ALU("CMP", 0, 7) +         # 0x1C: R0==255？+1 会回绕
    isa.I_JMP("JZ", 0x24) +          # 0x1E
    isa.I_ALU("ADD", 0, 6) +         # 0x20: 安全 +1
    isa.I_JMP("JMP", 0x28) +         # 0x22
    isa.I_LDI(0, 0) +                # 0x24: 255+1 → 0（回绕）
    isa.I_LDI(2, 1) +                # 0x26: 再进位
    isa.I_ST(0, SUM) +               # 0x28: 存和低字节
    isa.I_LD(0, A + 1) +             # 0x2A: 高字节（cin=上次的 cout）
    isa.I_LD(1, B + 1) +             # 0x2C
    isa.I_MOV(4, 2) +                # 0x2E
    isa.I_ALU("ADD", 0, 1) +         # 0x30
    isa.I_LDI(2, 0) +                # 0x32
    isa.I_JMP("JC", 0x38) +          # 0x34
    isa.I_JMP("JMP", 0x3A) +         # 0x36
    isa.I_LDI(2, 1) +                # 0x38
    isa.I_ALU("CMP", 4, 5) +         # 0x3A
    isa.I_JMP("JZ", 0x4A) +          # 0x3C
    isa.I_ALU("CMP", 0, 7) +         # 0x3E
    isa.I_JMP("JZ", 0x46) +          # 0x40
    isa.I_ALU("ADD", 0, 6) +         # 0x42
    isa.I_JMP("JMP", 0x4A) +         # 0x44
    isa.I_LDI(0, 0) +                # 0x46
    isa.I_LDI(2, 1) +                # 0x48
    isa.I_ST(0, SUM + 1) +           # 0x4A: 存和高字节
    isa.I_ST(2, SUM + 2) +           # 0x4C: 存最高进位（16 位溢出标志）
    # ================= 16 位减法 =================
    isa.I_LDI(2, 0) +                # 0x4E: 借位 bin = 0
    isa.I_LD(0, A) +                 # 0x50
    isa.I_LD(1, B) +                 # 0x52
    isa.I_MOV(4, 2) +                # 0x54: R4 = bin
    isa.I_ALU("SUB", 0, 1) +         # 0x56: C=0 表示借位
    isa.I_LDI(2, 0) +                # 0x58: bout 默认 0
    isa.I_JMP("JNC", 0x5E) +         # 0x5A: 借位 → 置 1
    isa.I_JMP("JMP", 0x60) +         # 0x5C
    isa.I_LDI(2, 1) +                # 0x5E
    isa.I_ALU("CMP", 4, 5) +         # 0x60: bin==0？→ 完成
    isa.I_JMP("JZ", 0x70) +          # 0x62
    isa.I_ALU("CMP", 0, 5) +         # 0x64: R0==0？−1 会回绕
    isa.I_JMP("JZ", 0x6C) +          # 0x66
    isa.I_ALU("SUB", 0, 6) +         # 0x68: 安全 −1
    isa.I_JMP("JMP", 0x70) +         # 0x6A
    isa.I_LDI(0, 255) +              # 0x6C: 0−1 → 255（回绕）
    isa.I_LDI(2, 1) +                # 0x6E: 再借位
    isa.I_ST(0, DIFF) +              # 0x70: 存差低字节
    isa.I_LD(0, A + 1) +             # 0x72: 高字节
    isa.I_LD(1, B + 1) +             # 0x74
    isa.I_MOV(4, 2) +                # 0x76
    isa.I_ALU("SUB", 0, 1) +         # 0x78
    isa.I_LDI(2, 0) +                # 0x7A
    isa.I_JMP("JNC", 0x80) +         # 0x7C
    isa.I_JMP("JMP", 0x82) +         # 0x7E
    isa.I_LDI(2, 1) +                # 0x80
    isa.I_ALU("CMP", 4, 5) +         # 0x82
    isa.I_JMP("JZ", 0x92) +          # 0x84
    isa.I_ALU("CMP", 0, 5) +         # 0x86
    isa.I_JMP("JZ", 0x8E) +          # 0x88
    isa.I_ALU("SUB", 0, 6) +         # 0x8A
    isa.I_JMP("JMP", 0x92) +         # 0x8C
    isa.I_LDI(0, 255) +              # 0x8E
    isa.I_LDI(2, 1) +                # 0x90
    isa.I_ST(0, DIFF + 1) +          # 0x92: 存差高字节
    isa.I_ST(2, DIFF + 2) +          # 0x94: 存借位标志
    isa.I_HALT()                     # 0x96
)


def poke(ram, addr, values):
    """初始化用：直接写内存数组（相当于烧写，不走时钟）。"""
    for i, v in enumerate(values):
        ram.data[(addr + i) & 0xFF] = v & 0xFF


def run_case(a, b):
    cpu = CPU(prog)
    poke(cpu.ram, A, [a & 0xFF, a >> 8])       # 低字节在前
    poke(cpu.ram, B, [b & 0xFF, b >> 8])
    n, halted = cpu.run()
    s = cpu.ram.read(SUM) | cpu.ram.read(SUM + 1) << 8
    d = cpu.ram.read(DIFF) | cpu.ram.read(DIFF + 1) << 8
    return s, cpu.ram.read(SUM + 2), d, cpu.ram.read(DIFF + 2), halted


CASES = [
    (0x01FF, 0x0002),   # 低字节进位链：FF+02 进位
    (0x00FF, 0x0001),   # 经典 00FF+1
    (0xFFFF, 0x0001),   # 16 位溢出：和回绕成 0，最高进位=1
    (0x0000, 0x0001),   # 减法借位链：0−1 = 0xFFFF，借位=1
    (0x1234, 0xCDEF),   # 普通值
    (60000, 10000),     # 十进制直观：和溢出
]

fails = 0
print(f"{'A':>7} {'B':>7} │ {'A+B':>8} {'进位':>4} │ {'A−B':>8} {'借位':>4} │ 判定")
print("─" * 62)
for a, b in CASES:
    s, sc, d, db, halted = run_case(a, b)
    es, esc = (a + b) & 0xFFFF, int(a + b > 0xFFFF)
    ed, edb = (a - b) & 0xFFFF, int(a < b)
    ok = (s, sc, d, db, halted) == (es, esc, ed, edb, True)
    fails += not ok
    print(f"{a:#07x} {b:#07x} │ {s:#08x} {sc:4d} │ {d:#08x} {db:4d} │"
          f" {'✓' if ok else '✗ 期望 ' + hex(es) + f'({esc}) ' + hex(ed) + f'({edb})'}")
print("─" * 62)
print("全部通过 ✓" if fails == 0 else f"{fails} 例失败 ✗")
