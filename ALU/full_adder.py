"""8 位行波进位加减法器（基于 gate.py 的门电路自底向上搭建）。

结构：半加器 → 一位全加器 → 行波进位链。
减法通过补码实现：A - B = A + ~B + 1。
"""
from .gate import AND, OR, XOR, NOT


def semi_adder_one(x1, x2):
    s = XOR(x1, x2)
    co = AND(x1, x2)
    return s, co


def full_adder_one(x1, x2, x3):
    s1, co1 = semi_adder_one(x1, x2)
    s2, co2 = semi_adder_one(x3, s1)
    s = s2
    co = OR(co2, co1)
    return s, co


def to_bits(value, n=8):
    """整数 → 低位在前的位列表。超出 n 位的高位丢弃（对齐硬件位宽）。"""
    return [(value >> i) & 1 for i in range(n)]


def from_bits(bits):
    """低位在前的位列表 → 整数。"""
    value = 0
    for i, b in enumerate(bits):
        value |= b << i
    return value


def ripple_add(a_bits, b_bits, ci=0):
    """行波进位加法链，位列表均低位在前。

    返回 (和的位列表, 各级进位输出列表, 最高位进位 C)。
    carries[i] 是第 i 位的进位输出；计算溢出标志 V 需要 carries[-2]
    （即进入最高位 bit7 的进位，与最高位进位 C 异或即得 V）。
    """
    sum_bits, carries = [], []
    for x, y in zip(a_bits, b_bits):
        s, ci = full_adder_one(x, y, ci)
        sum_bits.append(s)
        carries.append(ci)
    return sum_bits, carries, ci


def add8(a, b, cin=0):
    """8 位加法：a + b + cin → (和, 进位 C, 进入 bit7 的进位 c6)。"""
    sum_bits, carries, co = ripple_add(to_bits(a), to_bits(b), cin)
    return from_bits(sum_bits), co, carries[-2]


def sub8(a, b):
    """8 位减法：a - b = a + ~b + 1 → (差, C, c6)。

    C 为"借位取反"惯例：C=1 表示够减（无借位），C=0 表示发生了借位。
    """
    b_not = [NOT(x) for x in to_bits(b)]
    sum_bits, carries, co = ripple_add(to_bits(a), b_not, 1)
    return from_bits(sum_bits), co, carries[-2]


def full_adder(num, CI, A, B):
    """旧接口保留：num 位 A + B + CI → (结果, 最高位进位)。

    注意：旧版只打印不返回，且 CI=1 并不能实现减法（没有对 B 取反），
    减法请用 sub8。
    """
    sum_bits, _, co = ripple_add(to_bits(A, num), to_bits(B, num), CI)
    return from_bits(sum_bits), co


if __name__ == "__main__":
    for a, b in [(100, 55), (200, 100), (255, 1)]:
        s, c, _ = add8(a, b)
        print(f"ADD {a:3d} + {b:3d} = {s:3d}  C={c}")
    for a, b in [(100, 55), (55, 100), (0, 1)]:
        s, c, _ = sub8(a, b)
        print(f"SUB {a:3d} - {b:3d} = {s:3d}  C={c} (1=无借位)")
