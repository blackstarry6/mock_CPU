"""数据选择器（MUX）：门级 2 选 1 → one-hot AND-OR 阵列 → 字级多路选择。

三个粒度对应真实硬件的三个层次：
- mux2 是标准门级结构：未被选中的一路被 AND 屏蔽，OR 汇合输出
- mux_onehot 是 AND-OR 阵列，与译码器输出天然对接（译码器产 one-hot，
  MUX 消费 one-hot）——真实寄存器堆读端口就是这个结构
- mux_word 对整数表示的多个"字"做多路选择，供上层直接使用
"""
from functools import reduce

from ALU.gate import AND, NOT, OR
from .decoder import decode


def mux2(a, b, sel):
    """1 位 2 选 1：sel=0 选 a，sel=1 选 b。"""
    return OR(AND(a, NOT(sel)), AND(b, sel))


def mux_onehot(inputs, onehot):
    """1 位 n 路 one-hot 选择：AND-OR 阵列（onehot 恰有一位为 1）。"""
    return reduce(OR, [AND(d, s) for d, s in zip(inputs, onehot)])


def mux_word(words, addr, width=8):
    """从 2^n 个 width 位整数字中按地址选出一路。

    实现：译码器把 addr 变 one-hot，再逐位做 AND-OR 阵列——
    与真实寄存器堆读端口（译码 + 与或选择阵列）结构一致。
    """
    n_bits = len(words).bit_length() - 1
    sel = decode(addr, n_bits)
    result = 0
    for i in range(width):
        bit = mux_onehot([(w >> i) & 1 for w in words], sel)
        result |= bit << i
    return result
