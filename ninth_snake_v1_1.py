"""贪吃蛇 v1.1——修复防掉头双连转漏洞 + 死亡拍双重渲染，附三幕验收。

v1（ninth_snake.py，保持原样不动）的两个问题：
1. 防掉头参照物是"最新意向 cur"而非"实际投喂方向"——同一采样窗口内
   快速按两个键（如上行时 A+S）可让第二个键对照第一个幽灵转向通过
   检查，机器实际收到 180° 反向 → 一拍撞死自己
2. 死亡拍渲染两帧（循环内一帧 + 收尾一帧，内容完全相同）

修复：
1. 拆 cur 为 last_fed（上一拍实际投喂——防掉头的唯一参照，仅在投喂后
   更新）+ pending（下一拍意向，可被按键随时更新）。防线只认"已执行"，
   "意向转两次"骗不过"执行才走一步"
2. run_tick 后若已停机直接 break，终局只出 final 一帧

三幕验收（内嵌自校验）：
  第一幕（回归）：v1.1 跑 v1 同一个 SCRIPT 的差分——机器侧零改动，
                 合法输入下两版行为必须完全一致
  第二幕（立此存照）：内联复刻 v1 旧防线（三行），喂 A+S——旧逻辑
                 放行 180°，bug 文档化
  第三幕（修复证明）：新防线逻辑测试 + 游戏级注入 A+S——'s' 被拦截、
                 蛇存活继续走

真玩模式：python ninth_snake_v1_1.py --play
"""
import sys
import time

from ASM.asm import assemble
from CPU.cpu import CPU
from MEM.ram import RAM

# ---- 机器侧：与 v1 完全相同（一字节不动） ----
GAME = r"""
        LDI R5, #0
        LDI R1, #4
        LDI R2, #4
        JMP gate
poll:   LD  R0, [0xFC]
        CMP R0, R5
        JZ  poll
        DEC R0
        DEC R0
        ADD R1, R0
poll2:  LD  R0, [0xFC]
        CMP R0, R5
        JZ  poll2
        DEC R0
        DEC R0
        ADD R2, R0
        LDI R0, #8
        CMP R1, R0
        JC  over
        CMP R2, R0
        JC  over
        MOV R3, R2
        SHL R3
        SHL R3
        SHL R3
        ADD R3, R1
        LDI R0, #0xC0
        ADD R3, R0
        LDX R4, R3
        CMP R4, R5
        JZ  ok
        INC R4
        JZ  eat
over:   LDI R0, #1
        ST  R0, [cellO]
        HALT
ok:     LDI R0, #0
        ST  R0, [cellE]
        JMP sweep
eat:    LD  R0, [cellS]
        INC R0
        ST  R0, [cellS]
        LD  R0, [cellL]
        INC R0
        ST  R0, [cellL]
        LDI R0, #1
        ST  R0, [cellE]
sweep:  ST  R3, [cellA]
        LDI R6, #0xC0
        LDI R7, #64
        LD  R0, [cellL]
        INC R0
        LDI R4, #255
sw:     LDX R3, R6
        CMP R3, R5
        JZ  sn
        CMP R3, R4
        JC  sn
        INC R3
        CMP R3, R0
        JC  sc
        STX R3, R6
        JMP sn
sc:     STX R5, R6
sn:     INC R6
        DEC R7
        JNZ sw
        LD  R3, [cellA]
        LDI R0, #1
        STX R0, R3
gate:   LD  R0, [cellE]
        CMP R0, R5
        JNZ food
        JMP poll
food:   LD  R0, [cellR]
        SHR R0
        JNC fno
        LDI R3, #0xB8
        XOR R0, R3
fno:    ST  R0, [cellR]
        MOV R3, R0
        LDI R0, #0x3F
        AND R3, R0
        LDI R0, #0xC0
        ADD R3, R0
        LDX R4, R3
        CMP R4, R5
        JZ  fset
        JMP food
fset:   LDI R0, #255
        STX R0, R3
        JMP poll

.org 0xB8
cellL:  .db 3
cellS:  .db 0
cellO:  .db 0
cellR:  .db 1
cellA:  .db 0
cellE:  .db 1

.org 0xE2
        .db 3, 2, 1
"""

C_L, C_S, C_O = 0xB8, 0xB9, 0xBA
DIRS = {"w": (0, -1), "s": (0, 1), "a": (-1, 0), "d": (1, 0)}
OPP = {"w": "s", "s": "w", "a": "d", "d": "a"}
SCRIPT = "ddd" + "sss" + "aaaaaaa" + "wwww" + "dddd" + "dddd"   # 与 v1 相同


class SnakeKeyboardRAM(RAM):
    PORT = 0xFC

    def __init__(self):
        super().__init__()
        self.queue = []

    def type(self, keys):
        self.queue.extend(keys)

    def read(self, addr):
        if (addr & 0xFF) == self.PORT:
            return self.queue.pop(0) if self.queue else 0
        return super().read(addr)


class RefSnake:
    """Python 参考实现（差分对照面，与 v1 相同）。"""

    def __init__(self):
        self.g = [0] * 64
        for i, age in enumerate((3, 2, 1)):
            self.g[4 * 8 + 2 + i] = age
        self.x = self.y = 4
        self.length = 3
        self.score = 0
        self.over = 0
        self.lfsr = 1
        self.place_food()

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
            self.over = 1
            return
        if ate:
            self.score += 1
            self.length += 1
        for i, v in enumerate(self.g):
            if 0 < v < 255:
                self.g[i] = v + 1 if v + 1 <= self.length else 0
        self.g[a] = 1
        if ate:
            self.place_food()


# ---------- ★ 修复 1：收键函数抽离 + last_fed 双变量防线 ----------

def sample_keys(key_batch, last_fed, pending):
    """处理一批按键（游戏级可注入，不再焊死 msvcrt）。

    返回 (新 pending, 本批实际通过的按键列表)。
    防掉头只对照 last_fed（上一拍真实投喂方向）——意向随意改，
    防线永远锚定"已执行"。
    """
    accepted = []
    for k in key_batch:
        if k in DIRS and k != OPP[last_fed]:
            pending = k
            accepted.append(k)
    return pending, accepted


# ---------- ★ 修复 2：死亡拍不再双重渲染（run_tick 后判 halted） ----------

ARROW = {"w": "↑", "s": "↓", "a": "←", "d": "→"}


def render(ram, cpu, tick, final=False, last_fed=None, pending=None):
    hx, hy = cpu.rf.read(1), cpu.rf.read(2)
    hud = ""
    if last_fed is not None:
        star = " ★" if pending != last_fed else ""
        hud = f"   当前:{ARROW[last_fed]}  下一:{ARROW[pending]}{star}"
    print("+" + "-" * 8 + f"+   拍 {tick}  分数 {ram.read(C_S)}  蛇长 {ram.read(C_L)}"
          + hud + ("   GAME OVER" if final else ""))
    for y in range(8):
        row = ""
        for x in range(8):
            v = ram.read(0xC0 + y * 8 + x)
            row += "O" if (x, y) == (hx, hy) else "@" if v == 255 else "#" if v else "."
        print("|" + row + "|")
    print("+" + "-" * 8 + "+")


def make_machine():
    code = assemble(GAME)
    ram = SnakeKeyboardRAM()
    ram.load_program(code)
    cpu = CPU()
    cpu.ram = ram
    cpu.clk.attach(ram)
    poll = code.index(0x10)
    return ram, cpu, poll


def run_tick(ram, cpu, poll, dx, dy):
    ram.type([(dx + 2) & 0xFF, (dy + 2) & 0xFF])
    while not cpu.halted and not (not ram.queue and cpu.pc.value == poll):
        cpu.step()


def settle(cpu, poll):
    while cpu.pc.value != poll:
        cpu.step()


# ---------- 三幕验收 ----------

def act1_regression():
    """第一幕（回归）：v1.1 跑 v1 同一剧本的差分，两版必须逐格一致。"""
    ram, cpu, poll = make_machine()
    settle(cpu, poll)
    ref = RefSnake()
    tick = 0
    for mv in SCRIPT:
        if cpu.halted:
            break
        tick += 1
        run_tick(ram, cpu, poll, *DIRS[mv])
        ref.step(*DIRS[mv])
    m_grid = [ram.read(0xC0 + i) for i in range(64)]
    ok = (m_grid == ref.g and ram.read(C_S) == ref.score and ram.read(C_O) == 1)
    print(f"第一幕（回归）：机器分数 {ram.read(C_S)} / 参考 {ref.score}，"
          f"64 格{'一致' if m_grid == ref.g else '不一致'} —— {'通过 ✓' if ok else '失败 ✗'}")
    return ok


def act2_old_guard():
    """第二幕（立此存照）：复刻 v1 旧防线三行，喂 A+S——bug 必然发生。"""
    def v1_guard(key_batch, cur):
        for k in key_batch:               # v1 的原样逻辑：
            if k in DIRS and k != OPP[cur]:
                cur = k                    # ← 参照物=最新意向，即时更新
        return cur

    last_dir = "w"                         # 蛇正在上行
    fed = v1_guard(["a", "s"], last_dir)   # 快速两连按 A+S
    bug = fed == OPP[last_dir]             # 喂出的恰是 180° 反向
    print(f"第二幕（立此存照）：v1 旧防线收 ['a','s'] → 投喂 {fed!r}"
          f"（上行时 180° 反向 {'被放行 → 一拍撞死，bug 确认 ✗' if bug else '被拦截（不应发生）'}）")
    return bug


def act3_fix_proof():
    """第三幕（修复证明）：新防线拦截 + 游戏级注入 A+S 存活。"""
    # 3a 逻辑级：新防线收同一批键
    pending, accepted = sample_keys(["a", "s"], last_fed="w", pending="w")
    ok3a = pending == "a" and accepted == ["a"]
    print(f"第三幕 3a（新防线）：收 ['a','s'] → 投喂 {pending!r}，"
          f"通过 {accepted}（'s' 被拦截）—— {'通过 ✓' if ok3a else '失败 ✗'}")
    # 3b 游戏级：真机器上注入 A+S——蛇上行途中同窗两键，必须存活且继续
    ram, cpu, poll = make_machine()
    settle(cpu, poll)
    pending = "w"                           # 初始向上（远离初始身体）
    tick = 0
    alive = True
    plan = (["w"] * 3 + [["a", "s"]]        # 上行 3 拍后，第 4 拍窗口灌入 A+S
            + ["a"] * 3 + ["s"] * 5)        # 之后左 3 批（含注入共 4 步到 x=0）、下 5 批
    for batch in plan:
        tick += 1
        run_tick(ram, cpu, poll, *DIRS[pending])
        last_fed = pending
        pending, accepted = sample_keys(batch, last_fed, pending)
        if tick == 4:
            injected_ok = accepted == ["a"]  # 'a' 通过、's' 被拦截
        if cpu.halted:
            alive = False
            break
    ok3b = alive and injected_ok
    injected_str = str(accepted)
    print(f"第三幕 3b（游戏级注入）：上行途中第 4 拍灌入 ['a','s'] → "
          f"通过 {injected_str}（'s' 被拦截），蛇存活={alive}"
          f"（共 {tick} 拍）—— {'通过 ✓' if ok3b else '失败 ✗'}")
    return ok3a and ok3b


def play_game():
    """真玩模式（修复版）：WASD/方向键。"""
    import msvcrt
    ram, cpu, poll = make_machine()
    settle(cpu, poll)
    last_fed = pending = "d"
    tick = 0
    render(ram, cpu, tick, last_fed=last_fed, pending=pending)
    while not cpu.halted:
        time.sleep(0.12)
        batch = []
        while msvcrt.kbhit():
            k = msvcrt.getwch()
            batch.append({"H": "w", "P": "s", "K": "a", "M": "d"}.get(k, k.lower()))
        pending, _ = sample_keys(batch, last_fed, pending)
        tick += 1
        run_tick(ram, cpu, poll, *DIRS[pending])
        last_fed = pending                    # ★ 投喂后才更新参照
        if cpu.halted:
            break                             # ★ 修复 2：不再双重渲染
        render(ram, cpu, tick, last_fed=last_fed, pending=pending)
    render(ram, cpu, tick, final=True, last_fed=last_fed, pending=pending)
    print(f"游戏结束！最终分数 {ram.read(C_S)}，蛇长 {ram.read(C_L)}，共 {tick} 拍")


if __name__ == "__main__":
    if "--play" in sys.argv:
        play_game()
    else:
        results = [act1_regression(), act2_old_guard(), act3_fix_proof()]
        print("\n总判定：" + ("三幕全部通过 ✓" if all(results) else "存在失败 ✗"))
        sys.exit(0 if all(results) else 1)
