"""第十个程序：验收程序——冒泡排序 + 十进制打印（工具链阅兵式）。

前 15 个示例各演示一个新机制；本程序反过来：不新增任何东西，以
"真实 8 位机程序员"的身份解两个最经典的日常任务，把汇编器、子程序、
栈、指针、标志分支、I/O 端口全部当理所当然的建材自然用上——
哪个环节掉链子，哪个环节就露馅，故名"验收"。

本文件的全项目第一次：
  - 源码主体是 .asm 文本，经 assemble() 生成机器码（手拼 isa.I_* 正式退役）
  - 子程序当库函数被上层循环调用——调用约定接受复用检验
  - 栈的两种真实用法同框：现场保存（序言/尾声）与算法性逆序（数字出栈）

结构：常驻库（sort8 / print_dec / 内部 div10）+ 三个驱动，三幕差分：
  第一幕  print_dec 单值差分（对 str(n)）：数制转换 + 栈逆序
  第二幕  sort8 数组差分（对 sorted()）：双循环 + 指针 + 提前退出
  第三幕  合体端到端：乱序数组 → 排序 → 逐个十进制打印，对账 Python

调用约定（本文件微型 ABI）：
  R0        参数/返回值，传参即消耗（调用方每轮重装）
  R1-R4     草稿区，被调方自保存（序言 PUSH / 尾声 POP）
  R5/R6/R7  全局常数 0/10/48（驱动开头设置，全员只读）
  例外      div10 是内部子程序：R2 出余数，仅被 print_dec 调用

内存布局：程序 ≤0x93；控制台端口 0x9E；数组 0xA0~（N 字节）；
          栈从 0xFF 向下（峰值 ~7 层，最深 0xF9——三方互不侵犯）。

★ 本程序的端口为什么不是惯例的 0xFE——一个真实的内存映射设计问题：
  栈从 0xFF 向下生长，第二格恰好是 0xFE。本程序是第一个"子程序栈 ×
  控制台端口"合体用户，撞了个正着：PUSH 存现场的动作被端口钩子当成
  打字捕获（多出 \x00）；ST 打数字又覆盖栈里保存的 R2，尾声"还原"出
  一个 ASCII 数字泄漏进下一轮输出。真实硬件靠内存映射分家解决（6502
  专辟第 1 页做栈，正是为了与 I/O 区隔离）；本程序把端口搬到 0x9E
  ——避开栈生长区。机器级的正规化（端口区/栈区重划）记入后续工作。
"""
from ASM.asm import assemble
from CPU import isa
from CPU.cpu import CPU
from MEM.ram import RAM

PORT = 0x9E         # 控制台端口（本程序专用地址，避开栈区——见上）
ARR = 0xA0          # 数组基地址（惯例数据区）


class ConsoleDevice(RAM):
    """带写钩子的内存：照常存储，写端口则把字节收进输出带。"""

    def __init__(self):
        super().__init__()
        self.out = []

    def write(self, addr, value):
        super().write(addr, value)              # 照常登记写请求
        if (addr & 0xFF) == PORT:
            self.out.append(value & 0xFF)


def make_machine(code, array=None):
    """汇编映像 → 换好控制台内存的 CPU（数组一并烧写）。"""
    cpu = CPU()                                 # 先造 CPU（用默认内存）
    cpu.ram = ConsoleDevice()                   # 换"带控制台"的内存
    cpu.ram.load_program(code)                  # 烧写程序
    cpu.clk.attach(cpu.ram)                     # 挂时钟线（原内存空转无害）
    for i, v in enumerate(array or []):         # 烧写数组（初始化，不走时钟）
        cpu.ram.data[(ARR + i) & 0xFF] = v & 0xFF
    return cpu


# ================= 常驻库（汇编文本） =================

LIB = """\
; ============ 库：sort8 / print_dec / div10 ============
; 约定：R0 参数/返回（消耗）；R1-R4 草稿（被调方自保存）；
;       R5/R6/R7 = 常数 0/10/48（驱动设置，全员只读）

; ---- div10（内部）：R0/10 -> R0=商, R2=余数(0..9)；用 R4 ----
; 例外子程序：R2 出余数，仅被 print_dec 调用，不守草稿自保存约
div10:
    LDI R4, #0              ; 商清零
d10_loop:
    CMP R0, R6              ; R0>=10? 本机 C=1 <=> 够减（借位取反）
    JC  d10_sub             ; 够减 -> 再减一轮
    MOV R2, R0              ; 不够减：余数 = 剩余
    MOV R0, R4              ; 返回商
    RET
d10_sub:
    SUB R0, R6              ; R0 -= 10
    INC R4                  ; 商 += 1
    JMP d10_loop

; ---- print_dec（公开）：R0 = 0..255 -> 0xFE 逐字符；R0 消耗 ----
print_dec:
    PUSH R2                 ; 序言：草稿区自保存
    PUSH R3
    PUSH R4
    LDI R3, #0              ; 数字个数（8 位数 1..3 个）
pd_split:
    CALL div10              ; R0 = 商, R2 = 余数
    ADD R2, R7              ; +48 -> ASCII
    PUSH R2                 ; * 低位先压栈（个位最先算出来）
    INC R3
    CMP R0, R5              ; 商 == 0？（R5 = 0）
    JNZ pd_split            ; 还有高位 -> 继续拆
pd_pop:
    POP R0                  ; * 后进先出 = 高位先出
    ST  R0, [0x9E]          ; 打一个字符（端口 0x9E——避开栈区，见文件头）
    DEC R3
    JNZ pd_pop
    POP R4                  ; 尾声：逆序还原现场
    POP R3
    POP R2
    RET

; ---- sort8（公开）：R0 = N（>=2），数组 0xA0 起就地升序 ----
sort8:
    PUSH R1                 ; 序言：自保存
    PUSH R2
    PUSH R3
    PUSH R4
    DEC R0                  ; 每趟比较次数 = N-1
    PUSH R0                 ; * bound 常驻栈顶——寄存器不够，栈来凑
s_pass:
    POP R0                  ; 取 bound
    PUSH R0                 ; 原样压回（保持栈位不变）
    LDI R1, #0xA0           ; 内层指针复位
    LDI R4, #0              ; 交换旗帜（R5 是全局 0，不能挪用）
s_inner:
    LDX R2, R1              ; R2 = arr[j]
    INC R1                  ; 指针 -> j+1
    LDX R3, R1              ; R3 = arr[j+1]
    CMP R2, R3              ; C=1 <=> R2 >= R3（无符号）
    JZ  s_end               ; * 相等跳过——否则旗帜永不归零（死循环）
    JC  s_swap              ; R2 > R3：逆序，换
    JMP s_end
s_swap:
    STX R2, R1              ; mem[j+1] <- 较大者
    DEC R1
    STX R3, R1              ; mem[j] <- 较小者
    INC R1                  ; 指针归位
    LDI R4, #1              ; 本趟发生过交换
s_end:
    DEC R0
    JNZ s_inner
    CMP R4, R5              ; 本趟零交换？
    JNZ s_pass              ; 有交换 -> 再来一趟
    POP R0                  ; 清掉栈上的 bound
    POP R4                  ; 尾声：逆序还原
    POP R3
    POP R2
    POP R1
    RET
"""


def driver_a(n):
    """第一幕驱动：打印单值 n。（驱动拼在库前——机器从地址 0 启动，
    库放后面只当"零件仓"，永不自行执行；CALL 的前向引用汇编器两遍解决）"""
    return f"""\
    LDI R5, #0
    LDI R6, #10
    LDI R7, #48
    LDI R0, #{n}
    CALL print_dec
    HALT
"""


def driver_b(n):
    """第二幕驱动：排序 N 个元素。"""
    return f"""\
    LDI R5, #0
    LDI R6, #10
    LDI R7, #48
    LDI R0, #{n}
    CALL sort8
    HALT
"""


DRIVER_C = """\
    LDI R5, #0
    LDI R6, #10
    LDI R7, #48
    LDI R0, #8
    CALL sort8              ; 排序（R1-R4 有序归来，随便接着用）
    LDI R1, #0xA0           ; 打印游标
    LDI R4, #8              ; 计数
c_loop:
    LDX R0, R1              ; R0 = arr[i]（每轮重装——R0 是消耗品）
    CALL print_dec          ; 打印（好公民：不碰 R1，R2-R4 自还原）
    LDI R0, #32             ; 空格分隔
    ST  R0, [0x9E]
    INC R1
    DEC R4
    JNZ c_loop
    HALT
"""

TOTAL = 0
FAILS = 0


def check(name, got, want):
    """房子风格的三重断言打包：结果对账 + 停机 + SP 归零。"""
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")
    return got == want


# ---------- 工具链自检（本站特有） ----------

def toolchain_check(code, name):
    """汇编产物逐条可译码（无非法字节）+ 体积不越数组区。"""
    for i in range(0, len(code), 2):
        isa.decode(code[i], code[i + 1])        # 非法字节会在此抛异常
    ok = len(code) <= ARR
    print(f"  自检 {name}：{len(code):>3} 字节（上限 0x{ARR:X}），"
          f"逐条可译码 {'✓' if ok else '✗'}")
    return ok


def assemble_img(driver):
    """驱动在前（机器从 0 启动），库在后（零件仓，永不自行执行）。"""
    return assemble(driver + LIB)


# ---------- 第一幕：print_dec 单值差分 ----------

def act1():
    print("第一幕：print_dec 单值差分（对 Python str(n)）")
    cases = [0, 1, 5, 9, 10, 42, 99, 100, 123, 128, 200, 254, 255]
    print(f"  {'n':>5} {'机器输出':>8} {'期望':>8} {'执行':>6} │ 判定")
    print("  " + "─" * 40)
    for val in cases:
        cpu = make_machine(assemble_img(driver_a(val)))
        instrs, halted = cpu.run()
        got = "".join(chr(b) for b in cpu.ram.out)
        check(f"打印 {val}", (got, halted, cpu.sp.value), (str(val), True, 0))
        print(f"  {val:>5} {got:>8} {str(val):>8} {instrs:>6} │"
              f" {'✓' if got == str(val) else '✗'}")


# ---------- 第二幕：sort8 数组差分 ----------

def act2():
    print("\n第二幕：sort8 数组差分（对 Python sorted()）")
    cases = [
        ("已升序  ", [1, 2, 3, 4, 5, 6, 7, 8]),          # 最好情况：1 趟毕业
        ("完全逆序", [8, 7, 6, 5, 4, 3, 2, 1]),          # 最坏情况：趟趟全跑
        ("含重复  ", [5, 3, 5, 1, 3, 5, 1, 3]),          # 相等跳过交换
        ("全相同  ", [7] * 8),                            # 防死循环岗哨
        ("数值边界", [0, 255, 128, 1, 254, 2, 127, 3]),  # 0/255 参与比较
        ("乱序    ", [(i * 37 + 11) & 0xFF for i in range(8)]),
        ("N=2 短数", [9, 1]),                             # 参数 N 真的被测到
    ]
    print(f"  {'等价类':<8} {'执行':>6} │ 排序结果")
    print("  " + "─" * 56)
    for name, arr in cases:
        cpu = make_machine(assemble_img(driver_b(len(arr))), arr)
        instrs, halted = cpu.run()
        got = [cpu.ram.read(ARR + i) for i in range(len(arr))]
        want = sorted(arr)
        ok = check(f"排序 {name}", (got, halted, cpu.sp.value), (want, True, 0))
        print(f"  {name:<8} {instrs:>6} │ {got} {'✓' if ok else '✗ 期望 ' + str(want)}")


# ---------- 第三幕：合体端到端 ----------

def act3():
    print("\n第三幕：合体端到端——排序后逐个打印（对账 Python）")
    cases = [
        [5, 3, 8, 1, 9, 2, 7, 4],
        [200, 0, 255, 10, 10, 128, 1, 99],               # 含重复 + 边界值
        [(i * 53 + 29) & 0xFF for i in range(8)],
    ]
    code = assemble(DRIVER_C + LIB)
    for arr in cases:
        cpu = make_machine(code, arr)
        instrs, halted = cpu.run()
        got = "".join(chr(b) for b in cpu.ram.out)
        want = " ".join(map(str, sorted(arr))) + " "      # 机器每数后打一个空格
        consts_ok = [cpu.rf.read(i) for i in (5, 6, 7)] == [0, 10, 48]
        ok = check(f"端到端 {arr}",
                   (got, halted, cpu.sp.value, consts_ok), (want, True, 0, True))
        print(f"  机器输出：{got!r}{'✓' if ok else ' ✗ 期望 ' + repr(want)}（{instrs} 条）")
        print(f"  全局常数幸存（R5/R6/R7 仍是 0/10/48）：{'✓' if consts_ok else '✗'}"
              f"  SP 归零：{'✓' if cpu.sp.value == 0 else '✗'}")


# ---------- 账本 ----------

def ledger():
    print("\n账本（实测）：")
    for val in (5, 200):                                  # 一位数 vs 三位数
        cpu = make_machine(assemble_img(driver_a(val)))
        instrs, _ = cpu.run()
        print(f"  print_dec({val:>3})：{instrs:>4} 条")
    counts = {}
    for name, arr in (("已升序", [1, 2, 3, 4, 5, 6, 7, 8]),
                      ("完全逆序", [8, 7, 6, 5, 4, 3, 2, 1])):
        cpu = make_machine(assemble_img(driver_b(8)), arr)
        counts[name], _ = cpu.run()
    print(f"  sort8 已升序：{counts['已升序']:>4} 条（1 趟毕业）")
    print(f"  sort8 完全逆序：{counts['完全逆序']:>4} 条（趟趟全跑）")
    print(f"  提前退出的收益：{counts['完全逆序'] - counts['已升序']} 条"
          f"（{counts['完全逆序']} → {counts['已升序']}）")


def main():
    toolchain_check(assemble_img(DRIVER_C), "驱动+库")
    print("  端口 0x9E（避栈区）；0xFE 与栈第 2 格相撞的花絮见文件头注释")
    act1()
    act2()
    act3()
    ledger()
    print("\n" + "═" * 62)
    print(f"三幕 {TOTAL} 项断言全部通过 ✓" if FAILS == 0
          else f"{TOTAL} 项断言中 {FAILS} 项失败 ✗")
    print("验收结论：.asm 文本 → 机器码 → 正确结果，工具链全链路无断点；")
    print("子程序可复用（print_dec 被循环安全调用 8 次），栈纪律全程 SP 归零。")


if __name__ == "__main__":
    main()
