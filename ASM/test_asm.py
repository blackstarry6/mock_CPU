"""汇编器测试：编码差分 / 标号与伪指令 / 错误用例 / 端到端上机。

运行（项目根目录）：python -m ASM.test_asm
"""
import sys

from .asm import assemble, AsmError
from CPU import isa
from CPU.cpu import CPU

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


# ---------- ① 编码差分：与 isa.I_* 两套独立路径必须一致 ----------

def test_encode_diff():
    for r in range(8):
        check(f"LDI R{r}", assemble(f"LDI R{r}, #90"), isa.I_LDI(r, 90))
        check(f"MOV R{r}", assemble(f"MOV R{r}, R3"), isa.I_MOV(r, 3))
        check(f"LD R{r}", assemble(f"LD R{r}, [0x20]"), isa.I_LD(r, 0x20))
        check(f"ST R{r}", assemble(f"ST R{r}, [0x30]"), isa.I_ST(r, 0x30))
        for name in isa.ALU_OPS:
            check(f"{name} R{r}", assemble(f"{name} R{r}, R7"), isa.I_ALU(name, r, 7))
        for name in isa.UN_OPS:
            check(f"{name} R{r}", assemble(f"{name} R{r}"), isa.I_UN(name, r))
    for name in isa.JUMPS:
        check(f"{name}", assemble(f"{name} 0x42"), isa.I_JMP(name, 0x42))
    check("HALT", assemble("HALT"), isa.I_HALT())
    check("十六进制立即数", assemble("LDI R0, #0x5A"), isa.I_LDI(0, 0x5A))
    check("小写与注释", assemble("ldi r2, #7 ; 装载\n"), isa.I_LDI(2, 7))


# ---------- ② 标号与伪指令 ----------

def test_labels_directives():
    src = """
        LDI R0, #5
        LDI R1, #0
    loop:
        ADD R1, R0
        DEC R0
        JNZ loop        ; 后向引用
        JMP next        ; 前向引用
    next:
        HALT
    """
    got = assemble(src)
    want = (isa.I_LDI(0, 5) + isa.I_LDI(1, 0) + isa.I_ALU("ADD", 1, 0)
            + isa.I_UN("DEC", 0) + isa.I_JMP("JNZ", 0x04)
            + isa.I_JMP("JMP", 0x0C) + isa.I_HALT())
    check("标号程序整体", got, want)
    check("loop 解析为 0x04", got[9], 0x04)      # 第 5 条指令（JNZ）的操作数字节
    check("next 解析为 0x0C", got[11], 0x0C)
    check(".db 数据与字符串", assemble('.db 1, 0x41, "AB"'), [1, 0x41, 0x41, 0x42])
    check(".org 前进补零", assemble("HALT\n.org 0x04\n.db 9"), [0xF0, 0, 0, 0, 9])
    check("标号与指令同行", assemble("l: DEC R0\nJNZ l"),
          isa.I_UN("DEC", 0) + isa.I_JMP("JNZ", 0))


def test_label_rename():
    """蜕变测试：标号改名（引用同步改）→ 机器码逐字节不变。

    其他断言验证"标号解析对不对"，这条验证"名字本身没有泄漏进机器码"——
    名字只是翻译期的脚手架，查表换成地址后即抹除。
    """
    base = assemble("loop: DEC R0\nJNZ loop")
    for name in ("looop", "My_42nd_Label_", "_", "x"):
        check(f"标号改名不变性 {name!r}",
              assemble(f"{name}: DEC R0\nJNZ {name}"), base)


# ---------- ③ 错误用例：必须带行号地炸 ----------

def test_errors():
    def raises(src, keyword):
        try:
            assemble(src)
            return False
        except AsmError as e:
            return keyword in str(e)

    check("未定义标号", raises("JNZ nowhere", "未定义标号"), True)
    check("重复标号", raises("a: HALT\na: HALT", "重复定义"), True)
    check("寄存器越界", raises("LDI R8, #1", "非法寄存器"), True)
    check("未知助记符", raises("FOO R0", "未知助记符"), True)
    check("操作数数量", raises("ADD R0", "操作数"), True)
    check("立即数缺 #", raises("LDI R0, 5", "# 前缀"), True)
    check("地址缺括号", raises("LD R0, 0x80", "方括号"), True)
    check(".org 后退", raises("HALT\n.org 0", "只许前进"), True)
    check("错误含行号", raises("LDI R0, #1\nFOO", "第 2 行"), True)


# ---------- ④ 端到端：汇编 → 上机 → 与 Python 对账 ----------

def test_end_to_end():
    src = """
        LDI R0, #5
        LDI R1, #1
    loop:
        MUL R1, R0
        DEC R0
        JNZ loop
        HALT
    """
    cpu = CPU(assemble(src))
    n, halted = cpu.run()
    check("阶乘 停机", halted, True)
    check("阶乘 5!=120", cpu.rf.read(1), 120)

    src = """
        LDI R0, #5
        LDI R1, #0
    loop:
        ADD R1, R0
        DEC R0
        JNZ loop
        ST  R1, [0x90]     ; 结果存数据区
        LD  R2, [msg]      ; 从数据区取一个字符（地址用标号！）
        HALT
    .org 0x80
    msg:
        .db "HI"
    """
    cpu = CPU(assemble(src))
    n, halted = cpu.run()
    check("累加 停机", halted, True)
    check("累加 R1=15", cpu.rf.read(1), 15)
    check("存内存 0x90", cpu.ram.read(0x90), 15)
    check("取数据区字符", cpu.rf.read(2), ord("H"))


def main():
    for name, fn in [
        ("编码差分", test_encode_diff),
        ("标号与伪指令", test_labels_directives),
        ("标号改名不变性", test_label_rename),
        ("错误用例", test_errors),
        ("端到端上机", test_end_to_end),
    ]:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
