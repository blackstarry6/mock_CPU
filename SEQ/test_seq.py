"""SEQ 时序部件行为测试。

核心验证两件事（对照 ../知识存档.md）：
1. 记忆存在：不调用 d()，打多少拍值都不变
2. 边沿纪律：d() 之后、tick() 之前输出仍是旧值；tick 时刻才统一翻转
   （这正是同拍读写交换能成功的原因，见 test_swap_with_clock）

运行（在 SEQ 目录下）：python test_seq.py
"""
import sys

from dff import DFlipFlop, Clock
from register import Register

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def test_dff_hold():
    """不打拍就不变——"记忆"存在的直接证明。"""
    dff = DFlipFlop(init=1)
    for _ in range(5):
        dff.tick()
    check("DFF 无写入时保持", dff.q, 1)


def test_dff_edge():
    """边沿纪律：d() 后 q 不变，tick() 后才变；使能一次性消费。"""
    dff = DFlipFlop(init=0)
    dff.d(1)
    check("DFF 边沿前保持旧值", dff.q, 0)
    dff.tick()
    check("DFF 边沿后更新", dff.q, 1)
    dff.tick()
    check("DFF 使能已消费，再打拍保持", dff.q, 1)


def test_dff_last_d_wins():
    """D 是导线：打拍前多次改写，以最后一次为准。"""
    dff = DFlipFlop(init=0)
    dff.d(1)
    dff.d(0)
    dff.tick()
    check("DFF 最后一次 d 生效", dff.q, 0)


def test_register_basic():
    r = Register("R0", init=0x0F)
    check("REG 初始值", r.value, 0x0F)
    check("REG 由 8 个触发器组成", len(r.bits), 8)

    r.d(0xA5)
    check("REG 边沿前保持旧值", r.value, 0x0F)
    r.tick()
    check("REG 边沿后更新", r.value, 0xA5)

    r.tick()  # 没有再调用 d()：写使能已被上次 tick 消费
    check("REG 无写入时保持", r.value, 0xA5)


def test_register_mask():
    r = Register("R1")
    r.d(0x1FF)  # 超出 8 位
    r.tick()
    check("REG 截断到 8 位", r.value, 0xFF)


def test_swap_with_clock():
    """旗舰测试：同拍读写。交换 A/B，打拍前必须读到旧值，打拍后同时翻转。

    对照知识存档 3.4 节的反例：若边算边提交（原地更新），交换会失败。
    """
    clk = Clock()
    a = Register("A", init=0x05)
    b = Register("B", init=0x09)
    clk.attach(a, b)

    va, vb = a.value, b.value   # 组合阶段：只读旧值
    a.d(vb)
    b.d(va)

    check("交换·打拍前 A 仍旧值", a.value, 0x05)
    check("交换·打拍前 B 仍旧值", b.value, 0x09)
    clk.tick()
    check("交换·打拍后 A", a.value, 0x09)
    check("交换·打拍后 B", b.value, 0x05)
    check("时钟计数", clk.cycles, 1)


def test_clock_multi():
    """连续打拍：每拍"读旧值 → 算新值 → 提交"，3 拍自增 3 次。"""
    clk = Clock()
    r = Register("R", init=1)
    clk.attach(r)
    for _ in range(3):
        r.d(r.value + 1)
        clk.tick()
    check("连续打拍 3 次自增", r.value, 4)
    check("时钟计数", clk.cycles, 3)


def main():
    tests = [
        ("DFF 保持", test_dff_hold),
        ("DFF 边沿纪律", test_dff_edge),
        ("DFF 末次 D 生效", test_dff_last_d_wins),
        ("寄存器基本行为", test_register_basic),
        ("寄存器位宽截断", test_register_mask),
        ("同拍交换（时钟统一提交）", test_swap_with_clock),
        ("连续打拍", test_clock_multi),
    ]
    for name, fn in tests:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
