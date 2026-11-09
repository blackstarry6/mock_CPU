"""第十二个程序：相对跳转 JR——位置无关代码的雏形，纯 imp 精神复活。

编年史第五幕的第一块砖：绝对跳转把代码钉死在出生地（搬家就得改字节——
重定位），相对跳转（目标 = 下一条地址 + 带符号偏移）让控制流与位置无关：
同一段字节放哪都能跑。6502 的分支族就是这个配方（短距相对 ±128 与长距
绝对 JMP 并存）。

三幕：
  第一幕  位置无关的两个实验——①同一源码在两个基址各汇编一次：JR 版字节
          相同、绝对版跳转字节随基址变；②不重新汇编、原样搬家：JR 版照跑，
          绝对版跳回旧址踩炸弹猝死
  第二幕  块状 imp——无引擎、无补丁的移动蠕虫：把自己复制到紧邻前方后
          "落空"走进副本（PC 随复制前进——Redcode imp 的原理在块级复活），
          全块唯一的分支是一条 JRNZ。对照第七站：常驻引擎 + 每代改写 JMP
          地址字节的补丁（手工自重定位），如今双双退役；另设锚定对照——
          同一块换绝对 JNZ，大脑永远困在出生地，出生地一炸即死
  第三幕  取 PC 魔术半成功——x86 的 call/pop 取 EIP 在本机取到的值是对的
          （返回地址由硬件按 PC+2 现算，天然相对），但控制流被绝对 CALL
          拐回原址；原址一炸，副本即死。PIC 完全体还差两块砖：相对 CALL
          与相对数据寻址——第五幕的续集

运行：python twelfth_jr.py
"""
from ASM.asm import assemble
from CPU import isa
from CPU.cpu import CPU

BOMB = 0xFE         # 非法操作码当炸弹（第七站同款）


def machine(placements, start=0, fill=0):
    """按 (基址, 字节) 清单摆好内存的 CPU；fill 铺底（如炸弹场），start 设入口。"""
    cpu = CPU()
    cpu.ram.data[:] = [fill] * len(cpu.ram.data)
    for base, image in placements:
        for i, b in enumerate(image):
            cpu.ram.data[(base + i) & 0xFF] = b
    if start:
        cpu.pc.load(start)
        cpu.clk.tick()
    return cpu


def run_safe(cpu, steps):
    """跑至多 steps 拍：踩到非法指令返回 'dead'、停机返回 'halt'、否则 'alive'。"""
    for _ in range(steps):
        try:
            if not cpu.step():
                return "halt"
        except ValueError:
            return "dead"
    return "alive"


def hexs(bs):
    return " ".join(f"{b:02X}" for b in bs)


# ================= 第一幕：位置无关的两个实验 =================

BLOCK = """\
blk:
    LDI R0, #5
    LDI R1, #0
lp: ADD R1, R0          ; 累加 5+4+3+2+1
    DEC R0
    {J} lp              ; ★ 全块唯一的跳转：相对 or 绝对
    HALT
"""


def act1():
    print("第一幕：位置无关的两个实验（累加 1..5 的小循环块）")
    fails = 0
    print("  实验一·同一源码在两个基址各汇编一次：")
    for j in ("JRNZ", "JNZ"):
        lo = assemble(BLOCK.format(J=j))
        hi = assemble("JMP blk\n.org 0x80\n" + BLOCK.format(J=j))[0x80:]
        same = lo == hi
        fails += same != (j == "JRNZ")
        print(f"    {j:>4} 版 @0x00：{hexs(lo)}")
        print(f"    {j:>4} 版 @0x80：{hexs(hi)}   "
              f"{'逐字节相同 ✓ 位置无关' if same else '跳转字节随基址变——位置相关'}")
    print("  实验二·取 0x00 版字节原样拷到 0x80（不重新汇编），其余内存铺炸弹：")
    for j in ("JRNZ", "JNZ"):
        cpu = machine([(0x80, assemble(BLOCK.format(J=j)))], start=0x80, fill=BOMB)
        fate = run_safe(cpu, 200)
        if j == "JRNZ":
            ok = (fate, cpu.rf.read(1)) == ("halt", 15)
            print(f"    JRNZ 版：停机，R1 = {cpu.rf.read(1)} {'✓ 照常运行' if ok else '✗ ' + fate}")
        else:
            ok = fate == "dead"
            print(f"    JNZ  版：跳回旧址 0x04 → 炸弹格 → "
                  f"{'猝死 ✓（预期的位置相关之死）' if ok else fate + ' ✗'}")
        fails += not ok
    return fails


# ================= 第二幕：块状 imp——无引擎、无补丁的移动蠕虫 =================

WORM = """\
; 发射器：给第一代填好地址（数据寻址尚无"相对自己"的手段——见第三幕）
    LDI R1, #blk        ; 源 = 块首
    LDI R2, #nxt        ; 目标 = 紧邻前方（块尾之后）
blk:
    LDI R3, #14         ; 块长 14 字节（7 条 × 2）——每代重置计数
copy:
    LDX R4, R1          ; 读自己一字节
    STX R4, R2          ; 写到前方
    INC R1              ; 两根指针同步前进：拷完时恰好指向下一代的源与目标
    INC R2
    DEC R3
    {J} copy            ; ★ 全块唯一的分支
nxt:                    ; 落空 = 走进刚造好的副本：PC 随复制前进（imp 原理）
"""
BLK, BLEN = 0x04, 14
GEN_STEPS = 1 + BLEN * 6        # 每代：LDI + 14 轮（LDX STX INC INC DEC 分支）


def act2():
    print("\n第二幕：块状 imp——无引擎、无补丁的移动蠕虫")
    fails = 0
    patch = isa.disasm(*isa.I_STX(1, 5))
    print(f"  立此存照（第七站）：S7 `{patch}`——每代把新副本首址写进自己 JMP")
    print("  的地址字节 0x17：每繁殖一代手工执行一次自重定位；且引擎永不搬家。")

    G = 10
    img = assemble(WORM.format(J="JRNZ"))
    block = img[BLK:BLK + BLEN]
    cpu = machine([(0, img)])
    run_safe(cpu, 2 + G * GEN_STEPS)
    copies_ok = all(cpu.ram.data[BLK + BLEN * k:BLK + BLEN * (k + 1)] == block
                    for k in range(G + 1))
    pc_ok = cpu.pc.value == BLK + BLEN * G
    fails += not (copies_ok and pc_ok)
    print(f"  JRNZ 蠕虫爬行 {G} 代：执行点 0x{BLK:02X} → 0x{cpu.pc.value:02X}"
          f" {'✓' if pc_ok else '✗'}；{G + 1} 份副本逐字节相同、零补丁"
          f" {'✓' if copies_ok else '✗'}")

    cpu = machine([(0, assemble(WORM.format(J="JNZ")))])
    max_pc = 0
    for _ in range(2 + G * GEN_STEPS):
        cpu.step()
        max_pc = max(max_pc, cpu.pc.value)
    anchored = max_pc < BLK + 2 * BLEN
    fails += not anchored
    print(f"  JNZ 锚定版同跑 {G} 代：副本照铺（指针照常前进），但执行点最远只到"
          f" 0x{max_pc:02X}——大脑困在出生地 {'✓（预期）' if anchored else '✗'}")

    print("  定点爆破：爬 3 代后把出生地 [0x04,0x12) 填满炸弹，再跑 3 代——")
    for j in ("JRNZ", "JNZ"):
        cpu = machine([(0, assemble(WORM.format(J=j)))])
        run_safe(cpu, 2 + 3 * GEN_STEPS)
        for i in range(BLK, BLK + BLEN):
            cpu.ram.data[i] = BOMB
        fate = run_safe(cpu, 3 * GEN_STEPS)
        want = "alive" if j == "JRNZ" else "dead"
        ok = fate == want
        fails += not ok
        desc = (f"早已远走，安然无恙（执行点 0x{cpu.pc.value:02X}）" if fate == "alive"
                else "回出生地踩雷，猝死" if fate == "dead" else fate)
        print(f"    {j:>4} 版：{desc} {'✓' if ok else '✗'}")
    return fails


# ================= 第三幕：取 PC 魔术——半成功 =================

GETPC = """\
    CALL next           ; 压入返回地址（硬件现算 PC+2——天然相对）→ 跳 next（绝对！）
next:
    POP R1              ; R1 = "自己所在"的地址
    HALT
"""


def act3():
    print("\n第三幕：取 PC 魔术（x86 call/pop 取 EIP 的本机版）——半成功")
    fails = 0
    img = assemble(GETPC)                           # 为基址 0x00 汇编

    cpu = machine([(0, img)])
    fate = run_safe(cpu, 10)
    ok = (fate, cpu.rf.read(1), cpu.pc.value) == ("halt", 0x02, 0x04)
    fails += not ok
    print(f"  原址 0x00 运行：R1 = 0x{cpu.rf.read(1):02X}（学到自己的位置），"
          f"停在 0x{cpu.pc.value:02X} {'✓' if ok else '✗'}")

    cpu = machine([(0, img), (0x80, img)], start=0x80)
    fate = run_safe(cpu, 10)
    ok = (fate, cpu.rf.read(1), cpu.pc.value) == ("halt", 0x82, 0x04)
    fails += not ok
    print(f"  副本 0x80 运行：R1 = 0x{cpu.rf.read(1):02X}（值是对的！返回地址天然相对）")
    print(f"                 但停在 0x{cpu.pc.value:02X}——控制流被绝对 CALL 拐回原址"
          f" {'✓（预期）' if ok else '✗'}")

    cpu = machine([(0x80, img)], start=0x80, fill=BOMB)
    fate = run_safe(cpu, 10)
    ok = fate == "dead"
    fails += not ok
    print(f"  副本 + 原址被炸：CALL 跳回炸弹格 → {'猝死 ✓（预期）' if ok else fate + ' ✗'}")
    print("""  结论：x86 的 call/pop 能取 EIP，是因为 x86 的 CALL 本身就是相对位移；
        本机 CALL 是绝对的——JR 只相对化了"跳转"这一半。PIC 完全体还差两块
        砖：相对 CALL 与相对数据寻址（base+offset）。真·纯 imp（单条指令
        自复制）同样卡在后者——这就是第二幕蠕虫需要发射器填地址、需要 7 条
        而不是 1 条的原因。编年史第五幕，未完待续。""")
    return fails


def main():
    fails = act1() + act2() + act3()
    print("\n" + "═" * 62)
    print("三幕全部通过 ✓" if fails == 0 else f"{fails} 项失败 ✗")
    print("账本：JR 让控制流与位置无关——同一段字节放哪都能跑，蠕虫零补丁")
    print("自由迁徙；剩下的一半（相对 CALL / 相对数据寻址）留给第五幕续集。")


if __name__ == "__main__":
    main()
