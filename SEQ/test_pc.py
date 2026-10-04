"""程序计数器行为测试。

运行（项目根目录）：python -m SEQ.test_pc
"""
import sys

from .pc import ProgramCounter

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def test_incr_sequence():
    pc = ProgramCounter(init=0)
    for i in range(4):
        check(f"PC 第 {i} 拍", pc.value, i)
        pc.incr()
        pc.tick()


def test_same_cycle():
    pc = ProgramCounter(init=0x10)
    pc.incr()
    check("打拍前读旧值", pc.value, 0x10)
    pc.tick()
    check("打拍后自增", pc.value, 0x11)
    pc.tick()
    check("无声明则保持", pc.value, 0x11)


def test_wraparound():
    pc = ProgramCounter(init=0xFF)
    pc.incr()
    pc.tick()
    check("255 自增回绕到 0", pc.value, 0x00)


def test_jump():
    pc = ProgramCounter(init=0x20)
    pc.incr()
    pc.load(0x7C)
    pc.tick()
    check("load 覆盖 incr", pc.value, 0x7C)


def main():
    for name, fn in [
        ("顺序自增", test_incr_sequence),
        ("同拍读旧", test_same_cycle),
        ("255 回绕", test_wraparound),
        ("跳转装载", test_jump),
    ]:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
