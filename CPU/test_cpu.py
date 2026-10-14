"""CPU 整机测试：ISA 编解码 → 单指令 → 分支 → 循环程序差分。

期望值全部由 Python 原生计算生成，延续项目的差分测试风格。
运行（项目根目录）：python -m CPU.test_cpu
"""
import math
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
    check("CALL", isa.decode(*isa.I_CALL(0x42)), ("CALL", None, 0x42))
    check("RET", isa.decode(*isa.I_RET()), ("RET", None, None))
    for r in range(8):
        check(f"PUSH R{r}", isa.decode(*isa.I_PUSH(r)), ("PUSH", r, None))
        check(f"POP R{r}", isa.decode(*isa.I_POP(r)), ("POP", r, None))
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


# ---------- ⑤ 子程序：CALL/RET 与硬件栈 ----------

def test_subroutines():
    """调用/返回、多处调用、嵌套、递归；SP 必须全程归位。"""
    # 基本：调用 → 执行 → 返回到 CALL 的下一条
    prog = (isa.I_LDI(0, 7) +
            isa.I_CALL(0x08) +              # 0x02
            isa.I_LDI(1, 1) +               # 0x04：返回后应执行（返回点正确的证据）
            isa.I_HALT() +                  # 0x06
            isa.I_LDI(2, 9) + isa.I_RET())  # 0x08: 子程序
    cpu, _, h = run_prog(prog)
    check("调用·子程序执行", cpu.rf.read(2), 9)
    check("调用·返回点正确", cpu.rf.read(1), 1)
    check("调用·SP 归零", cpu.sp.value, 0)

    # 同一子程序被两处调用：各自返回各自的现场
    prog = (isa.I_CALL(0x0A) +              # 0x00 → 回 0x02
            isa.I_CALL(0x0A) +              # 0x02 → 回 0x04
            isa.I_HALT() +                  # 0x04
            [0, 0, 0, 0] +                  # 0x06-0x09 填充
            isa.I_UN("INC", 4) + isa.I_RET())   # 0x0A: 子程序
    cpu, _, h = run_prog(prog)
    check("两处调用·各回各家", (cpu.rf.read(4), cpu.sp.value, h), (2, 0, True))

    # 嵌套 A→B→C：三层返回地址同时入栈，LIFO 逐层解开
    prog = (isa.I_LDI(1, 1) + isa.I_LDI(2, 2) + isa.I_LDI(3, 3) +
            isa.I_CALL(0x0E) +              # 0x06: A 调 B
            isa.I_ST(1, 0x92) +             # 0x08: B 返回后执行（A 还活着）
            isa.I_HALT() +                  # 0x0A
            [0, 0] +                        # 0x0C-0D 填充
            isa.I_CALL(0x14) +              # 0x0E: B 调 C
            isa.I_ST(2, 0x91) +             # 0x10: C 返回后执行（B 还活着）
            isa.I_RET() +                   # 0x12
            isa.I_ST(3, 0x90) + isa.I_RET())   # 0x14: C
    cpu, _, h = run_prog(prog)
    check("嵌套·C 执行", cpu.ram.read(0x90), 3)
    check("嵌套·B 在 C 返回后继续", cpu.ram.read(0x91), 2)
    check("嵌套·A 在 B 返回后继续", cpu.ram.read(0x92), 1)
    check("嵌套·SP 归零", cpu.sp.value, 0)

    # 递归求和 sum(1..n)：下降前先累加（R1 += R0），无需调用后局部变量
    for n, want in [(1, 1), (5, 15), (10, 55), (50, 1275 & 0xFF)]:
        prog = (isa.I_LDI(0, n) + isa.I_LDI(1, 0) + isa.I_LDI(5, 0) +
                isa.I_CALL(0x0A) +          # 0x06
                isa.I_HALT() +              # 0x08
                isa.I_ALU("CMP", 0, 5) +    # 0x0A: 子程序 sum：n==0？
                isa.I_JMP("JZ", 0x14) +     # 0x0C → 直达 RET
                isa.I_ALU("ADD", 1, 0) +    # 0x0E: R1 += n
                isa.I_UN("DEC", 0) +        # 0x10
                isa.I_CALL(0x0A) +          # 0x12: 递归
                isa.I_RET())                # 0x14
        cpu, _, h = run_prog(prog)
        check(f"递归 sum({n})", (cpu.rf.read(1), cpu.sp.value, h), (want, 0, True))


# ---------- ⑥ PUSH/POP：栈上保存/恢复现场，fib 验收 ----------

def test_push_pop():
    """往返与 LIFO、跨调用保存现场、定义直译版阶乘、两次递归的 fib。"""
    # 往返 + LIFO：后进先出
    prog = (isa.I_LDI(0, 0x5A) +
            isa.I_PUSH(0) +                # 压 0x5A
            isa.I_LDI(0, 0) +
            isa.I_PUSH(0) +                # 压 0
            isa.I_POP(1) +                 # 先弹出的是后进的 0
            isa.I_POP(2) +                 # 再弹出先进的 0x5A
            isa.I_HALT())
    cpu, _, h = run_prog(prog)
    check("LIFO·后进先出", cpu.rf.read(1), 0)
    check("LIFO·先进后出", cpu.rf.read(2), 0x5A)
    check("LIFO·SP 归零", cpu.sp.value, 0)

    # 跨调用保存现场：子程序内部毁掉 R0，靠 PUSH/POP 完璧归赵
    prog = (isa.I_LDI(0, 77) +
            isa.I_CALL(0x06) +             # 0x02
            isa.I_HALT() +                 # 0x04
            isa.I_PUSH(0) +                # 0x06: keep 子程序
            isa.I_LDI(0, 0) + isa.I_UN("INC", 0) +   # 随意毁 R0
            isa.I_POP(0) + isa.I_RET())
    cpu, _, h = run_prog(prog)
    check("跨调用·R0 恢复", (cpu.rf.read(0), cpu.sp.value, h), (77, 0, True))

    # 定义直译版阶乘：乘法在递归之后（无 PUSH/POP 时算出 0 的那个版本）
    for n in range(8):
        prog = (isa.I_LDI(5, 0) + isa.I_LDI(0, n) + isa.I_LDI(1, 1) +
                isa.I_CALL(0x0A) +          # 0x06
                isa.I_HALT() +              # 0x08
                isa.I_ALU("CMP", 0, 5) +    # 0x0A: fact
                isa.I_JMP("JZ", 0x18) +
                isa.I_PUSH(0) +             # ★ 存本层 n
                isa.I_UN("DEC", 0) +
                isa.I_CALL(0x0A) +
                isa.I_POP(0) +              # ★ 取回本层 n
                isa.I_ALU("MUL", 1, 0) +
                isa.I_RET())                # 0x18
        cpu, _, h = run_prog(prog)
        check(f"阶乘 {n}!", (cpu.rf.read(1), cpu.sp.value, h),
              (math.factorial(n) & 0xFF, 0, True))

    # fib 验收：两次递归调用，n 与第一次结果都要活过第二次调用
    for n, want in [(0, 0), (1, 1), (2, 1), (3, 2), (4, 3), (5, 5), (7, 13), (10, 55)]:
        prog = (isa.I_LDI(5, 0) + isa.I_LDI(6, 1) + isa.I_LDI(0, n) +
                isa.I_CALL(0x0A) +          # 0x06
                isa.I_HALT() +              # 0x08
                isa.I_ALU("CMP", 0, 5) +    # 0x0A: fib：n==0？
                isa.I_JMP("JZ", 0x28) +     # → zero
                isa.I_ALU("CMP", 0, 6) +    # n==1？
                isa.I_JMP("JZ", 0x2C) +     # → one
                isa.I_PUSH(0) +             # ★ 存 n
                isa.I_UN("DEC", 0) +
                isa.I_CALL(0x0A) +          # R1 = fib(n-1)
                isa.I_POP(0) +              # 取回 n
                isa.I_PUSH(1) +             # ★ 存第一次结果
                isa.I_UN("DEC", 0) + isa.I_UN("DEC", 0) +
                isa.I_CALL(0x0A) +          # R1 = fib(n-2)
                isa.I_POP(2) +              # 取回第一次结果
                isa.I_ALU("ADD", 1, 2) +    # R1 = 两者之和
                isa.I_RET() +               # 0x26
                isa.I_LDI(1, 0) + isa.I_RET() +   # 0x28: zero
                isa.I_LDI(1, 1) + isa.I_RET())    # 0x2C: one
        cpu, _, h = run_prog(prog)
        check(f"fib({n})", (cpu.rf.read(1), cpu.sp.value, h), (want, 0, True))


def main():
    for name, fn in [
        ("ISA 编解码往返", test_isa),
        ("单指令基本行为", test_single),
        ("条件分支", test_branches),
        ("子程序 CALL/RET", test_subroutines),
        ("PUSH/POP 与 fib 验收", test_push_pop),
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
