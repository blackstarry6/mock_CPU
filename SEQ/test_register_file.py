"""寄存器堆行为测试。

运行（项目根目录）：python -m SEQ.test_register_file
"""
import sys

from .register_file import RegisterFile

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def test_write_walk():
    """8 个地址逐一声明写入、一次打拍：写译码只命中各自目标。"""
    rf = RegisterFile()
    for i in range(8):
        rf.write(i, i * 33 + 5)
    rf.tick()
    for i in range(8):
        check(f"walk R{i}", rf.read(i), (i * 33 + 5) & 0xFF)


def test_only_addressed():
    """写 R3 时其余 7 个寄存器必须纹丝不动。"""
    rf = RegisterFile()
    for i in range(8):
        rf.write(i, 0x10 + i)
    rf.tick()
    rf.write(3, 0xAA)
    rf.tick()
    check("被寻址 R3 更新", rf.read(3), 0xAA)
    for i in range(8):
        if i != 3:
            check(f"R{i} 保持不变", rf.read(i), 0x10 + i)


def test_same_cycle_read_old():
    """同拍读旧写新：write 声明后 read 仍返回旧值，打拍后才变。"""
    rf = RegisterFile()
    rf.write(5, 0x77)
    rf.tick()
    rf.write(5, 0x99)
    check("同拍读旧", rf.read(5), 0x77)
    rf.tick()
    check("打拍后读新", rf.read(5), 0x99)


def test_read_is_combinational():
    """读端口无副作用：重复读、交错读不改变结果。"""
    rf = RegisterFile()
    rf.write(0, 0x11)
    rf.write(7, 0x22)
    rf.tick()
    check("读 R0", rf.read(0), 0x11)
    check("读 R7", rf.read(7), 0x22)
    check("再读 R0 仍不变", rf.read(0), 0x11)


def test_mask():
    """地址截断（11&7=3）与值截断（0x1FF→0xFF）。"""
    rf = RegisterFile()
    rf.write(11, 0x1FF)
    rf.tick()
    check("写入落在 R3（地址截断）", rf.read(3), 0xFF)
    check("其余寄存器为 0", rf.read(0), 0)


def main():
    for name, fn in [
        ("逐地址写入读取", test_write_walk),
        ("译码只命中目标", test_only_addressed),
        ("同拍读旧写新", test_same_cycle_read_old),
        ("读端口无副作用", test_read_is_combinational),
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
