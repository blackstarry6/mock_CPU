[TOC]

# 概述

**COMB/mux.py + COMB/decoder.py**

- 2 选 1 MUX 用纯门搭：`mux2 = OR(AND(NOT(sel), a), AND(sel, b))`——sel=0 选 a、sel=1 选 b，教科书结构
- n 选 1 用 **AND-OR 阵列**实现：每个输入和自己的 one-hot 选择线相与，再全部或起来——这正好和译码器的输出对接（译码器产 one-hot，MUX 消费 one-hot），也是真实器件里的标准结构
- 译码器：地址位（及其取反）按最小项 AND 出 one-hot，带使能端 EN（EN=0 时全 0——这个使能端就是寄存器堆写端口的 WE）





# COMB下的工作

## 包结构改造

目录下新增`__init__.py`。

COMB：通用组合逻辑部件包（MUX、译码器）。





## decoder.py

n 位地址译码器：地址 → 2^n 选一（one-hot），带使能端 EN。

门级实现：每个输出 = EN 与各地址位（或其取反）组成的最小项相与——即真实译码器芯片（如 74LS138/139）内部的与门阵列。

```python
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
```







## mux.py

数据选择器（MUX）：门级 2 选 1 → one-hot AND-OR 阵列 → 字级多路选择。

三个粒度对应真实硬件的三个层次：
- mux2 是标准门级结构：未被选中的一路被 AND 屏蔽，OR 汇合输出
- mux_onehot 是 AND-OR 阵列，与译码器输出天然对接（译码器产 one-hot，MUX 消费 one-hot）——真实寄存器堆读端口就是这个结构
- mux_word 对整数表示的多个"字"做多路选择，供上层直接使用

> **One-hot 编码（独热编码）** 使用一个二进制向量来表示一个类别，向量中只有一个元素是 `1`，其余所有元素都是 `0`。
>
> `reduce(函数, 序列)` 的作用是**折叠**：反复把函数作用于“当前累积值”和“下一个元素”，直到把整个序列缩成一个值：
>
> ```python
> from functools import reduce
> 
> reduce(OR, [b0, b1, b2, ..., b7])
> # 展开就是：OR(OR(OR(OR(b0, b1), b2), b3), ..., b7)
> ```
>
> 具体例子：`reduce(OR, [1,0,0,0,0,0,0,0])` → 先 `OR(1,0)=1`，再 `OR(1,0)=1`……最终 1。

```python
def mux2(a, b, sel):
    """1 位 2 选 1：sel=0 选 a，sel=1 选 b。"""
    return OR(AND(a, NOT(sel)), AND(b, sel))
 
 
def mux_onehot(inputs, onehot):
    """1 位 n 路 one-hot 选择：AND-OR 阵列（onehot 恰有一位为 1）。"""
    return reduce(OR, [AND(d, s) for d, s in zip(inputs, onehot)])
 
 
def mux_word(words, addr, width=8):
    """
    从 2^n 个 width 位整数字中按地址选出一路。
    实现：译码器把 addr 变 one-hot，再逐位做 AND-OR 阵列——与真实寄存器堆读端口（译码 + 与或选择阵列）结构一致。
    """
    n_bits = len(words).bit_length() - 1
    sel = decode(addr, n_bits)
    result = 0
    for i in range(width):
        bit = mux_onehot([(w >> i) & 1 for w in words], sel)
        result |= bit << i
    return result
```





## test_comb.py

