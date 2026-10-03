"""8 位 ALU：算术、逻辑、移位、乘法运算与标志位。

全部运算基于 gate.py 的门电路与 full_adder.py 的加法器实现。

标志位定义（对齐主流 8 位 CPU 惯例）：
  Z — 结果为 0（用 NOR 门对全部位或之后取反得到）
  N — 结果最高位 bit7 为 1
  C — 加法进位；减法"借位取反"（C=1 表示无借位）；移位时为移出的那一位；
      MUL 时表示积超出 8 位（高字节非 0）
  V — 有符号溢出，仅 ADD/SUB 有意义，其余恒为 0
"""
from functools import reduce

from gate import AND, OR, XOR, NOT
from full_adder import add8, sub8, to_bits, from_bits, ripple_add

WORD = 8
MASK = 0xFF


def _zero_flag(bits):
    """Z = NOR(b0..bn)：所有位 OR 起来再取反。"""
    return NOT(reduce(OR, bits))


def _mkflags(bits, c=0, v=0):
    """由结果的位列表生成完整标志位。bits 低位在前、恰好 8 位。"""
    return {"Z": _zero_flag(bits), "N": bits[-1], "C": c, "V": v}


# ---------- 算术 ----------

def alu_add(a, b):
    s, c, c6 = add8(a, b)
    return s, _mkflags(to_bits(s), c, XOR(c6, c))


def alu_sub(a, b):
    s, c, c6 = sub8(a, b)
    return s, _mkflags(to_bits(s), c, XOR(c6, c))


def alu_mul(a, b):
    """8x8 → 16 位无符号乘法（移位相加）。

    逐位检查 B（用 AND 门做部分积选择），为 1 则把左移 i 位后的 A
    用 16 位行波进位加法器累加。
    """
    b_bits = to_bits(b)
    acc_bits = [0] * 16
    for i in range(WORD):
        if AND(b_bits[i], 1):
            shifted = to_bits(a << i, 16)
            acc_bits, _, _ = ripple_add(acc_bits, shifted)
    result = from_bits(acc_bits)
    flags = {
        "Z": _zero_flag(acc_bits),
        "N": acc_bits[7],                    # N 取低字节最高位
        "C": reduce(OR, acc_bits[8:]),       # C = 高字节非 0
        "V": 0,
    }
    return result, flags


# ---------- 逻辑 ----------

def _bitwise(a, b, gate):
    bits = [gate(x, y) for x, y in zip(to_bits(a), to_bits(b))]
    return from_bits(bits), _mkflags(bits)


def alu_and(a, b):
    return _bitwise(a, b, AND)


def alu_or(a, b):
    return _bitwise(a, b, OR)


def alu_xor(a, b):
    return _bitwise(a, b, XOR)


def alu_not(a, b=0):
    bits = [NOT(x) for x in to_bits(a)]
    return from_bits(bits), _mkflags(bits)


# ---------- 移位 / 循环移位 ----------

def alu_shl(a, b=0):
    bits = to_bits(a)
    out = [0] + bits[:-1]        # 低位补 0，bit7 移出进 C
    return from_bits(out), _mkflags(out, c=bits[-1])


def alu_shr(a, b=0):
    bits = to_bits(a)
    out = bits[1:] + [0]         # 逻辑右移，高位补 0，bit0 移出进 C
    return from_bits(out), _mkflags(out, c=bits[0])


def alu_rol(a, b=0):
    bits = to_bits(a)
    out = [bits[-1]] + bits[:-1]  # bit7 绕回 bit0
    return from_bits(out), _mkflags(out, c=bits[-1])


def alu_ror(a, b=0):
    bits = to_bits(a)
    out = bits[1:] + [bits[0]]    # bit0 绕回 bit7
    return from_bits(out), _mkflags(out, c=bits[0])


# ---------- 分发 ----------

OPS = {
    "ADD": alu_add,
    "SUB": alu_sub,
    "MUL": alu_mul,
    "AND": alu_and,
    "OR": alu_or,
    "XOR": alu_xor,
    "NOT": alu_not,
    "SHL": alu_shl,
    "SHR": alu_shr,
    "ROL": alu_rol,
    "ROR": alu_ror,
}


def alu(op, a, b=0):
    """执行运算，返回 (结果, 标志位字典)。MUL 结果 16 位，其余 8 位。

    输入自动截断到 8 位（对齐硬件：超出位宽的输入被忽略）。
    """
    return OPS[op](a & MASK, b & MASK)


if __name__ == "__main__":
    demo = [
        ("ADD", 100, 55), ("SUB", 55, 100), ("SUB", 100, 55),
        ("AND", 0b11001100, 0b10101010), ("XOR", 0b11001100, 0b10101010),
        ("SHL", 0b10000001, 0), ("ROL", 0b10000001, 0), ("SHR", 0b00000011, 0),
        ("MUL", 200, 100), ("MUL", 16, 16),
    ]
    for op, a, b in demo:
        r, f = alu(op, a, b)
        fs = "".join(k for k in "ZNCV" if f[k])
        width = 16 if op == "MUL" else 8
        print(f"{op:>3} {a:>3}, {b:>3} = {r:>{width//4 + 1}} (0b{r:0{width}b})  标志: {fs or '—'}")
