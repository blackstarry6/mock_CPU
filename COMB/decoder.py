"""n 位地址译码器：地址 → 2^n 选一（one-hot），带使能端 EN。

门级实现：每个输出 = EN 与各地址位（或其取反）组成的最小项相与——
即真实译码器芯片（如 74LS138/139）内部的与门阵列。
"""
from functools import reduce

from ALU.gate import AND, NOT


def decode(addr, n_bits, en=1):
    """n_bits 位地址译成 2^n 个 one-hot 输出，en=0 时全部为 0。

    输出列表第 i 项为 1 当且仅当 addr == i（按位宽截断）且 en == 1。
    """
    addr_bits = [(addr >> i) & 1 for i in range(n_bits)]
    outputs = []
    for i in range(1 << n_bits):
        terms = [addr_bits[j] if (i >> j) & 1 else NOT(addr_bits[j])
                 for j in range(n_bits)]
        outputs.append(reduce(AND, [en] + terms))
    return outputs
