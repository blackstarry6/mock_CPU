"""ALU 穷举测试：全部 256x256 输入与 Python 原生运算逐项对照。

运行（项目根目录）：python -m ALU.test_alu
MUL 为 16 位门级仿真、较慢，整轮约 5 分钟属正常。
"""
import sys
import time

from .alu import alu

TOTAL = 0
FAILS = 0


def check(name, got, want, detail):
    global TOTAL, FAILS
    TOTAL += 1
    if got != want:
        FAILS += 1
        if FAILS <= 20:
            print(f"FAIL [{name}] {detail}: got {got}, want {want}")


def test_add_sub():
    for a in range(256):
        for b in range(256):
            exact = a + b
            r, f = alu("ADD", a, b)
            d = f"ADD {a},{b}"
            check("ADD", r, exact & 0xFF, d)
            check("ADD.Z", f["Z"], int(r == 0), d)
            check("ADD.N", f["N"], (r >> 7) & 1, d)
            check("ADD.C", f["C"], exact >> 8, d)
            check("ADD.V", f["V"], int(((a ^ r) & (b ^ r) & 0x80) != 0), d)

            exact = a - b
            r, f = alu("SUB", a, b)
            d = f"SUB {a},{b}"
            check("SUB", r, exact & 0xFF, d)
            check("SUB.Z", f["Z"], int(r == 0), d)
            check("SUB.N", f["N"], (r >> 7) & 1, d)
            check("SUB.C", f["C"], int(a >= b), d)
            check("SUB.V", f["V"], int(((a ^ b) & (a ^ r) & 0x80) != 0), d)


def test_logic():
    for a in range(256):
        for b in range(256):
            for op, want in [("AND", a & b), ("OR", a | b), ("XOR", a ^ b)]:
                r, f = alu(op, a, b)
                d = f"{op} {a},{b}"
                check(op, r, want, d)
                check(op + ".Z", f["Z"], int(r == 0), d)
                check(op + ".N", f["N"], (r >> 7) & 1, d)
                check(op + ".C", f["C"], 0, d)
                check(op + ".V", f["V"], 0, d)


def test_not():
    for a in range(256):
        r, f = alu("NOT", a, 0)
        d = f"NOT {a}"
        check("NOT", r, (~a) & 0xFF, d)
        check("NOT.Z", f["Z"], int(r == 0), d)
        check("NOT.N", f["N"], (r >> 7) & 1, d)


def test_shift():
    for a in range(256):
        cases = [
            ("SHL", ((a << 1) & 0xFF, (a >> 7) & 1)),
            ("SHR", (a >> 1, a & 1)),
            ("ROL", ((a << 1 | a >> 7) & 0xFF, (a >> 7) & 1)),
            ("ROR", ((a >> 1 | a << 7) & 0xFF, a & 1)),
        ]
        for op, (want, carry) in cases:
            r, f = alu(op, a, 0)
            d = f"{op} {a}"
            check(op, r, want, d)
            check(op + ".Z", f["Z"], int(r == 0), d)
            check(op + ".N", f["N"], (r >> 7) & 1, d)
            check(op + ".C", f["C"], carry, d)


def test_mul():
    for a in range(256):
        for b in range(256):
            want = a * b
            r, f = alu("MUL", a, b)
            d = f"MUL {a},{b}"
            check("MUL", r, want, d)
            check("MUL.Z", f["Z"], int(r == 0), d)
            check("MUL.N", f["N"], (r >> 7) & 1, d)
            check("MUL.C", f["C"], int(want > 0xFF), d)
            check("MUL.V", f["V"], 0, d)


def main():
    tests = [
        ("ADD/SUB", test_add_sub),
        ("AND/OR/XOR", test_logic),
        ("NOT", test_not),
        ("SHL/SHR/ROL/ROR", test_shift),
        ("MUL", test_mul),
    ]
    for name, fn in tests:
        t = time.perf_counter()
        fn()
        print(f"  {name:<14} 完成，累计 {TOTAL} 项断言 "
              f"({time.perf_counter() - t:.1f}s)")
    if FAILS:
        print(f"\n共 {TOTAL} 项断言，{FAILS} 项失败 ✗")
        sys.exit(1)
    print(f"\n共 {TOTAL} 项断言，全部通过 ✓")


if __name__ == "__main__":
    main()
