"""基本逻辑门（AND/NAND/OR/NOR/XOR/NOT）——纯 Python 算术实现。

历史：最初用 numpy 感知机（权重·输入 + 偏置 > 阈值）实现，教学价值高
（展示"门 = 线性分类器"），但 numpy 数组创建开销约 4.4µs/次。改为纯
Python 算术后降至 ~0.2µs（约 20 倍提速），**数学完全等价**（权重、偏置、
阈值不变，只是不再造数组）。原版见 git 历史：
    git show HEAD~1:ALU/gate.py

真值表（六门全量验证于 test_alu.py 的 197 万项穷举）：
    AND: 1 仅当全 1     NAND: AND 取反
    OR:  0 仅当全 0     NOR:  OR 取反
    XOR: 不同为 1       NOT:  单目取反
"""


def AND(x1, x2):
    """感知机 AND：0.5x₁+0.5x₂−0.7 > 0 ⇔ 全 1（数学等价于原 numpy 版）。"""
    return 1 if 0.5 * x1 + 0.5 * x2 - 0.7 > 0 else 0


def NAND(x1, x2):
    """感知机 NAND：−0.5x₁−0.5x₂+0.7 > 0 ⇔ 非全 1。"""
    return 1 if -0.5 * x1 - 0.5 * x2 + 0.7 > 0 else 0


def OR(x1, x2):
    """感知机 OR：0.5x₁+0.5x₂−0.2 > 0 ⇔ 至少一个 1。"""
    return 1 if 0.5 * x1 + 0.5 * x2 - 0.2 > 0 else 0


def NOR(x1, x2):
    """感知机 NOR：−0.5x₁−0.5x₂+0.2 > 0 ⇔ 全 0。"""
    return 1 if -0.5 * x1 - 0.5 * x2 + 0.2 > 0 else 0


def XOR(x1, x2):
    """感知机组合 XOR：NAND 与 OR 的 AND（三门前馈网络）。"""
    s1 = NAND(x1, x2)
    s2 = OR(x1, x2)
    return AND(s1, s2)


def NOT(x1):
    """NOT：单目取反。"""
    return 1 if not x1 else 0
