"""CPU 整机测试：ISA 编解码 → 单指令 → 分支 → 循环程序差分。

期望值全部由 Python 原生计算生成，延续项目的差分测试风格。
运行（项目根目录）：python -m CPU.test_cpu
"""
import ast
import math
import sys
from pathlib import Path

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


# ---------- 架构护栏：跨包 import 边冻结 ----------

PACKAGES = ("ALU", "COMB", "SEQ", "MEM", "CPU", "ASM")
EXPECTED_EDGES = {"COMB→ALU", "SEQ→ALU", "SEQ→COMB",
                  "CPU→ALU", "CPU→SEQ", "CPU→MEM", "ASM→CPU"}


def _cross_package_edges():
    """扫描六个包的实际 import，收集跨包依赖边（集合）。

    护栏的由来：README 曾写"跨包 import 仅 6 条"，ASM 加入带来第 7 条
    （ASM→CPU）后没人更新——自称精确的定量断言被岁月悄悄证伪。与其
    口头承诺"耦合面收窄"，不如让测试盯住：新增一条边必须同时改这里
    和 README，耦合的扩张从"悄悄发生"变成"显式决定"。
    只认 from X[.Y] import 形式（项目无裸 import 包）；相对导入（from .）
    是包内依赖；根目录示例脚本是驱动层、不在分层体系内，均不计。
    """
    root = Path(__file__).resolve().parent.parent
    edges = set()
    for pkg in PACKAGES:
        for py in (root / pkg).glob("*.py"):
            for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    head = node.module.split(".")[0]
                    if head in PACKAGES and head != pkg:
                        edges.add(f"{pkg}→{head}")
    return edges


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
    for r in range(8):
        check(f"LDX R{r}", isa.decode(*isa.I_LDX(r, 3)), ("LDX", r, 3))
        check(f"STX R{r}", isa.decode(*isa.I_STX(r, 3)), ("STX", r, 3))
    for r in range(8):
        check(f"ADC R{r}", isa.decode(*isa.I_ADC(r, 7)), ("ADC", r, 7))
        check(f"SBB R{r}", isa.decode(*isa.I_SBB(r, 7)), ("SBB", r, 7))
    for r in range(8):
        check(f"LDX 指针R{r}", isa.decode(*isa.I_LDX(2, r)), ("LDX", 2, r))
        check(f"STX 指针R{r}", isa.decode(*isa.I_STX(2, r)), ("STX", 2, r))
    check("HALT", isa.decode(*isa.I_HALT()), ("HALT", None, None))
    check("操作码表与控制表对齐", set(isa.MNEMONICS) == set(control.MICROCODE), True)
    check("跨包 import 边冻结（恰 7 条）", _cross_package_edges(), EXPECTED_EDGES)
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


# ---------- ⑦ 寄存器间接寻址 LDX/STX ----------

def test_indirect():
    """单次读写、指针步进、双指针拷贝、与自修改版的逐字节差分。"""
    # 单次读写：R3 当指针
    prog = (isa.I_LDI(3, 0x80) +
            isa.I_LDI(0, 0x5A) +
            isa.I_STX(0, 3) +               # mem[R3] ← R0
            isa.I_LDI(1, 0) +
            isa.I_LDX(1, 3) +               # R1 ← mem[R3]
            isa.I_HALT())
    cpu, _, h = run_prog(prog)
    check("间接·写入", cpu.ram.read(0x80), 0x5A)
    check("间接·读回", (cpu.rf.read(1), h), (0x5A, True))

    # 指针步进填表：0xC0..0xC3 各填 0x77（INC 指针即可，无补丁）
    prog = (isa.I_LDI(3, 0xC0) +            # 0x00: 指针
            isa.I_LDI(4, 4) +               # 0x02: 计数
            isa.I_LDI(0, 0x77) +            # 0x04: 值
            isa.I_STX(0, 3) +               # 0x06: 循环头
            isa.I_UN("INC", 3) +            # 0x08: 指针+1——普通数据操作
            isa.I_UN("DEC", 4) +            # 0x0A
            isa.I_JMP("JNZ", 0x06) +        # 0x0C
            isa.I_HALT())                   # 0x0E
    cpu, _, h = run_prog(prog)
    check("步进填表", [cpu.ram.read(0xC0 + i) for i in range(4)], [0x77] * 4)

    # 双指针拷贝：16 字节 0x40 → 0x60（自修改时代 9 条/格，现在 6 条/格）
    prog = (isa.I_LDI(2, 0x40) +            # 0x00: src 指针
            isa.I_LDI(3, 0x60) +            # 0x02: dst 指针
            isa.I_LDI(4, 16) +              # 0x04: 计数
            isa.I_LDX(0, 2) +               # 0x06: R0 ← mem[R2]
            isa.I_STX(0, 3) +               # 0x08: mem[R3] ← R0
            isa.I_UN("INC", 2) +            # 0x0A
            isa.I_UN("INC", 3) +            # 0x0C
            isa.I_UN("DEC", 4) +            # 0x0E
            isa.I_JMP("JNZ", 0x06) +        # 0x10
            isa.I_HALT())                   # 0x12
    src = [(i * 37 + 11) & 0xFF for i in range(16)]
    cpu = CPU(prog)
    for i, v in enumerate(src):             # 烧入源数据
        cpu.ram.data[0x40 + i] = v
    n, h = cpu.run()
    dst = [cpu.ram.read(0x60 + i) for i in range(16)]
    check("双指针拷贝·内容", dst, src)
    check("双指针拷贝·条数", (n, h), (3 + 16 * 6, True))   # 3 设置 + 16×6

    # ★ 差分验收：自修改版填表（sixth_munch 原版核心）vs 间接版，64 格逐字节比对
    old_prog = (                        # —— 自修改版（与 sixth_munch.py 相同，原文件不动）——
        isa.I_LDI(5, 8) +               # 0x00
        isa.I_LDI(1, 0) +               # 0x02
        isa.I_LDI(6, 0xC0) +            # 0x04
        isa.I_LDI(0, 0) +               # 0x06: y 头
        isa.I_MOV(3, 0) +               # 0x08: x 头
        isa.I_ALU("XOR", 3, 1) +        # 0x0A
        isa.I_ST(3, 0xC0) +             # 0x0C ← 自修改目标
        isa.I_UN("INC", 6) +            # 0x0E
        isa.I_ST(6, 0x0D) +             # 0x10 ← 补丁
        isa.I_UN("INC", 0) +            # 0x12
        isa.I_ALU("CMP", 0, 5) +        # 0x14
        isa.I_JMP("JNZ", 0x08) +        # 0x16
        isa.I_UN("INC", 1) +            # 0x18
        isa.I_ALU("CMP", 1, 5) +        # 0x1A
        isa.I_JMP("JNZ", 0x06) +        # 0x1C
        isa.I_HALT())                   # 0x1E
    new_prog = (                        # —— 间接版：STX 一条顶 ST+补丁两条 ——
        isa.I_LDI(5, 8) +               # 0x00
        isa.I_LDI(1, 0) +               # 0x02
        isa.I_LDI(6, 0xC0) +            # 0x04
        isa.I_LDI(0, 0) +               # 0x06: y 头
        isa.I_MOV(3, 0) +               # 0x08: x 头
        isa.I_ALU("XOR", 3, 1) +        # 0x0A
        isa.I_STX(3, 6) +               # 0x0C ★ 间接存储，无补丁
        isa.I_UN("INC", 6) +            # 0x0E
        isa.I_UN("INC", 0) +            # 0x10
        isa.I_ALU("CMP", 0, 5) +        # 0x12
        isa.I_JMP("JNZ", 0x08) +        # 0x14
        isa.I_UN("INC", 1) +            # 0x16
        isa.I_ALU("CMP", 1, 5) +        # 0x18
        isa.I_JMP("JNZ", 0x06) +        # 0x1A
        isa.I_HALT())                   # 0x1C
    cpu_old, n_old, h_old = run_prog(old_prog)
    cpu_new, n_new, h_new = run_prog(new_prog)
    fb_old = [cpu_old.ram.read(0xC0 + i) for i in range(64)]
    fb_new = [cpu_new.ram.read(0xC0 + i) for i in range(64)]
    check("差分·64 格逐字节一致", fb_new, fb_old)
    check("差分·两版正常停机", (h_old, h_new), (True, True))
    check("差分·指令数（旧 547 → 新 483，每格省 1 条）", (n_old, n_new), (547, 483))


# ---------- ⑧ 带进位加减 ADC/SBB：进位跨指令接力 ----------

def test_carry():
    """微码进位来源、单字节进/借位、SUB 接线回归、标志粘性、16 位差分。"""
    # 微码层：带进位指令与普通加减只差 c_from 一个字段——表格即文档
    add, adc = control.MICROCODE["ADD"], control.MICROCODE["ADC"]
    sub, sbb = control.MICROCODE["SUB"], control.MICROCODE["SBB"]
    check("微码·ADD 与 ADC 只差 c_from", add[:6] == adc[:6], True)
    check("微码·ADC 的进位接 C 标志", adc.c_from, "FLAG")
    check("微码·SUB 与 SBB 只差 c_from", sub[:6] == sbb[:6], True)
    check("微码·SBB 的进位接 C 标志", sbb.c_from, "FLAG")
    check("微码·SUB 的 cin 接 1（补码 +1）", sub.c_from, "ONE")
    check("微码·CMP/INC/DEC 的 cin", (control.MICROCODE["CMP"].c_from,
          control.MICROCODE["INC"].c_from, control.MICROCODE["DEC"].c_from),
          ("ONE", "ZERO", "ONE"))

    # ADC 吃进上一条 ADD 的进位：255+1 → C=1，高字节 0+0+C=1
    prog = (isa.I_LDI(0, 255) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)
            + isa.I_LDI(4, 0) + isa.I_LDI(3, 0) + isa.I_ADC(4, 3) + isa.I_HALT())
    cpu, _, h = run_prog(prog)
    check("ADC·吃进位", (cpu.rf.read(0), cpu.rf.read(4), h), (0, 1, True))
    check("ADC·0+0+1 无新进位", cpu.flags()["C"], 0)

    # ADC 在无进位时不多加：1+2 → C=0，10+20+C=30
    prog = (isa.I_LDI(0, 1) + isa.I_LDI(1, 2) + isa.I_ALU("ADD", 0, 1)
            + isa.I_LDI(4, 10) + isa.I_LDI(3, 20) + isa.I_ADC(4, 3) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("ADC·无进位不多加", cpu.rf.read(4), 30)

    # SBB 借位链：0−1 → 255 C=0，高字节 0−0−借位 = 255（16 位 0−1 = 0xFFFF）
    prog = (isa.I_LDI(0, 0) + isa.I_LDI(1, 1) + isa.I_ALU("SUB", 0, 1)
            + isa.I_LDI(4, 0) + isa.I_LDI(3, 0) + isa.I_SBB(4, 3) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("SBB·借位链 16 位 0−1", (cpu.rf.read(0), cpu.rf.read(4)), (255, 255))
    check("SBB·再借位 C=0", cpu.flags()["C"], 0)

    # SBB 在无借位时就是普通减法：5−3 → C=1，10−4−0=6
    prog = (isa.I_LDI(0, 5) + isa.I_LDI(1, 3) + isa.I_ALU("SUB", 0, 1)
            + isa.I_LDI(4, 10) + isa.I_LDI(3, 4) + isa.I_SBB(4, 3) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("SBB·无借位即普通减", cpu.rf.read(4), 6)

    # SUB 接线回归：cin 必须恰好接 1（否则悄悄变成 a−b−1）
    for a, b in [(5, 3), (100, 55), (0, 1), (200, 100)]:
        prog = (isa.I_LDI(0, a) + isa.I_LDI(1, b) + isa.I_ALU("SUB", 0, 1) + isa.I_HALT())
        cpu, _, _ = run_prog(prog)
        check(f"SUB 回归 {a}−{b}", (cpu.rf.read(0), cpu.flags()["C"]),
              ((a - b) & 0xFF, int(a >= b)))
    cpu, _, _ = run_prog(isa.I_LDI(0, 3) + isa.I_LDI(1, 5)
                         + isa.I_ALU("CMP", 0, 1) + isa.I_HALT())
    check("CMP 回归·借位 C=0", cpu.flags()["C"], 0)
    cpu, _, _ = run_prog(isa.I_LDI(0, 0) + isa.I_UN("DEC", 0) + isa.I_HALT())
    check("DEC 回归·0−1=255", cpu.rf.read(0), 255)   # C 的行为已改"保持"，见下组
    cpu, _, _ = run_prog(isa.I_LDI(0, 255) + isa.I_UN("INC", 0) + isa.I_HALT())
    check("INC 回归·255+1=0", cpu.rf.read(0), 0)

    # 标志粘性：C 跨过不动标志的指令存活，ADC 取到的仍是旧值
    prog = (isa.I_LDI(0, 255) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)   # C=1
            + isa.I_LDI(2, 5) + isa.I_LD(3, 0x00) + isa.I_LDI(4, 6)       # 全都不动标志
            + isa.I_ADC(2, 4) + isa.I_HALT())                             # 5+6+旧 C=12
    cpu, _, _ = run_prog(prog)
    check("标志粘性·ADC 取旧 C", cpu.rf.read(2), 12)

    # ADC 的有符号溢出：127 + 0 + C=1 = 128 → V=1（V=c6⊕C 对带进位加法同样成立）
    prog = (isa.I_LDI(0, 255) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)   # C=1
            + isa.I_LDI(0, 127) + isa.I_LDI(1, 0) + isa.I_ADC(0, 1) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("ADC 溢出 127+0+C", (cpu.rf.read(0), cpu.flags()["V"], cpu.flags()["N"]),
          (128, 1, 1))

    # 进位跨两条 ADC 接力：24 位 0x0000FF + 0x000001 = 0x010000
    prog = (isa.I_LDI(0, 0xFF) + isa.I_LDI(1, 0x01)
            + isa.I_ALU("ADD", 0, 1)                                      # 字节 0：00，C=1
            + isa.I_LDI(1, 0) + isa.I_LDI(2, 0) + isa.I_ADC(2, 1)         # 字节 1：01，C=0
            + isa.I_LDI(3, 0) + isa.I_ADC(3, 1)                           # 字节 2：00
            + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("24 位进位接力 0xFF+1", (cpu.rf.read(0), cpu.rf.read(2), cpu.rf.read(3)),
          (0, 1, 0))

    # ★ 16 位差分矩阵：ADD/ADC、SUB/SBB 与 Python 逐例比对
    #   布局与 fourth_multibyte(v1/v2) 相同：低字节在前，结果看 (低, 高, 进位/借位)
    CASES = [(0x01FF, 0x0002), (0x00FF, 0x0001), (0xFFFF, 0x0001), (0x0000, 0x0001),
             (0x1234, 0xCDEF), (60000, 10000), (0x8000, 0x7FFF), (0x0000, 0x0000)]
    for a, b in CASES:
        prog = (isa.I_LDI(0, a & 0xFF) + isa.I_LDI(1, b & 0xFF)
                + isa.I_ALU("ADD", 0, 1)                                  # 低字节，C=c0
                + isa.I_LDI(2, a >> 8) + isa.I_LDI(3, b >> 8)
                + isa.I_ADC(2, 3) + isa.I_HALT())                         # 高字节 +c0
        cpu, _, h = run_prog(prog)
        s = a + b
        check(f"16 位加 {a:#06x}+{b:#06x}",
              (cpu.rf.read(0), cpu.rf.read(2), cpu.flags()["C"], h),
              (s & 0xFF, (s >> 8) & 0xFF, int(s > 0xFFFF), True))
        prog = (isa.I_LDI(0, a & 0xFF) + isa.I_LDI(1, b & 0xFF)
                + isa.I_ALU("SUB", 0, 1)                                  # 低字节，C=0 即借位
                + isa.I_LDI(2, a >> 8) + isa.I_LDI(3, b >> 8)
                + isa.I_SBB(2, 3) + isa.I_HALT())                         # 高字节 −借位
        cpu, _, h = run_prog(prog)
        d = a - b
        check(f"16 位减 {a:#06x}−{b:#06x}",
              (cpu.rf.read(0), cpu.rf.read(2), 1 - cpu.flags()["C"], h),
              (d & 0xFF, (d >> 8) & 0xFF, int(a < b), True))


# ---------- ⑨ INC/DEC 保持 C/V：进位链中间可安全步进指针 ----------

def test_inc_dec_carry():
    """INC/DEC 只写 Z/N，C/V 保持（对齐 x86 INC 保全 CF / 6502 INX 不碰 C）。

    动机：指针步进（INC）与循环计数（DEC）是循环的必需品，而它们曾把
    C 顺手踩掉——多精度加法的指针循环因此写不出来（fourth_multibyte_v2
    第二幕：0xFF+1 曾算出 0x01010000）。本组锁定修复后的语义。
    """
    # 微码层：INC/DEC 的 flags 字段为 "ZN"
    check("微码·INC 只写 Z/N", control.MICROCODE["INC"].flags, "ZN")
    check("微码·DEC 只写 Z/N", control.MICROCODE["DEC"].flags, "ZN")

    # C 保持（双向）：预设 C=1 → INC 后仍 1；预设 C=0 → DEC 后仍 0
    prog = (isa.I_LDI(0, 255) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)  # C=1
            + isa.I_LDI(2, 5) + isa.I_UN("INC", 2) + isa.I_HALT())        # 5→6
    cpu, _, _ = run_prog(prog)
    check("INC·C 保持=1", (cpu.rf.read(2), cpu.flags()["C"]), (6, 1))
    prog = (isa.I_LDI(0, 0) + isa.I_LDI(1, 1) + isa.I_ALU("SUB", 0, 1)    # C=0
            + isa.I_LDI(2, 5) + isa.I_UN("DEC", 2) + isa.I_HALT())        # 5→4
    cpu, _, _ = run_prog(prog)
    check("DEC·C 保持=0", (cpu.rf.read(2), cpu.flags()["C"]), (4, 0))

    # V 保持：预设 V=1（127+1 有符号溢出）→ INC 别的寄存器后 V 仍 1
    prog = (isa.I_LDI(0, 127) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)  # V=1
            + isa.I_LDI(2, 5) + isa.I_UN("INC", 2) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("INC·V 保持=1", cpu.flags()["V"], 1)

    # Z/N 照写：INC 1→2 时 Z=0；DEC 1→0 时 Z=1（循环语义不丢）
    prog = (isa.I_LDI(0, 1) + isa.I_UN("INC", 0) + isa.I_LDI(1, 1)
            + isa.I_UN("DEC", 1) + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("INC/DEC·Z 照写", (cpu.rf.read(0), cpu.rf.read(1), cpu.flags()["Z"]),
          (2, 0, 1))
    cpu, _, _ = run_prog(isa.I_LDI(0, 0x7F) + isa.I_UN("INC", 0) + isa.I_HALT())
    check("INC·N 照写", (cpu.rf.read(0), cpu.flags()["N"]), (0x80, 1))

    # ★ 新能力最小复现：进位链中间插 INC（修复前这条必挂）
    #   即 fourth_multibyte_v2 第二幕的最小化：ADD 产 C=1 → 指针步进 → ADC 接力
    prog = (isa.I_LDI(0, 255) + isa.I_LDI(1, 1) + isa.I_ALU("ADD", 0, 1)  # C=1
            + isa.I_LDI(5, 0xC0) + isa.I_UN("INC", 5)                     # 指针步进
            + isa.I_LDI(2, 0) + isa.I_LDI(3, 0) + isa.I_ADC(2, 3)         # 0+0+C=1
            + isa.I_HALT())
    cpu, _, _ = run_prog(prog)
    check("★进位链中间插 INC·ADC 仍吃到 C=1", (cpu.rf.read(2), cpu.rf.read(5)),
          (1, 0xC1))

    # 回绕检测能力未丢：INC 255→0 时 Z=1 接得住（旧靠 C，新靠 Z）
    cpu, _, _ = run_prog(isa.I_LDI(0, 255) + isa.I_UN("INC", 0) + isa.I_HALT())
    check("INC 回绕·Z=1 仍可检测", (cpu.rf.read(0), cpu.flags()["Z"]), (0, 1))


def main():
    for name, fn in [
        ("ISA 编解码往返", test_isa),
        ("单指令基本行为", test_single),
        ("条件分支", test_branches),
        ("子程序 CALL/RET", test_subroutines),
        ("PUSH/POP 与 fib 验收", test_push_pop),
        ("寄存器间接寻址 LDX/STX", test_indirect),
        ("带进位加减 ADC/SBB", test_carry),
        ("INC/DEC 保持 C/V", test_inc_dec_carry),
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
