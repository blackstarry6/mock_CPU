"""第五个程序：软件除法——移位相减（恢复余数法），8 位 ÷ 8 位 = 商 + 余数。

这就是硬件除法器的算法本体（8086 的 DIV 指令在微码里跑的就是它），
我们用通用寄存器和 ALU 轮流扮演除法器的每个部件：

    R=0（余数），Q=被除数；对 8 位各做一轮：
      ① R:Q 整体左移一位（被除数下一位经 C 标志注入 R 的 bit0）
      ② 试减：R ≥ D？→ R -= D，商的本位记 1；否则本位记 0（"恢复"）
    8 轮后：Q 的 8 位全部被商替换（首位商在最高位），R = 余数

关键机制：SHL 把移出位送进 C，JC 分支把它捡起来——C 标志是移位指令
"看进字节内部"的窗口；同拍之内两次 SHL 会覆盖 C，所以两次移位之间
必须用分支把第一位先落地。

寄存器：R0=Q（商），R1=R（余数），R2=D（除数），R3=计数，R4=常数1
内存：被除数 0xA0，除数 0xA1 → 商 0xB0，余数 0xB1（除数为 0 是
未定义行为，与真机一致，本程序不测试）。
"""
from CPU import isa
from CPU.cpu import CPU

DIVIDEND, DIVISOR = 0xA0, 0xA1
QUOT, REM = 0xB0, 0xB1

prog = (
    isa.I_LDI(4, 1) +                # 0x00: R4 = 常数 1
    isa.I_LD(0, DIVIDEND) +          # 0x02: R0 = Q = 被除数
    isa.I_LD(2, DIVISOR) +           # 0x04: R2 = D
    isa.I_LDI(1, 0) +                # 0x06: R1 = R = 0
    isa.I_LDI(3, 8) +                # 0x08: 处理 8 位
    # ---- 循环体：每轮处理一位 ----
    isa.I_UN("SHL", 0) +             # 0x0A: C ← 被除数下一位
    isa.I_JMP("JC", 0x12) +          # 0x0C
    isa.I_UN("SHL", 1) +             # 0x0E: 该位=0：R<<1
    isa.I_JMP("JMP", 0x16) +         # 0x10
    isa.I_UN("SHL", 1) +             # 0x12: 该位=1：R<<1
    isa.I_ALU("ADD", 1, 4) +         # 0x14:       |1（bit0 已腾空，+1 安全）
    isa.I_ALU("CMP", 1, 2) +         # 0x16: R ≥ D？（C=1 即够减）
    isa.I_JMP("JC", 0x1C) +          # 0x18: 够减 → 去减法
    isa.I_JMP("JMP", 0x20) +         # 0x1A: 不够减 → 商本位 0（恢复）
    isa.I_ALU("SUB", 1, 2) +         # 0x1C: R -= D
    isa.I_ALU("ADD", 0, 4) +         # 0x1E: 商本位置 1
    isa.I_UN("DEC", 3) +             # 0x20
    isa.I_JMP("JNZ", 0x0A) +         # 0x22
    # ---- 结果 ----
    isa.I_ST(0, QUOT) +              # 0x24: 商
    isa.I_ST(1, REM) +               # 0x26: 余数
    isa.I_HALT()                     # 0x28
)


def poke(ram, addr, values):
    for i, v in enumerate(values):
        ram.data[(addr + i) & 0xFF] = v & 0xFF


def divide(a, d):
    cpu = CPU(prog)
    poke(cpu.ram, DIVIDEND, [a])
    poke(cpu.ram, DIVISOR, [d])
    n, halted = cpu.run()
    return cpu.ram.read(QUOT), cpu.ram.read(REM), halted


HIGHLIGHT = [
    (100, 7),     # 普通
    (255, 1),     # 最大商
    (255, 255),   # 除数最大
    (7, 100),     # 商为 0
    (0, 5),       # 零被除数
    (200, 130),   # 大除数
    (254, 127),   # 整除
    (129, 128),   # 相邻值
]


def main():
    fails = 0
    print(f"{'被除数':>6} {'除数':>5} │ {'商':>4} {'余数':>4} │ 期望        判定")
    print("─" * 50)
    for a, d in HIGHLIGHT:
        q, r, h = divide(a, d)
        eq, er = divmod(a, d)
        ok = (q, r, h) == (eq, er, True)
        fails += not ok
        print(f"{a:6d} {d:5d} │ {q:4d} {r:4d} │ {eq}...{er}"
              f"   {'✓' if ok else '✗'}")

    # 全矩阵差分：11 × 11 = 121 组
    DIVIDENDS = [0, 1, 2, 7, 100, 127, 128, 129, 200, 254, 255]
    DIVISORS = [1, 2, 3, 7, 100, 127, 128, 129, 130, 200, 255]
    matrix_fails = 0
    for a in DIVIDENDS:
        for d in DIVISORS:
            q, r, h = divide(a, d)
            if (q, r, h) != (*divmod(a, d), True):
                matrix_fails += 1
                print(f"FAIL: {a}/{d} → {q}...{r}，期望 {divmod(a, d)}")
    print("─" * 50)
    print(f"全矩阵 {len(DIVIDENDS) * len(DIVISORS)} 组："
          f"{'全部通过 ✓' if matrix_fails == 0 else f'{matrix_fails} 组失败 ✗'}")


if __name__ == "__main__":
    main()
