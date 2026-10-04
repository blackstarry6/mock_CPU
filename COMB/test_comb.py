"""COMB 组合部件测试：mux2 / one-hot 阵列 / 译码器 / 字级 MUX。

运行（项目根目录）：python -m COMB.test_comb
"""
import sys

from .mux import mux2, mux_onehot, mux_word
from .decoder import decode

TOTAL = 0
FAILS = 0


def check(name, got, want):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        print(f"FAIL [{name}] got {got}, want {want}")


def test_mux2():
    for a in (0, 1):
        for b in (0, 1):
            for sel in (0, 1):
                want = a if sel == 0 else b
                check(f"mux2({a},{b},sel={sel})", mux2(a, b, sel), want)


def test_mux_onehot():
    data = [1, 0, 1, 1, 0, 0, 1, 0]
    for i, bit in enumerate(data):
        onehot = [1 if j == i else 0 for j in range(8)]
        check(f"one-hot 选第 {i} 路", mux_onehot(data, onehot), bit)


def test_decoder():
    for n_bits, size in [(2, 4), (3, 8)]:
        for addr in range(size):
            out = decode(addr, n_bits)
            for i in range(size):
                check(f"{n_bits} 位译码 addr={addr} out[{i}]",
                      out[i], 1 if i == addr else 0)
    for addr in range(4):
        check(f"en=0 全灭 addr={addr}", sum(decode(addr, 2, en=0)), 0)


def test_mux_word():
    words = [0x00, 0x5A, 0xFF, 0x0F, 0xA3, 0x81, 0x7C, 0x3D]
    for addr in range(8):
        check(f"字选择 addr={addr}", mux_word(words, addr), words[addr])
    check("地址按位宽截断", mux_word(words, 8 + 5), words[5])


def main():
    for name, fn in [
        ("mux2 全真值表", test_mux2),
        ("one-hot AND-OR 阵列", test_mux_onehot),
        ("译码器 2-4 / 3-8 / 使能", test_decoder),
        ("字级 MUX", test_mux_word),
    ]:
        fn()
        print(f"  {name} 完成")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
