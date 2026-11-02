"""第十一个程序：猜数字——I/O 对话机（人猜机 / 机猜人两幕）。

tenth 教机器"说"数字（print_dec），本站教它"听"（parse_dec：读键、
回显、按十进制累加）——I/O 全双工从回声机升级成对话机。机器侧源码
全部从 ASM/dec_io.asm 库拼接（项目第一个真正的程序库，驱动在前、
库在后），微 ABI 与 tenth 同款。

两幕：
  第一幕  人猜机（经典）：LFSR 藏一个 0~99 的秘密数，你猜它答
          '<' 猜小了 / '>' 猜大了 / '=' 中了，命中后打印回合数
  第二幕  机猜人（反向）：二分搜索，7 问定乾坤——每个回答 1 bit，
          2^7 = 128 > 100，信息论现场；回答自相矛盾（lo > hi）打印
          '!' 终止——不变量当裁判

中点用防溢出写法 mid = lo + (hi-lo)/2（JDK 二分带 (lo+hi)/2 的 bug
活了九年——int 在 2^31 溢出，我们在 8 位撞 255 的墙，同一道面试名题）。

运行：python eleventh_guess.py            # 两幕剧本回放 + 差分自校验
      python eleventh_guess.py --play 1   # 真玩：你猜机器（随机种子）
      python eleventh_guess.py --play 2   # 真玩：机器猜你（h/l/y 应答）

内存：程序 ≤0xE7；第二幕 mid 暂存格 0xE8；栈 0xFB 向下；I/O 阁楼
0xFC~0xFF（端口/栈已分家）。mid 格曾放 0xE0——被自检断言抓到程序越界
压格（功能测试侥幸全绿，因为被压的是第二幕永不执行的 lfsr 死代码）：
地图纪律比功能测试先看见碰撞。
"""
import os
import sys

from ASM.asm import assemble
from CPU import isa
from CPU.cpu import CPU
from MEM.ram import RAM

MID = 0xE8          # 第二幕 mid 暂存格（寄存器满员，内存帮忙）
SP_EMPTY = 0xFC     # 空栈哨兵（端口/栈分家后的惯例）

LIB = open(os.path.join(os.path.dirname(__file__), "ASM", "dec_io.asm"),
           encoding="utf-8").read()


def driver_a(seed):
    """第一幕驱动：人猜机（种子字面量进代码——剧本回放全程确定）。"""
    return f"""\
; ---- 第一幕：人猜机——LFSR 藏数，你猜它答 ----
    LDI R5, #0              ; 常数三件套（0 / 10 / 48）
    LDI R6, #10
    LDI R7, #48
    LDI R0, #{seed}         ; 种子
    CALL lfsr
    MOV R1, R0              ; 秘密数候选（R1 在全部库调用下幸存）
    LDI R3, #100
s_trim:                     ; mod 100（减法版，最多两轮；AND 99 是位掩模不是取模）
    CMP R1, R3
    JNC s_ok                ; C=0 <=> R1 < 100
    SUB R1, R3
    JMP s_trim
s_ok:
    LDI R4, #0              ; 回合计数（R4 同样幸存）
g_loop:
    CALL parse_dec          ; R0 = 猜测值（带回显）
    INC R4
    CMP R0, R1              ; 猜测 vs 秘密：C=1 <=> 猜测 >= 秘密
    JZ  g_hit
    JNC g_less              ; 猜小了
    LDI R0, #62             ; '>' 猜大了
    ST  R0, [0xFE]
    LDI R0, #13
    ST  R0, [0xFE]
    JMP g_loop
g_less:
    LDI R0, #60             ; '<' 猜小了
    ST  R0, [0xFE]
    LDI R0, #13
    ST  R0, [0xFE]
    JMP g_loop
g_hit:
    LDI R0, #61             ; '=' 中了
    ST  R0, [0xFE]
    LDI R0, #13
    ST  R0, [0xFE]
    MOV R0, R4
    CALL print_dec          ; 回合数
    LDI R0, #13
    ST  R0, [0xFE]
    HALT
"""


DRIVER_B = """\
; ---- 第二幕：机猜人——二分搜索，7 问定乾坤 ----
    LDI R5, #0
    LDI R6, #10
    LDI R7, #48
    LDI R1, #0              ; lo
    LDI R2, #99             ; hi
    LDI R4, #0              ; q（问数）
b_loop:
    MOV R0, R2
    SUB R0, R1              ; hi - lo（不变量 lo<=hi：永不借位）
    SHR R0                  ; (hi-lo)/2
    ADD R0, R1              ; mid = lo + ...：结果 <= hi，8 位永不回绕
    ST  R0, [0xE8]          ; mid 存格（寄存器满员，内存帮忙）
    CALL print_dec          ; 亮出猜测
    LDI R0, #63             ; '?'
    ST  R0, [0xFE]
w_loop:                     ; 等单键 h/l/y（忽略行尾回车）
    LD  R0, [0xFC]
    CMP R0, R5
    JZ  w_loop
    LDI R3, #13
    CMP R0, R3
    JZ  w_loop
    ST  R0, [0xFE]          ; 回显应答
    LDI R3, #13
    ST  R3, [0xFE]
    INC R4                  ; 问数 +1
    LDI R3, #121            ; 'y'
    CMP R0, R3
    JZ  b_hit
    LDI R3, #104            ; 'h'：猜大了 -> hi = mid-1
    CMP R0, R3
    JZ  b_high
    LD  R3, [0xE8]          ; 其余当 'l'：猜小了 -> lo = mid+1
    INC R3
    MOV R1, R3
    JMP b_check
b_high:
    LD  R3, [0xE8]
    CMP R3, R5              ; mid==0 还说猜大？——谎言（再低就回绕成 255）
    JZ  b_lie
    DEC R3
    MOV R2, R3
b_check:
    MOV R0, R1
    CMP R0, R2              ; lo vs hi：C=1 <=> lo >= hi
    JZ  b_loop              ; 相等：还剩唯一候选，再问一次
    JC  b_lie               ; lo > hi：回答自相矛盾，不变量被打破
    JMP b_loop
b_hit:
    LDI R0, #61             ; '='
    ST  R0, [0xFE]
    LDI R3, #13
    ST  R3, [0xFE]
    MOV R0, R4
    CALL print_dec          ; 问数
    LDI R3, #13
    ST  R3, [0xFE]
    HALT
b_lie:
    LDI R0, #33             ; '!' 你撒谎
    ST  R0, [0xFE]
    HALT
"""


class DialogDevice(RAM):
    """键盘 0xFC + 控制台 0xFE 的对话设备。

    队列空时：剧本模式返回 0 哨兵（机器忙等下一拍再试）；
    --play 模式阻塞读 stdin 一行（拆成单键 + CR 投喂）——回合制游戏
    不需要实时键盘，input() 的阻塞就是天然的节拍。
    """

    def __init__(self, keys=None, interactive=False):
        super().__init__()
        self.out = []
        self.keys = list(keys or [])
        self.interactive = interactive

    def read(self, addr):
        if (addr & 0xFF) == 0xFC:
            if self.keys:
                return self.keys.pop(0)
            if self.interactive:
                while not self.keys:
                    line = input("你> ")
                    self.keys.extend(ord(c) & 0xFF for c in line)
                    self.keys.append(13)
                return self.keys.pop(0)
            return 0
        return super().read(addr)

    def write(self, addr, value):
        super().write(addr, value)
        if (addr & 0xFF) == 0xFE:
            self.out.append(value & 0xFF)


def make_machine(code, keys=None, interactive=False):
    cpu = CPU()
    cpu.ram = DialogDevice(keys, interactive)
    cpu.ram.load_program(code)
    cpu.clk.attach(cpu.ram)
    return cpu


def text(tape):
    """输出带 -> 可读文本（13 渲染为换行）。"""
    return "".join(chr(b) if b != 13 else "\n" for b in tape)


# ---------- 独立参考实现（差分用，与机器零共享代码） ----------

def ref_lfsr(s):
    b = s & 1
    s >>= 1
    return s ^ 0xB8 if b else s


def bisect(secret):
    """二分策略生成猜测序列（第一幕的"聪明玩家"用）。"""
    lo, hi, gs = 0, 99, []
    while True:
        g = lo + (hi - lo) // 2
        gs.append(g)
        if g == secret:
            return gs
        if g < secret:
            lo = g + 1
        else:
            hi = g - 1


def ref_act1(seed, guesses):
    """第一幕参考：返回 (期望转录, 秘密数, 回合数)。"""
    secret = ref_lfsr(seed) % 100
    out = []
    for n, g in enumerate(guesses, 1):
        out += [ord(c) for c in str(g)] + [13]              # 回显
        if g < secret:
            out += [ord("<"), 13]
        elif g > secret:
            out += [ord(">"), 13]
        else:
            out += [ord("="), 13] + [ord(c) for c in str(n)] + [13]
            return out, secret, n
    raise ValueError("剧本没猜中就耗尽了")


def ref_act2(secret):
    """第二幕参考：返回 (期望转录, 应答剧本, 问数)。"""
    lo, hi, q = 0, 99, 0
    out, keys = [], []
    while True:
        mid = lo + (hi - lo) // 2
        q += 1
        out += [ord(c) for c in str(mid)] + [ord("?")]
        if mid == secret:
            keys += [ord("y"), 13]
            out += [ord("y"), 13, ord("="), 13]
            out += [ord(c) for c in str(q)] + [13]
            return out, keys, q
        if mid > secret:
            keys += [ord("h"), 13]
            out += [ord("h"), 13]
            hi = mid - 1
        else:
            keys += [ord("l"), 13]
            out += [ord("l"), 13]
            lo = mid + 1


TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}]\n  got  {got}\n  want {want}")
    return got == want


# ---------- 自检 ----------

def toolchain_check():
    for name, code in (("第一幕像", assemble(driver_a(1) + LIB)),
                       ("第二幕像", assemble(DRIVER_B + LIB))):
        for i in range(0, len(code), 2):
            isa.decode(code[i], code[i + 1])
        ok = len(code) <= MID
        print(f"  自检 {name}：{len(code):>3} 字节（上限 0x{MID:X}），"
              f"逐条可译码 {'✓' if ok else '✗'}")


# ---------- 第一幕：人猜机差分 ----------

def act1():
    print("第一幕：人猜机（LFSR 藏数，你猜它答）——差分对独立参考实现")
    strategies = [
        ("二分", lambda s: bisect(s)),
        ("线性", lambda s: list(range(0, s + 1))),
        ("首猜命中", lambda s: [s]),
        ("边界游", lambda s: [0, 99, s]),
    ]
    fails = 0
    print(f"  {'种子':>4} {'策略':>4} {'秘密':>4} {'回合':>4} │ 判定")
    print("  " + "─" * 40)
    for seed in (1, 2, 7, 123, 255):
        secret = ref_lfsr(seed) % 100
        for sname, fn in strategies:
            guesses = fn(secret)
            keys = [ord(c) for g in guesses for c in f"{g}\r"]
            cpu = make_machine(assemble(driver_a(seed) + LIB), keys)
            cpu.run()
            want, _, rounds = ref_act1(seed, guesses)
            ok = check(f"种子{seed}/{sname}",
                       (cpu.ram.out, cpu.halted, cpu.sp.value),
                       (want, True, SP_EMPTY))
            fails += not ok
            print(f"  {seed:>4} {sname:>4} {secret:>4} {rounds:>4} │ {'✓' if ok else '✗'}")
    print("  " + "─" * 40)
    print("  第一幕全部通过 ✓" if fails == 0 else f"  第一幕 {fails} 例失败 ✗")


# ---------- 第二幕：机猜人差分 ----------

def act2():
    print("\n第二幕：机猜人（二分搜索）——差分对独立参考实现")
    fails = 0
    print(f"  {'秘密':>4} {'问数':>4} │ 判定")
    print("  " + "─" * 28)
    code = assemble(DRIVER_B + LIB)
    for secret in (0, 1, 37, 50, 99, 98, 42):
        want, keys, q = ref_act2(secret)
        cpu = make_machine(code, keys)
        cpu.run()
        ok = check(f"秘密{secret}", (cpu.ram.out, cpu.halted, cpu.sp.value),
                   (want, True, SP_EMPTY))
        fails += not ok
        print(f"  {secret:>4} {q:>4} │ {'✓' if ok else '✗'}"
              f"{'（≤7 ✓）' if q <= 7 else '（超 7 问 ✗）'}")
    # 说谎剧本：一路喊"猜大了"——mid 到 0 还喊大即谎言（回绕防护岗哨）
    keys = [ord(c) for _ in range(20) for c in "h\r"]
    cpu = make_machine(code, keys)
    cpu.run()
    ok = check("说谎检测", (cpu.ram.out[-1], cpu.halted), (ord("!"), True))
    fails += not ok
    print(f"  说谎 {'!':>4} │ {'✓' if ok else '✗'}（lo>hi / mid=0 回绕双重岗哨）")
    print("  " + "─" * 28)
    print("  第二幕全部通过 ✓" if fails == 0 else f"  第二幕 {fails} 例失败 ✗")


def main():
    toolchain_check()
    act1()
    act2()
    print("\n" + "═" * 56)
    print(f"两幕 {TOTAL} 项断言全部通过 ✓" if FAILS == 0
          else f"{TOTAL} 项断言中 {FAILS} 项失败 ✗")
    print("验收结论：print/parse 对偶成型（说数字/听数字），库文件制首航；")
    print("二分 7 问 = 信息论现场，说谎检测 = 不变量当裁判。")


if __name__ == "__main__":
    if "--play" in sys.argv:
        act = "2" if "2" in sys.argv[1:] else "1"
        if act == "1":
            import random
            seed = random.randrange(1, 256)
            print("我想好了一个 0~99 的数。猜猜看（数字 + 回车；< 小了 / > 大了 / = 中了）")
            cpu = make_machine(assemble(driver_a(seed) + LIB), interactive=True)
        else:
            print("你心里想一个 0~99 的数，我来猜。应答：h=猜大了 l=猜小了 y=中了")
            cpu = make_machine(assemble(DRIVER_B + LIB), interactive=True)
        cpu.run()
        print("\n[机器转录]")
        print(text(cpu.ram.out))
        sys.exit(0)
    main()
