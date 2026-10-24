"""第四个程序 v2：用 ADC/SBB 重写多字节加减法（v1 见 fourth_multibyte.py，原样保留）。

v1 在没有带进位指令的机器上手工传进位：每字节 14 条、整机 76 条。
本机补上 ADC/SBB 后同一件事 25 条——而且语义直接写进指令：
ADC = "加完顺手吃掉上次的进位"，C 标志在字节之间自动接力。

借位惯例（本机与 6502/ARM 同派）：SUB 后 C=1 表示无借位，因此 SBB
的进位输入恰好就是 C 本身（x86 的 CF=1 表示借位，那边要取反）。

三幕：
  第一幕  16 位加减法——与 v1 相同的用例与内存布局，期望值 Python 直算
  第二幕  翻车现场——指针循环版差在哪：INC/DEC 会重写 C，进位链断在
          指针步进上（x86 的 INC/DEC 保全 CF、6502 的 INX/INY 不碰 C、
          Z80 的 INC r 不碰 Cy——真 ISA 专门为多精度循环留了这条活路）
  第三幕  32 位展开链——LD/ADC/ST 每字节 4 条；64 位、256 位照葫芦画瓢

内存布局：第一幕与 v1 一致（A=0xA0~A1，B=0xA2~A3，低字节在前，
和=0xB0~B2，差=0xB4~B6）；第二/三幕 A32=0xC0~C3，B32=0xC4~C7，
和=0xC8~CC（最高进位在 0xCC）。
"""
from CPU import isa
from CPU.cpu import CPU

A, B = 0xA0, 0xA2
SUM, DIFF = 0xB0, 0xB4
A32, B32, S32 = 0xC0, 0xC4, 0xC8


def poke(ram, addr, values):
    """初始化用：直接写内存数组（相当于烧写，不走时钟）。"""
    for i, v in enumerate(values):
        ram.data[(addr + i) & 0xFF] = v & 0xFF


# ================= 第一幕：16 位加减法（v1 的 76 条 → 25 条） =================

prog16 = (
    # ---- 16 位加法：12 条（v1 同一段 36 条）----
    isa.I_LD(0, A) +                # 0x00: R0 = a 低字节
    isa.I_LD(1, B) +                # 0x02: R1 = b 低字节
    isa.I_ALU("ADD", 0, 1) +        # 0x04: 低字节和，C=c0
    isa.I_ST(0, SUM) +              # 0x06
    isa.I_LD(0, A + 1) +            # 0x08: 高字节
    isa.I_LD(1, B + 1) +            # 0x0A
    isa.I_ADC(0, 1) +               # 0x0C: 高字节 + c0，C=16 位进位
    isa.I_ST(0, SUM + 1) +          # 0x0E
    isa.I_LDI(0, 0) +               # 0x10: 0+0+C = C——ALU 兼职"标志搬运工"
    isa.I_LDI(1, 0) +               # 0x12
    isa.I_ADC(0, 1) +               # 0x14
    isa.I_ST(0, SUM + 2) +          # 0x16: 最高进位
    # ---- 16 位减法：12 条 ----
    isa.I_LD(0, A) +                # 0x18
    isa.I_LD(1, B) +                # 0x1A
    isa.I_ALU("SUB", 0, 1) +        # 0x1C: C=0 表示低字节借位
    isa.I_ST(0, DIFF) +             # 0x1E
    isa.I_LD(0, A + 1) +            # 0x20
    isa.I_LD(1, B + 1) +            # 0x22
    isa.I_SBB(0, 1) +               # 0x24: 再减去借位
    isa.I_ST(0, DIFF + 1) +         # 0x26
    isa.I_LDI(0, 0) +               # 0x28: 借位默认 0
    isa.I_JMP("JC", 0x2E) +         # 0x2A: C=1（无借位）→ 跳过
    isa.I_LDI(0, 1) +               # 0x2C: C=0 → 借位 1
    isa.I_ST(0, DIFF + 2) +         # 0x2E: 取 NOT C 没有单指令技巧
    isa.I_HALT())                   # 0x30: 合计 25 条
# 注：借位（=NOT C）只能老实分支。ADC/SBB 都随 C 单调增，凑不出 1−C；
# x86 那边正相反——CF 本身就是借位，0+0+CF 一步搬出借位。惯例决定哪头便宜。


def run_case(a, b):
    cpu = CPU(prog16)
    poke(cpu.ram, A, [a & 0xFF, a >> 8])       # 低字节在前（与 v1 一致）
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
print("第一幕：16 位加减法（与 v1 同用例、同布局，逐字节差分）")
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
print("第一幕全部通过 ✓" if fails == 0 else f"第一幕 {fails} 例失败 ✗")

# ================= 第二幕：翻车现场——指针循环版必须翻车 =================
# 看似最优雅的写法：LDX/STX 指针 + ADC 进位链，首字节展开做 ADD，
# 循环体每字节 9 条。但循环体里的 INC×3 与 DEC 都会重写 C——
# 进位链断在指针步进上。

buggy = (
    isa.I_LDI(2, A32) +             # 0x00: A 指针
    isa.I_LDI(3, B32) +             # 0x02: B 指针
    isa.I_LDI(4, S32) +             # 0x04: 和指针
    isa.I_LDI(5, 3) +               # 0x06: 计数（首字节已展开，剩 3 字节）
    isa.I_LDX(0, 2) +               # 0x08: 首字节：ADD 建立进位链
    isa.I_LDX(1, 3) +               # 0x0A
    isa.I_ALU("ADD", 0, 1) +        # 0x0C
    isa.I_STX(0, 4) +               # 0x0E
    isa.I_UN("INC", 2) +            # 0x10: 指针步进
    isa.I_UN("INC", 3) +            # 0x12
    isa.I_UN("INC", 4) +            # 0x14
    isa.I_LDX(0, 2) +               # 0x16: 循环体开始
    isa.I_LDX(1, 3) +               # 0x18
    isa.I_ADC(0, 1) +               # 0x1A: ★ 想吃上一次的 C……
    isa.I_STX(0, 4) +               # 0x1C
    isa.I_UN("INC", 2) +            # 0x1E: ……但 INC/DEC 全都重写 C
    isa.I_UN("INC", 3) +            # 0x20
    isa.I_UN("INC", 4) +            # 0x22
    isa.I_UN("DEC", 5) +            # 0x24
    isa.I_JMP("JNZ", 0x16) +        # 0x26
    isa.I_LDI(0, 0) +               # 0x28: 最高进位 → mem[R4]（恰为 0xCC）
    isa.I_LDI(1, 0) +               # 0x2A
    isa.I_ADC(0, 1) +               # 0x2C
    isa.I_STX(0, 4) +               # 0x2E
    isa.I_HALT())                   # 0x30

print("\n第二幕：翻车现场——指针循环版（看似最优雅，实则必然翻车）")
a, b = 0x000000FF, 0x00000001
cpu = CPU(buggy)
poke(cpu.ram, A32, [a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0xFF, (a >> 24) & 0xFF])
poke(cpu.ram, B32, [b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF, (b >> 24) & 0xFF])
cpu.run()
got = sum(cpu.ram.read(S32 + i) << (8 * i) for i in range(4))
carry = cpu.ram.read(S32 + 4)
want = (a + b) & 0xFFFFFFFF
repro = (got, carry) == (0x01010000, 1)
print(f"  0x{a:08X} + 0x{b:08X}")
print(f"  机器算出 0x{got:08X}（最高进位 {carry}）   期望 0x{want:08X}（最高进位 0）")
print(f"  {'（翻车可复现 ✓ 病灶确认）' if repro else '（翻车方式与预期不符，请回看第二幕注释）'}")
print("  病灶（两种坏法一次全齐）：")
print("    ① 字节 1 丢了真进位——首字节 ADD 产出的 C=1，被随后的")
print("       三个 INC 抹成 0（本例 0x00FF+1 的高字节本该是 0x01）；")
print("    ② 字节 2、3 和最高进位各吃一个假进位——计数器 DEC 每轮")
print("       无借位，把 C 置回 1，链条变成'从此每字节都进位'。")
print("  修法：x86 的 INC/DEC 保全 CF、6502 的 INX/INY 不碰 C、")
print("        Z80 的 INC r 不碰 Cy——真 ISA 专门给多精度循环留活路。")
print("        本机 INC/DEC 的'C 保持'选项记入后续工作。")

# ================= 第三幕：32 位展开链（每字节 4 条） =================

prog32 = (
    # 每字节 LD/LD/ADC/ST（首字节 ADD）——v1 每字节 14 条还不能循环
    isa.I_LD(0, A32) + isa.I_LD(1, B32) +
    isa.I_ALU("ADD", 0, 1) + isa.I_ST(0, S32) +            # 0x00-0x06: 字节 0
    isa.I_LD(0, A32 + 1) + isa.I_LD(1, B32 + 1) +
    isa.I_ADC(0, 1) + isa.I_ST(0, S32 + 1) +               # 0x08-0x0E: 字节 1
    isa.I_LD(0, A32 + 2) + isa.I_LD(1, B32 + 2) +
    isa.I_ADC(0, 1) + isa.I_ST(0, S32 + 2) +               # 0x10-0x16: 字节 2
    isa.I_LD(0, A32 + 3) + isa.I_LD(1, B32 + 3) +
    isa.I_ADC(0, 1) + isa.I_ST(0, S32 + 3) +               # 0x18-0x1E: 字节 3
    isa.I_LDI(0, 0) + isa.I_LDI(1, 0) +
    isa.I_ADC(0, 1) + isa.I_ST(0, S32 + 4) +               # 0x20-0x26: 最高进位
    isa.I_HALT())                                           # 0x28: 合计 21 条


def run32(a, b):
    cpu = CPU(prog32)
    poke(cpu.ram, A32, [a & 0xFF, a >> 8 & 0xFF, a >> 16 & 0xFF, a >> 24 & 0xFF])
    poke(cpu.ram, B32, [b & 0xFF, b >> 8 & 0xFF, b >> 16 & 0xFF, b >> 24 & 0xFF])
    n, halted = cpu.run()
    s = sum(cpu.ram.read(S32 + i) << (8 * i) for i in range(4))
    return s, cpu.ram.read(S32 + 4), halted


CASES32 = [
    (0xFFFFFFFF, 0x00000001),   # 全链进位：4 字节接力，和回绕成 0
    (0x00FFFFFF, 0x00000001),   # 进位穿 3 个字节
    (0x000000FF, 0x00000001),   # 经典 FF+1（第一幕的 32 位版）
    (0x12345678, 0x87654321),   # 每字节都不进位，和 = 0x99999999
    (0xDEADBEEF, 0x00000001),   # 低字节不进位，链路安静
    (0x00000000, 0x00000000),   # 全零
]

fails32 = 0
print("\n第三幕：32 位展开链（LD/ADC/ST 每字节 4 条，差分对 Python）")
print(f"{'A':>11} {'B':>11} │ {'A+B':>11} {'进位':>4} │ 判定")
print("─" * 58)
for a, b in CASES32:
    s, sc, halted = run32(a, b)
    es, esc = (a + b) & 0xFFFFFFFF, int(a + b > 0xFFFFFFFF)
    ok = (s, sc, halted) == (es, esc, True)
    fails32 += not ok
    print(f" 0x{a:08X}  0x{b:08X} │   0x{s:08X} {sc:4d} │"
          f" {'✓' if ok else '✗ 期望 0x%08X(%d)' % (es, esc)}")
print("─" * 58)
print("第三幕全部通过 ✓" if fails32 == 0 else f"第三幕 {fails32} 例失败 ✗")

print("\n" + "═" * 62)
print("账本：")
print("  16 位加减法   v1 手工传进位 76 条 → v2 带进位指令 25 条")
print("  32 位加法     每字节 4 条 × 4 + 收尾 5 条 = 21 条（64 位照葫芦画瓢）")
print("  指针循环版    翻车：INC/DEC 重写 C——真 ISA 的 INC 专门保全进位")
