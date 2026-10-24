"""8 位 ALU：算术、逻辑、移位、乘法运算与标志位。

全部运算基于 gate.py 的门电路与 full_adder.py 的加法器实现。
进位输入（cin）：加减法器天生带 cin 端口，控制器选择接 0（ADD）、
接 1（SUB 补码的 +1）还是接 C 标志（ADC/SBB）——带进位指令不是
新电路，是同一加减法器换一个进位来源。

标志位定义（对齐主流 8 位 CPU 惯例）：
  Z — 结果为 0（用 NOR 门对全部位或之后取反得到）
  N — 结果最高位 bit7 为 1
  C — 加法进位；减法"借位取反"（C=1 表示无借位）；移位时为移出的那一位；
      MUL 时表示积超出 8 位（高字节非 0）
  V — 有符号溢出，仅加减法有意义（含 ADC/SBB），其余恒为 0
"""
from functools import reduce

from .gate import AND, OR, XOR, NOT
from .full_adder import add8, sub8, to_bits, from_bits, ripple_add

WORD = 8
MASK = 0xFF


def _zero_flag(bits):
    """Z = NOR(b0..bn)：所有位 OR 起来再取反。"""
    return NOT(reduce(OR, bits))


def _mkflags(bits, c=0, v=0):
    """由结果的位列表生成完整标志位。bits 低位在前、恰好 8 位。"""
    return {"Z": _zero_flag(bits), "N": bits[-1], "C": c, "V": v}


# ---------- 算术 ----------

def alu_add(a, b, cin=0):
    """ADD 与 ADC 共用同一加法器：cin=0 是 ADD，cin=C 标志是 ADC。"""
    s, c, c6 = add8(a, b, cin)
    return s, _mkflags(to_bits(s), c, XOR(c6, c))


def alu_sub(a, b, cin=1):
    """SUB 与 SBB 共用同一减法器：cin=1 是 SUB（补码的 +1），cin=C 是 SBB。"""
    s, c, c6 = sub8(a, b, cin)
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


def alu(op, a, b=0, cin=None):
    """执行运算，返回 (结果, 标志位字典)。MUL 结果 16 位，其余 8 位。

    输入自动截断到 8 位（对齐硬件：超出位宽的输入被忽略）。
    cin 是进位输入端口：数据通路上只有加减法器有这根线（逻辑/移位/
    乘法没有进位输入），控制器用它区分 ADD/ADC、SUB/SBB。不传 cin
    则用运算自己的默认（ADD=0 / SUB=1，即普通加减法的历史语义）。
    """
    if op in ("ADD", "SUB"):
        if cin is None:
            return OPS[op](a & MASK, b & MASK)
        return OPS[op](a & MASK, b & MASK, cin)
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
    # ADC/SBB 演示（cin 接 C 标志）：16 位 0x00FF+1 与 0x0000−1 的第二字节
    for op, a, b, cin in [("ADD", 0, 0, 1), ("SUB", 0, 0, 0)]:
        r, f = alu(op, a, b, cin=cin)
        fs = "".join(k for k in "ZNCV" if f[k])
        print(f"{op:>3} {a:>3}, {b:>3}, cin={cin} = {r:3d}  标志: {fs or '—'}")
