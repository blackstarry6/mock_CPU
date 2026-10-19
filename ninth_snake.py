"""第九个程序：贪吃蛇（复古模式，约 1 FPS）——键盘 + 帧缓冲首次合体。

架构（方案 B：先跑通，不改 gate.py）：
- 键盘即时钟：机器阻塞等键，驱动端每拍投喂两个"增量键码"（dx+2、dy+2 ∈
  {1,2,3}，避开 0=无键哨兵）——真玩时按键只改变投什么，不改变何时投
- 帧缓冲即蛇身：8×8 场地 0xC0~0xFF，蛇身格存"年龄"（头=1，每拍 +1，
  超过蛇长即清零=尾巴缩回）；食物=255。单一数据结构，零重复记账
- 食物：机内 Galois LFSR（种子 1，抽头 0xB8），落在非空格则重抽
- 撞检：坐标 ≥8（含回绕 255）= 撞墙；目标格非空非食物 = 撞自己
- 初始局面由 .db 烧写（蛇身/蛇长/LFSR/首食物标志），机器只初始化 3 个寄存器

验收：剧本回放（固定键序）与 Python 参考实现逐格差分——两套独立实现
跑同一剧本，最终棋盘/分数/结局必须完全一致。
真玩模式：python ninth_snake.py --play（WASD/方向键，msvcrt 非阻塞读键）。
"""
import sys
import time

from ASM.asm import assemble
from CPU.cpu import CPU
from MEM.ram import RAM

GAME = r"""
        LDI R5, #0          ; 常数 0
        LDI R1, #4          ; 头 x=4
        LDI R2, #4          ; 头 y=4
        JMP gate            ; cellE 初值 1 → 开局先放第一颗食物
poll:   LD  R0, [0xFC]      ; 等键（键盘即时钟）
        CMP R0, R5
        JZ  poll
        DEC R0
        DEC R0              ; 键码 = 增量 + 2
        ADD R1, R0          ; x += dx
poll2:  LD  R0, [0xFC]
        CMP R0, R5
        JZ  poll2
        DEC R0
        DEC R0
        ADD R2, R0          ; y += dy
        LDI R0, #8
        CMP R1, R0          ; 越界（回绕 255 也 ≥8）→ 撞墙
        JC  over
        CMP R2, R0
        JC  over
        MOV R3, R2          ; 格址 = 0xC0 + y*8 + x
        SHL R3
        SHL R3
        SHL R3
        ADD R3, R1
        LDI R0, #0xC0
        ADD R3, R0
        LDX R4, R3          ; 读目标格
        CMP R4, R5
        JZ  ok              ; 空 → 普通移动
        INC R4              ; 255+1 回绕成 0 → 是食物
        JZ  eat
over:   LDI R0, #1          ; 其余非空 → 撞自己；坠到这里的还有撞墙
        ST  R0, [cellO]
        HALT
ok:     LDI R0, #0
        ST  R0, [cellE]
        JMP sweep
eat:    LD  R0, [cellS]
        INC R0
        ST  R0, [cellS]     ; score++
        LD  R0, [cellL]
        INC R0
        ST  R0, [cellL]     ; 蛇长 +1
        LDI R0, #1
        ST  R0, [cellE]
sweep:  ST  R3, [cellA]     ; 暂存新头地址（扫描占用 R3）
        LDI R6, #0xC0
        LDI R7, #64
        LD  R0, [cellL]
        INC R0              ; R0 = 蛇长+1（过期阈值）
        LDI R4, #255        ; R4 = 食物标记
sw:     LDX R3, R6          ; —— 全场扫描：年龄 +1，超龄清零 ——
        CMP R3, R5
        JZ  sn
        CMP R3, R4
        JC  sn              ; ≥255 是食物，跳过
        INC R3
        CMP R3, R0
        JC  sc              ; 年龄 > 蛇长 → 尾巴缩回
        STX R3, R6
        JMP sn
sc:     STX R5, R6
sn:     INC R6
        DEC R7
        JNZ sw
        LD  R3, [cellA]
        LDI R0, #1
        STX R0, R3          ; 新头年龄 = 1
gate:   LD  R0, [cellE]
        CMP R0, R5
        JNZ food            ; 刚吃过 → 放新食物
        JMP poll
food:   LD  R0, [cellR]     ; —— Galois LFSR：s >>=1，低位为 1 则 ^0xB8 ——
        SHR R0
        JNC fno
        LDI R3, #0xB8
        XOR R0, R3
fno:    ST  R0, [cellR]
        MOV R3, R0
        LDI R0, #0x3F
        AND R3, R0          ; 格号 = s & 63
        LDI R0, #0xC0
        ADD R3, R0
        LDX R4, R3
        CMP R4, R5
        JZ  fset            ; 空格 → 落食
        JMP food            ; 占用 → 重抽（LFSR 已前进）
fset:   LDI R0, #255
        STX R0, R3
        JMP poll

.org 0xB8
cellL:  .db 3               ; 蛇长
cellS:  .db 0               ; 分数
cellO:  .db 0               ; 结束标志
cellR:  .db 1               ; LFSR 种子
cellA:  .db 0               ; 新头地址暂存
cellE:  .db 1               ; "刚吃"标志（初值 1 → 开局先放食物）

.org 0xE2
        .db 3, 2, 1         ; 初始蛇身（x=2,3,4；尾=3 → 头=1，头是最新）
"""

C_L, C_S, C_O, C_R = 0xB8, 0xB9, 0xBA, 0xBB
DIRS = {"w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}


class SnakeKeyboardRAM(RAM):
    """只钩一个口的极简设备：读 0xFC = 取键（空队列返回 0）。"""

    PORT = 0xFC

    def __init__(self):
        super().__init__()
        self.queue = []

    def type(self, keys):                # 投喂若干键码
        self.queue.extend(keys)

    def read(self, addr):
        if (addr & 0xFF) == self.PORT:
            return self.queue.pop(0) if self.queue else 0
        return super().read(addr)


# ---------- Python 参考实现（差分验收的对照面） ----------

class RefSnake:
    """与机器侧规则逐条对应的纯 Python 贪吃蛇。"""

    def __init__(self):
        self.g = [0] * 64
        for i, age in enumerate((3, 2, 1)):     # 初始蛇身同 .db（尾→头）
            self.g[4 * 8 + 2 + i] = age
        self.x = self.y = 4
        self.length = 3
        self.score = 0
        self.over = 0
        self.lfsr = 1
        self.place_food()                        # 开局先放食物（同 cellE=1）

    def place_food(self):
        while True:
            lsb = self.lfsr & 1
            self.lfsr = (self.lfsr >> 1) ^ (0xB8 if lsb else 0)
            if self.g[self.lfsr & 63] == 0:
                self.g[self.lfsr & 63] = 255
                return

    def step(self, dx, dy):
        self.x = (self.x + dx) & 255
        self.y = (self.y + dy) & 255
        if self.x >= 8 or self.y >= 8:
            self.over = 1
            return
        a = self.y * 8 + self.x
        ate = self.g[a] == 255
        if not ate and self.g[a] != 0:
            self.over = 1                        # 撞自己
            return
        if ate:
            self.score += 1
            self.length += 1
        for i, v in enumerate(self.g):           # 全场扫描：年龄 +1，超龄清零
            if 0 < v < 255:
                self.g[i] = v + 1 if v + 1 <= self.length else 0
        self.g[a] = 1
        if ate:
            self.place_food()


# ---------- 驱动端 ----------

def render(ram, cpu, tick, final=False):
    hx, hy = cpu.rf.read(1), cpu.rf.read(2)
    print("+" + "-" * 8 + f"+   拍 {tick}  分数 {ram.read(C_S)}  蛇长 {ram.read(C_L)}"
          + ("   GAME OVER" if final else ""))
    for y in range(8):
        row = ""
        for x in range(8):
            v = ram.read(0xC0 + y * 8 + x)
            row += "O" if (x, y) == (hx, hy) else "@" if v == 255 else "#" if v else "."
        print("|" + row + "|")
    print("+" + "-" * 8 + "+")


def make_machine():
    code = assemble(GAME)     # 代码若越过 0xB8，.org 会当场报"只许前进"
    assert code[0xB8] == 3 and code[0xBD] == 1   # cellL=3、cellE=1 烧写就位
    ram = SnakeKeyboardRAM()
    ram.load_program(code)
    cpu = CPU()
    cpu.ram = ram
    cpu.clk.attach(ram)
    poll = code.index(0x10)                      # 第一条 LD R0,[0xFC] 的地址
    return ram, cpu, poll


def run_tick(ram, cpu, poll, dx, dy):
    ram.type([(dx + 2) & 0xFF, (dy + 2) & 0xFF])  # 投喂增量键码（+2 避开 0 哨兵）
    while not cpu.halted and not (not ram.queue and cpu.pc.value == poll):
        cpu.step()


def settle(cpu, poll):                           # 开机：放好首食物、走到等键位
    while cpu.pc.value != poll:
        cpu.step()


# 剧本（手推验证过的安全路线）：右3 下3 → 沿第7行吃到食物①(0,7)
# → 上4 右4 吃到食物②(4,3) → 再右4 撞墙结束。期望：分数 2，蛇长 5。
SCRIPT = "ddd" + "sss" + "aaaaaaa" + "wwww" + "dddd" + "dddd"


def script_game():
    """剧本回放 + 与参考实现差分自校验。"""
    ram, cpu, poll = make_machine()
    settle(cpu, poll)
    ref = RefSnake()
    tick = 0
    render(ram, cpu, tick)
    for mv in SCRIPT:
        if cpu.halted:
            break
        tick += 1
        run_tick(ram, cpu, poll, *DIRS[mv])
        ref.step(*DIRS[mv])
        time.sleep(0.02)
    if cpu.halted:
        render(ram, cpu, tick, final=True)
    m_grid = [ram.read(0xC0 + i) for i in range(64)]
    ok = (m_grid == ref.g
          and ram.read(C_S) == ref.score
          and ram.read(C_O) == ref.over == 1)
    print(f"\n自校验：机器分数 {ram.read(C_S)} / 参考分数 {ref.score}，"
          f"64 格{'一致' if m_grid == ref.g else '不一致'}，"
          f"结局 over={ram.read(C_O)} —— {'通过 ✓' if ok else '失败 ✗'}")
    return ok


def play_game():
    """真玩模式：WASD/方向键（Windows msvcrt 非阻塞读键）。"""
    import msvcrt
    ram, cpu, poll = make_machine()
    settle(cpu, poll)
    cur = "d"                                    # 当前方向（也当节拍器）
    opp = {"w": "s", "s": "w", "a": "d", "d": "a"}
    tick = 0
    render(ram, cpu, tick)
    while not cpu.halted:
        time.sleep(0.12)
        while msvcrt.kbhit():                    # 收集真人按键（禁止 180° 掉头）
            k = msvcrt.getwch()
            k = {"H": "w", "P": "s", "K": "a", "M": "d"}.get(k, k.lower())
            if k in DIRS and k != opp[cur]:
                cur = k
        tick += 1
        run_tick(ram, cpu, poll, *DIRS[cur])
        render(ram, cpu, tick)
    render(ram, cpu, tick, final=True)
    print(f"游戏结束！最终分数 {ram.read(C_S)}，蛇长 {ram.read(C_L)}，共 {tick} 拍")


if __name__ == "__main__":
    if "--play" in sys.argv:
        play_game()
    else:
        sys.exit(0 if script_game() else 1)
