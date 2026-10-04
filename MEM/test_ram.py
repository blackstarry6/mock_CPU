"""RAM 行为测试。

运行（项目根目录）：python -m MEM.test_ram
"""
import sys

from .ram import RAM

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def test_initial_and_load():
    ram = RAM()
    check("初始全 0", ram.read(0), 0)
    ram.load_program([0x12, 0x34, 0x56], base=0x10)
    check("烧写 0x10", ram.read(0x10), 0x12)
    check("烧写 0x11", ram.read(0x11), 0x34)
    check("烧写 0x12", ram.read(0x12), 0x56)


def test_write_tick():
    ram = RAM()
    ram.write(0x20, 0xAB)
    check("打拍前读旧", ram.read(0x20), 0)
    ram.tick()
    check("打拍后读新", ram.read(0x20), 0xAB)
    ram.tick()
    check("写请求一次性消费", ram.read(0x20), 0xAB)


def test_last_write_wins():
    """单写端口：打拍前多次登记，只有最后一次生效。"""
    ram = RAM()
    ram.write(1, 0xAA)
    ram.write(2, 0xBB)
    ram.tick()
    check("前一次请求被覆盖", ram.read(1), 0)
    check("最后一次请求生效", ram.read(2), 0xBB)


def test_mask():
    ram = RAM()                 # 256 字节
    ram.write(0x100 + 3, 0x1FF)  # 地址 → 3，值 → 0xFF
    ram.tick()
    check("地址/值截断", ram.read(3), 0xFF)
    check("高位地址回绕同一格", ram.read(0x103), 0xFF)


def main():
    for name, fn in [
        ("初始状态与烧写", test_initial_and_load),
        ("写打拍与一次性消费", test_write_tick),
        ("末次登记生效", test_last_write_wins),
        ("地址/值截断", test_mask),
    ]:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
