"""第七个程序：Core War 核心大战——蠕虫 vs 轰炸机，同一片内存决斗。

历史：Core War（1984，Redcode/MARS）——两个战士程序共享一片内存轮流执行，
让对手执行到非法指令即胜。最著名的战士 imp 仅一条指令（MOV 0,1），靠
Redcode 专为游戏设计的"PC 随复制前进"爬行。本机是绝对跳转 ISA，纯 imp
不可能（副本里的跳转目标全失效——这也是真实病毒需要相对跳转的原因）。

本对战的两名战士：

  蠕虫（0x00 起）——"常驻引擎 + 蛙跳入口"变体：
    引擎（S0..S8 共 18 字节）永不搬家，所有绝对地址永远有效；
    每代把身体 LDX/STX 拷贝到前方 18 字节，然后 S7 用 STX 把自己 JMP 的
    地址字节改成新副本首址（STX 自修改 + LDX/STX 拷贝，两种新能力联手），
    跳进副本，从副本再蛙跳。沿途留下复制品的痕迹（trail）。

  轰炸机（0xE0 起）——原地扫射：
    循环向 [0x20,0xE0) 投放 0xFE 炸弹（非法操作码，踩中即猝死），
    扫完重装再扫。永远炸不到蠕虫引擎 [0x00,0x18)，也注意不到身后。

竞技场：两颗 CPU 实例共享同一片 RAM（各留自己的寄存器/PC/栈——MARS 的
进程模型），驱动端轮流各走一步。胜负家规：
  - 一方 step() 抛异常（执行到非法指令）→ 对方胜
  - 蠕虫引擎区被改写 → 轰炸机胜；轰炸机机体被改写 → 蠕虫胜
  - 走满 MAX_CYCLES 未分胜负 → 平局
"""
from CPU import isa
from CPU.cpu import CPU
from MEM.ram import RAM

WORM_BASE, WORM_LEN = 0x00, 0x18          # 引擎+入口共 24 字节（前 6 为一次性初始化）
BOMB_BASE, BOMB_LEN = 0xE0, 0x10          # 轰炸机 16 字节
BODY_OFF, BODY_LEN = 0x06, 18             # 蛙跳身体（S0..S8）
SWEEP_START, SWEEP_LEN = 0x20, 0xC0       # 轰炸范围 [0x20,0xE0)

worm = (
    isa.I_LDI(1, WORM_BASE + BODY_OFF) +  # 0x00: 初始化（仅入口执行一次）
    isa.I_LDI(2, WORM_BASE + BODY_OFF + BODY_LEN) +  # 0x02: 目标 = 前方 18 字节
    isa.I_LDI(5, 0x17) +                  # 0x04: S8 那条 JMP 的地址字节位置（永久不变）
    isa.I_LDI(3, BODY_LEN) +              # 0x06: S0 每代重置计数
    isa.I_LDX(4, 1) +                     # 0x08: S1 读自己一字节
    isa.I_STX(4, 2) +                     # 0x0A: S2 写到新家
    isa.I_UN("INC", 1) +                  # 0x0C: S3
    isa.I_UN("INC", 2) +                  # 0x0E: S4
    isa.I_UN("DEC", 3) +                  # 0x10: S5
    isa.I_JMP("JNZ", 0x08) +              # 0x12: S6 绝对回跳——永远指引擎，引擎不搬家所以永远对
    isa.I_STX(1, 5) +                     # 0x14: S7 ★ 把新副本首址（R1）写进自己 JMP 的地址字节
    isa.I_JMP("JMP", 0x06)                # 0x16: S8 ← 地址字节 0x17 每代被 S7 改写
)

bomber = (
    isa.I_LDI(1, SWEEP_START) +           # 0xE0: 扫射起点
    isa.I_LDI(2, 0xFE) +                  # 0xE2: 炸弹 = 非法操作码
    isa.I_LDI(3, SWEEP_LEN) +             # 0xE4: 数量
    isa.I_STX(2, 1) +                     # 0xE6: 投弹 ← 循环
    isa.I_UN("INC", 1) +                  # 0xE8
    isa.I_UN("DEC", 3) +                  # 0xEA
    isa.I_JMP("JNZ", 0xE6) +              # 0xEC
    isa.I_JMP("JMP", 0xE0)                # 0xEE: 重装再扫
)

# ---- 竞技场：共享 RAM + 双 CPU（各自寄存器，MARS 进程模型）----
ram = RAM()
ram.load_program(worm, WORM_BASE)
ram.load_program(bomber, BOMB_BASE)

cpu_w = CPU()                             # 蠕虫：PC 天生 0
cpu_w.ram = ram
cpu_w.clk.attach(ram)
cpu_b = CPU()
cpu_b.ram = ram
cpu_b.clk.attach(ram)
cpu_b.pc.load(BOMB_BASE)                 # 轰炸机入口 0xE0
cpu_b.clk.tick()                         # 提交初始 PC


PATCHED = 0x17                           # S7 每代自改的 JMP 地址字节——合法变化，不算受损


def engine_damaged():
    return any(i != PATCHED and ram.read(i) != worm[i] for i in range(WORM_LEN))


def bomber_overwritten():
    return any(ram.read(BOMB_BASE + i) != bomber[i] for i in range(BOMB_LEN))


def render():
    front = cpu_w.rf.read(1)              # R1 = 蠕虫当前副本基址（推进前沿）
    print("    " + " ".join(f"{c:x}" for c in range(16)))
    for row in range(16):
        cells = []
        for col in range(16):
            a = row * 16 + col
            if WORM_BASE <= a < WORM_BASE + WORM_LEN:
                ok = ram.read(a) == worm[a] or a == PATCHED
                cells.append("W" if ok else "x")
            elif BOMB_BASE <= a < BOMB_BASE + BOMB_LEN:
                cells.append("B" if ram.read(a) == bomber[a - BOMB_BASE] else "w")
            elif BODY_OFF + WORM_BASE <= a < front:
                cells.append("w")        # 蠕虫铺过的痕迹
            elif ram.read(a) == 0xFE:
                cells.append("x")        # 炸弹
            else:
                cells.append(".")
        print(f"{row * 16:03x}: " + " ".join(cells))
    print("图例：W=引擎  w=蠕虫痕迹/机体  B=轰炸机  x=炸弹/残骸  .=空")


MAX_CYCLES = 4000
winner, reason, cycle = None, None, 0
for cycle in range(1, MAX_CYCLES + 1):
    for name, cpu, other in (("蠕虫", cpu_w, "轰炸机"), ("轰炸机", cpu_b, "蠕虫")):
        try:
            cpu.step()
        except ValueError:
            winner, reason = other, f"{name} 执行到非法指令，猝死"
    if winner is None and engine_damaged():
        winner, reason = "轰炸机", "蠕虫引擎被炸"
    if winner is None and bomber_overwritten():
        winner, reason = "蠕虫", "轰炸机机体被蠕虫铺过"
    if winner:
        break

print(f"对战结束：第 {cycle} 拍，胜者 —— {winner}（{reason}）\n")
render()
