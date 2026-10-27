"""第四个程序 v3：指针循环版多字节加法——"C 保持"修复后的复活验收。

v2（原样保留）第二幕曾展示：指针循环看似最优雅，却因 INC/DEC 重写 C 而
必然翻车（0xFF+1 算出 0x01010000）。修复（INC/DEC 只写 Z/N、C/V 保持——
x86 的 INC 保全 CF、6502 的 INX 不碰 C 同款）之后，同一段程序原地算对。
本文件把那个"翻车程序"一字不改地请回来，给它一个正式的差分验收，
并借参数化推广讲清多精度算术的空间/时间取舍。

三幕：
  第一幕  32 位指针循环差分——v2 第二幕的 25 条程序跑 6 组用例，与 Python 对账
  第二幕  立此存照——同一程序同一输入，修复前（v2 冻结记录）vs 修复后（实跑）
  第三幕  任意位宽与账本——位宽只改一个计数常量：64 位差分 + 256 位全链演示；
          循环版代码恒 25 条但执行 9N+6 条，展开版执行 4N+4 条但体积线性涨
          ——时间与空间第一次分家

内存布局：32 位 A=0xC0~C3 / B=0xC4~C7 / 和=0xC8~CC（与 v2 一致，最高进位在尾）；
          64 位 0xD0~D7 / 0xD8~DF / 0xE0~E8；256 位 0x40~5F / 0x60~7F / 0x80~A0。
"""
from CPU import isa
from CPU.cpu import CPU


def poke(ram, addr, values):
    """初始化用：直接写内存数组（相当于烧写，不走时钟）。"""
    for i, v in enumerate(values):
        ram.data[(addr + i) & 0xFF] = v & 0xFF


def run_loop(prog, a_addr, b_addr, s_addr, nbytes, a, b):
    """跑一组用例：烧入低字节在前的 A、B，返回 (和, 最高进位, 执行条数, 停机)。"""
    cpu = CPU(prog)
    poke(cpu.ram, a_addr, [(a >> (8 * i)) & 0xFF for i in range(nbytes)])
    poke(cpu.ram, b_addr, [(b >> (8 * i)) & 0xFF for i in range(nbytes)])
    n, halted = cpu.run()
    s = sum(cpu.ram.read(s_addr + i) << (8 * i) for i in range(nbytes))
    return s, cpu.ram.read(s_addr + nbytes), n, halted


A32, B32, S32 = 0xC0, 0xC4, 0xC8

# ================= 第一幕：32 位指针循环差分（v2 第二幕的程序，一字不改） =================
# 字节与 fourth_multibyte_v2.py 第二幕完全相同（注释除外——注释不产生字节）；
# 变的不是程序，是机器：INC/DEC 现在只写 Z/N，C 不再被踩。

loop32 = (
    isa.I_LDI(2, A32) +             # 0x00: A 指针
    isa.I_LDI(3, B32) +             # 0x02: B 指针
    isa.I_LDI(4, S32) +             # 0x04: 和指针
    isa.I_LDI(5, 3) +               # 0x06: 计数（首字节已展开，剩 3 字节）
    isa.I_LDX(0, 2) +               # 0x08: 首字节：ADD 建立进位链
    isa.I_LDX(1, 3) +               # 0x0A
    isa.I_ALU("ADD", 0, 1) +        # 0x0C
    isa.I_STX(0, 4) +               # 0x0E
    isa.I_UN("INC", 2) +            # 0x10: 指针步进——修复后不再踩 C
    isa.I_UN("INC", 3) +            # 0x12
    isa.I_UN("INC", 4) +            # 0x14
    isa.I_LDX(0, 2) +               # 0x16: 循环体开始
    isa.I_LDX(1, 3) +               # 0x18
    isa.I_ADC(0, 1) +               # 0x1A: ★吃上一次的 C——现在真的吃得到
    isa.I_STX(0, 4) +               # 0x1C
    isa.I_UN("INC", 2) +            # 0x1E
    isa.I_UN("INC", 3) +            # 0x20
    isa.I_UN("INC", 4) +            # 0x22
    isa.I_UN("DEC", 5) +            # 0x24: 计数——同样只写 Z/N
    isa.I_JMP("JNZ", 0x16) +        # 0x26
    isa.I_LDI(0, 0) +               # 0x28: 0+0+C = 最高进位 → mem[R4]
    isa.I_LDI(1, 0) +               # 0x2A
    isa.I_ADC(0, 1) +               # 0x2C
    isa.I_STX(0, 4) +               # 0x2E
    isa.I_HALT())                   # 0x30

CASES32 = [
    (0xFFFFFFFF, 0x00000001),   # 全链进位：4 字节接力，和回绕成 0
    (0x00FFFFFF, 0x00000001),   # 进位穿 3 个字节
    (0x000000FF, 0x00000001),   # 经典 FF+1（第二幕的主角）
    (0x12345678, 0x87654321),   # 每字节都不进位，和 = 0x99999999
    (0xDEADBEEF, 0x00000001),   # 低字节不进位，链路安静
    (0x00000000, 0x00000000),   # 全零
]

fails = 0
print("第一幕：32 位指针循环差分（v2 第二幕的程序，一字不改）")
print(f"{'A':>11} {'B':>11} │ {'A+B':>11} {'进位':>4} {'执行':>4} │ 判定")
print("─" * 66)
for a, b in CASES32:
    s, sc, n, h = run_loop(loop32, A32, B32, S32, 4, a, b)
    es, esc = (a + b) & 0xFFFFFFFF, int(a + b > 0xFFFFFFFF)
    ok = (s, sc, h) == (es, esc, True)
    fails += not ok
    print(f" 0x{a:08X}  0x{b:08X} │   0x{s:08X} {sc:4d} {n:4d} │"
          f" {'✓' if ok else '✗ 期望 0x%08X(%d)' % (es, esc)}")
print("─" * 66)
print("第一幕全部通过 ✓" if fails == 0 else f"第一幕 {fails} 例失败 ✗")

# ================= 第二幕：立此存照——同一个程序，两种机器 =================

print("\n第二幕：立此存照——同一个程序，两种机器")
a, b = 0x000000FF, 0x00000001
s, sc, n, h = run_loop(loop32, A32, B32, S32, 4, a, b)
want = (a + b) & 0xFFFFFFFF
print(f"  程序：上方 25 条指针循环（= v2 第二幕）    输入：0x{a:08X} + 0x{b:08X}")
print(f"  ┌ 修复前  INC/DEC 写全部四标志 → 0x01010000（最高进位 1）✗   [v2 冻结记录]")
fixed_ok = (s, sc) == (want, 0)
print(f"  └ 修复后  INC/DEC 只写 Z/N     → 0x{s:08X}（最高进位 {sc}）"
      f"{'✓ 与期望一致' if fixed_ok else '✗'}   [本机实跑，{n} 条]")
print("  病灶与疗效：")
print("    ① 字节 1 曾丢真进位——三个 INC 把 C 抹成 0；现 INC 保持 C，进位完整抵达")
print("    ② 字节 2、3 曾吃 DEC 的假进位；现 DEC 不写 C，链条安静")
print("  注：修复前的值引自 v2 第二幕的冻结断言——v2 原样保留，")
print("      是修复前机器的历史文档。")

# ================= 第三幕：任意位宽与空间时间账本 =================

def loop_adder(a_addr, b_addr, s_addr, nbytes):
    """参数化指针循环加法器：任意位宽共用同一段 25 条指令的代码。

    位宽不进代码结构、只进数据——计数器初值 = nbytes − 1（首字节已展开）。
    依赖 INC/DEC 的"C 保持"（第一幕验收的修复）。指令布局恒定，JNZ 目标恒 0x16。
    """
    return (isa.I_LDI(2, a_addr) + isa.I_LDI(3, b_addr) + isa.I_LDI(4, s_addr)
            + isa.I_LDI(5, nbytes - 1)              # ★ 位宽只在这里
            + isa.I_LDX(0, 2) + isa.I_LDX(1, 3)
            + isa.I_ALU("ADD", 0, 1) + isa.I_STX(0, 4)
            + isa.I_UN("INC", 2) + isa.I_UN("INC", 3) + isa.I_UN("INC", 4)
            + isa.I_LDX(0, 2) + isa.I_LDX(1, 3)
            + isa.I_ADC(0, 1) + isa.I_STX(0, 4)
            + isa.I_UN("INC", 2) + isa.I_UN("INC", 3) + isa.I_UN("INC", 4)
            + isa.I_UN("DEC", 5) + isa.I_JMP("JNZ", 0x16)
            + isa.I_LDI(0, 0) + isa.I_LDI(1, 0) + isa.I_ADC(0, 1)
            + isa.I_STX(0, 4) + isa.I_HALT())


def unrolled_adder(a_addr, b_addr, s_addr, nbytes):
    """展开链（v2 第三幕的推广）：每字节 LD/LD/ADC/ST，首字节 ADD。"""
    prog = []
    for i in range(nbytes):
        op = isa.I_ALU("ADD", 0, 1) if i == 0 else isa.I_ADC(0, 1)
        prog += isa.I_LD(0, a_addr + i) + isa.I_LD(1, b_addr + i) + op \
            + isa.I_ST(0, s_addr + i)
    prog += (isa.I_LDI(0, 0) + isa.I_LDI(1, 0) + isa.I_ADC(0, 1)
             + isa.I_ST(0, s_addr + nbytes))
    return prog + isa.I_HALT()


print("\n第三幕：任意位宽与空间时间账本")
same = loop_adder(A32, B32, S32, 4) == loop32
print(f"  生成器自检：loop_adder(…, 4) 与第一幕程序逐字节一致 {'✓' if same else '✗'}")

# ---- 64 位差分：与第一幕同一段代码，只改计数常量（3→7）与指针初值 ----
A64, B64, S64 = 0xD0, 0xD8, 0xE0
loop64 = loop_adder(A64, B64, S64, 8)
CASES64 = [
    (0xFFFFFFFFFFFFFFFF, 0x0000000000000001),   # 全链进位：8 字节接力，和回绕成 0
    (0x000000FFFFFFFFFF, 0x0000000000000001),   # 进位穿 5 个字节
    (0x1111111111111111, 0x2222222222222222),   # 每字节都不进位，和 = 0x3333…
    (0x00000000000000FF, 0x0000000000000001),   # 经典 FF+1
    (0xDEADBEEFCAFEBABE, 0x2152411000000002),   # 高 32 位相加恰好全 1
    (0x0000000000000000, 0x0000000000000000),   # 全零
]
fails64 = 0
print("  64 位差分（同一段 25 条代码，LDI R5 改 3→7、指针换地址）：")
print(f"  {'A':>19} {'B':>19} │ {'A+B':>19} {'进位':>4} {'执行':>4} │ 判定")
print("  " + "─" * 74)
for a, b in CASES64:
    s, sc, n, h = run_loop(loop64, A64, B64, S64, 8, a, b)
    es, esc = (a + b) & 0xFFFFFFFFFFFFFFFF, int(a + b > 0xFFFFFFFFFFFFFFFF)
    ok = (s, sc, h) == (es, esc, True)
    fails64 += not ok
    print(f"   0x{a:016X}  0x{b:016X} │     0x{s:016X} {sc:4d} {n:4d} │"
          f" {'✓' if ok else '✗ 期望 0x%016X(%d)' % (es, esc)}")
print("  " + "─" * 74)
print("  64 位全部通过 ✓" if fails64 == 0 else f"  64 位 {fails64} 例失败 ✗")

# ---- 256 位全链演示：程序还是那 25 条 ----
A256, B256, S256 = 0x40, 0x60, 0x80
loop256 = loop_adder(A256, B256, S256, 32)
a, b = 2 ** 256 - 1, 1
s, sc, n256, h = run_loop(loop256, A256, B256, S256, 32, a, b)
ok = (s, sc, h) == (0, 1, True)
print(f"  256 位全链：0xFFFF…FF（64 个 F）+ 1 → 0x{s:064X}")
print(f"  （最高进位 {sc}，执行 {n256} 条）{'✓' if ok else '✗'}")
print("  ——32 个字节的进位接力，程序仍是那 25 条：位宽是数据，不是代码")

# ---- 账本：实测两版的代码体积与执行条数（输入取全 FF + 1） ----
print("\n  空间时间账本（实测）：")
print(f"  {'位宽':>7} │ {'循环代码':>6} {'循环执行':>6} │ {'展开代码':>6} {'展开执行':>6}")
print("  " + "─" * 52)
for nbytes, aa, bb, ss, lp in ((4, A32, B32, S32, loop32),
                               (8, A64, B64, S64, loop64)):
    up = unrolled_adder(aa, bb, ss, nbytes)
    _, _, nl, _ = run_loop(lp, aa, bb, ss, nbytes, (1 << (8 * nbytes)) - 1, 1)
    _, _, nu, _ = run_loop(up, aa, bb, ss, nbytes, (1 << (8 * nbytes)) - 1, 1)
    print(f"  {nbytes * 8:4d} 位 │ {len(lp) // 2:5d} 条 {nl:5d} 条 │"
          f" {len(up) // 2:5d} 条 {nu:5d} 条")
print(f"  256 位 │   25 条 {n256:5d} 条 │    装不下（代码 266 字节 > 256 字节内存）")
print("""
  分家点：N=5（40 位）时两版代码体积打平（25 条 vs 25 条）；此后循环版体积
  恒定、展开版线性涨——展开版的极限约 30 字节（240 位），代码就占满整块
  内存，数据再无立足之地。代价反过来：执行条数展开版永远更少
  （4N+4 vs 9N+6）——时间与空间的取舍，第一次以可测量的方式摆上桌。""")

print("═" * 62)
print("三部曲收官：")
print("  v1 手工传进位  每字节 14 条，不能循环         76 条做 16 位")
print("  v2 展开链      每字节 4 条，体积线性涨         21 条做 32 位")
print("  v3 指针循环    代码恒 25 条，位宽只是数据      25 条做任意位宽（实测 256 位）")
print("  弧线：没有进位指令 → 有了但链条脆 → 链条稳且可循环——多精度算术完全体")
