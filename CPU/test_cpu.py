"""CPU 整机测试：ISA 编解码 → 单指令 → 分支 → 循环程序差分。

期望值全部由 Python 原生计算生成，延续项目的差分测试风格。
运行（项目根目录）：python -m CPU.test_cpu
"""
import sys

from . import isa, control
from .cpu import CPU

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def run_prog(prog, max_instr=10000):
    cpu = CPU(prog)
    n, halted = cpu.run(max_instr)
    return cpu, n, halted


# ---------- ① ISA：全量编解码往返 ----------

def test_isa():
    for r in range(8):
        check(f"LDI R{r}", isa.decode(*isa.I_LDI(r, 0x5A)), ("LDI", r, 0x5A))
        check(f"MOV R{r}", isa.decode(*isa.I_MOV(r, 3)), ("MOV", r, 3))
        check(f"LD R{r}", isa.decode(*isa.I_LD(r, 0x20)), ("LD", r, 0x20))
        check(f"ST R{r}", isa.decode(*isa.I_ST(r, 0x30)), ("ST", r, 0x30))
        for name in isa.ALU_OPS:
            check(f"{name} R{r}", isa.decode(*isa.I_ALU(name, r, 7)), (name, r, 7))
        for name in isa.UN_OPS:
            check(f"{name} R{r}", isa.decode(*isa.I_UN(name, r)), (name, r, None))
    for name in isa.JUMPS:
        check(f"{name}", isa.decode(*isa.I_JMP(name, 0x42)), (name, None, 0x42))
    check("HALT", isa.decode(*isa.I_HALT()), ("HALT", None, None))
    check("操作码表与控制表对齐", set(isa.MNEMONICS) == set(control.MICROCODE), True)
    try:
        isa.decode(0xFE, 0)
        ok = False
    except ValueError:
        ok = True
    check("非法操作码抛异常", ok, True)


# ---------- ② 单指令基本行为 ----------

def test_single():
    cpu, _, h = run_prog(isa.I_LDI(3, 0x7F) + isa.I_HALT())
    check("LDI 装载", cpu.rf.read(3), 0x7F)
    check("正常停机", h, True)

    cpu, _, _ = run_prog(isa.I_LDI(0, 9) + isa.I_MOV(5, 0) + isa.I_HALT())
    check("MOV 传送", cpu.rf.read(5), 9)

    cpu, _, _ = run_prog(isa.I_LDI(2, 0x66) + isa.I_ST(2, 0x80)
                         + isa.I_LD(4, 0x80) + isa.I_HALT())
    check("ST→LD 往返", cpu.rf.read(4), 0x66)
    check("内存内容", cpu.ram.read(0x80), 0x66)

    # ADD 回绕：1+255=256 → 0，Z=1 C=1
    cpu, _, _ = run_prog(isa.I_LDI(0, 1) + isa.I_LDI(1, 255)
                         + isa.I_ALU("ADD", 0, 1) + isa.I_HALT())
    check("ADD 回绕", cpu.rf.read(0), 0)
    check("ADD 后 Z=1", cpu.flags()["Z"], 1)
    check("ADD 后 C=1", cpu.flags()["C"], 1)

    # SUB 借位：3-5 → 254，C=0（有借位）
    cpu, _, _ = run_prog(isa.I_LDI(0, 3) + isa.I_LDI(1, 5)
                         + isa.I_ALU("SUB", 0, 1) + isa.I_HALT())
    check("SUB 借位", cpu.rf.read(0), (3 - 5) & 0xFF)
    check("SUB 后 C=0", cpu.flags()["C"], 0)

    # CMP：只更新标志，不动寄存器；标志跨非标志指令保持
    cpu, _, _ = run_prog(isa.I_LDI(0, 7) + isa.I_LDI(1, 7)
                         + isa.I_ALU("CMP", 0, 1) + isa.I_LDI(2, 5) + isa.I_HALT())
    check("CMP 不写回", cpu.rf.read(0), 7)
    check("CMP 相等 Z=1", cpu.flags()["Z"], 1)
    check("标志跨 LDI 保持", cpu.flags()["Z"], 1)

    # 单目组合：SHL+INC+DEC
    cpu, _, _ = run_prog(isa.I_LDI(0, 0x0F) + isa.I_UN("SHL", 0)
                         + isa.I_UN("INC", 0) + isa.I_UN("DEC", 0) + isa.I_HALT())
    check("SHL/INC/DEC 组合", cpu.rf.read(0), 0x1E)

    cpu, _, _ = run_prog(isa.I_LDI(0, 3) + isa.I_UN("SHR", 0) + isa.I_HALT())
    check("SHR", cpu.rf.read(0), 1)

    # MUL：200×100=20000，低字节 0x20，C=1（积超 8 位）
    cpu, _, _ = run_prog(isa.I_LDI(0, 200) + isa.I_LDI(1, 100)
                         + isa.I_ALU("MUL", 0, 1) + isa.I_HALT())
    check("MUL 低字节", cpu.rf.read(0), 20000 & 0xFF)
    check("MUL 后 C=1", cpu.flags()["C"], 1)

    # PC 顺序推进：3 条指令后停在 6
    cpu, _, _ = run_prog(isa.I_LDI(0, 1) + isa.I_LDI(1, 2)
                         + isa.I_ALU("ADD", 0, 1) + isa.I_HALT())
    check("PC 顺序推进", cpu.state()["pc"], 6)
    check("指令计数", cpu.state()["instrs"], 3)


# ---------- ③ 分支：条件真假各走一遍 ----------

def _branch_case(setup, jump_name, taken):
    """构造：setup → 条件跳转 → 毒药 LDI R1 → HALT；taken 时 R1 应为 0。"""
    prog = (setup
            + isa.I_JMP(jump_name, 0x08)   # 0x04 起（setup 占 2~4 字节）
            + isa.I_LDI(1, 0xEE)           # 毒药：仅落空时执行
            + isa.I_HALT())
    return run_prog(prog)


def test_branches():
    # Z 标志：7-7 → Z=1 → JZ 跳、JNZ 落空
    setup = isa.I_LDI(0, 7) + isa.I_ALU("CMP", 0, 0)      # 占 0x00-0x03
    cpu, _, h = _branch_case(setup, "JZ", True)
    check("JZ 跳过毒药", cpu.rf.read(1), 0)
    check("JZ 停机", h, True)
    cpu, _, _ = _branch_case(setup, "JNZ", False)
    check("JNZ 落空执行毒药", cpu.rf.read(1), 0xEE)

    # C 标志：3-5 有借位 C=0 → JNC 跳、JC 落空（毒药用 R7，避开操作数 R1）
    setup = isa.I_LDI(0, 3) + isa.I_LDI(1, 5) + isa.I_ALU("CMP", 0, 1)  # 0x00-0x05
    prog = (setup + isa.I_JMP("JNC", 0x0A) + isa.I_LDI(7, 0xEE) + isa.I_HALT())
    cpu, _, h = run_prog(prog)
    check("JNC 跳过毒药", cpu.rf.read(7), 0)
    check("JNC 停机", h, True)
    prog = (setup + isa.I_JMP("JC", 0x0A) + isa.I_LDI(7, 0xEE) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("JC 落空执行毒药", cpu.rf.read(7), 0xEE)

    # N 标志：0x80+1=0x81 → N=1 → JN 跳
    setup = isa.I_LDI(0, 0x80) + isa.I_UN("INC", 0)       # 0x00-0x03
    cpu, _, _ = _branch_case(setup, "JN", True)
    check("JN 跳过毒药", cpu.rf.read(1), 0)

    # V 标志：0x7F+1 正溢出 → V=1 → JV 跳（毒药用 R7）
    setup = isa.I_LDI(0, 0x7F) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)  # 0x00-0x05
    prog = (setup + isa.I_JMP("JV", 0x0A) + isa.I_LDI(7, 0xEE) + isa.I_HALT())
    cpu, _, h = run_prog(prog)
    check("JV 跳过毒药", cpu.rf.read(7), 0)
    check("JV 停机", h, True)

    # JMP 无条件：向前跳
    cpu, _, _ = run_prog(isa.I_JMP("JMP", 0x06) + isa.I_LDI(1, 0xEE)
                         + isa.I_HALT())
    check("JMP 无条件跳", cpu.rf.read(1), 0)


# ---------- ④ 循环程序差分（期望值由 Python 计算） ----------

def test_loop_sum():
    """1+2+...+n，n=1..12。"""
    for n in range(1, 13):
        prog = (isa.I_LDI(0, n) + isa.I_LDI(1, 0)
                + isa.I_ALU("ADD", 1, 0)      # 0x04
                + isa.I_UN("DEC", 0)
                + isa.I_JMP("JNZ", 0x04)
                + isa.I_HALT())
        cpu, _, h = run_prog(prog)
        check(f"累加 1..{n}", cpu.rf.read(1), (n * (n + 1) // 2) & 0xFF)
        check(f"累加 1..{n} 停机", h, True)


def test_loop_mul():
    """R2 = R0 × R1（循环加法），与 Python 差分。"""
    for a, b in [(7, 6), (13, 11), (0, 9), (3, 0), (16, 16), (200, 100)]:
        prog = (isa.I_LDI(0, a) + isa.I_LDI(1, b) + isa.I_LDI(2, 0)
                + isa.I_ALU("ADD", 2, 1)      # 0x06
                + isa.I_UN("DEC", 0)
                + isa.I_JMP("JNZ", 0x06)
                + isa.I_HALT())
        cpu, _, h = run_prog(prog)
        check(f"{a}×{b} 循环乘法", cpu.rf.read(2), (a * b) & 0xFF)
        check(f"{a}×{b} 停机", h, True)


def test_fibonacci():
    """迭代斐波那契 k=1..13，结果 mod 256。"""
    for k in range(1, 14):
        prog = (isa.I_LDI(0, k) + isa.I_LDI(1, 0) + isa.I_LDI(2, 1)
                + isa.I_MOV(3, 1)             # 0x06: t = a
                + isa.I_MOV(1, 2)             # 0x08: a = b
                + isa.I_ALU("ADD", 2, 3)      # 0x0A: b += t
                + isa.I_UN("DEC", 0)
                + isa.I_JMP("JNZ", 0x06)
                + isa.I_HALT())
        cpu, _, h = run_prog(prog)
        a, b = 0, 1
        for _ in range(k):
            a, b = b, (a + b) & 0xFF
        check(f"fib({k})", cpu.rf.read(1), a)
        check(f"fib({k}) 停机", h, True)


def main():
    for name, fn in [
        ("ISA 编解码往返", test_isa),
        ("单指令基本行为", test_single),
        ("条件分支", test_branches),
        ("循环累加差分", test_loop_sum),
        ("循环乘法差分", test_loop_mul),
        ("斐波那契差分", test_fibonacci),
    ]:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
