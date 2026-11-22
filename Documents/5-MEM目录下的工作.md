[TOC]

# 概述

**MEM/ram.py**

- 256 字节，字节数组；`read(addr)` 组合读、`write(addr, value)` 暂存写请求、`tick()` 提交——**同步写 RAM**，和统一时钟纪律对齐（真实片上 RAM 也多为同步写）
- 附一个 `load_program(bytes, base=0)`：初始化时批量装载，相当于烧写 ROM，绕过时钟（一次性、仅限初始化）
- 地址自动截断到 8 位





# MEM下的工作

## ram.py

256 字节同步 RAM：读组合、写打拍。

与 SEQ 的时序纪律一致：
- read() 是导线直通，随时可读，读到当前存储值（写打拍前为旧值）
- write() 只是登记写请求，tick() 时钟沿统一提交（一次性消费，
  多次登记以最后一次为准——单写端口的导线语义）。真实 CPU 的片上 RAM 也多为同步写，与该模型吻合。

load_program() 用于初始化批量装载（相当于烧写 ROM）：直接写入存储阵列，不经时钟，仅限初始化时使用。

```python
class RAM:
    def __init__(self, size=256, width=8):
        assert size & (size - 1) == 0, "容量必须是 2 的幂"
        self.size = size
        self.addr_mask = size - 1
        self.value_mask = (1 << width) - 1
        self.data = [0] * size
        self._we = 0
        self._addr = 0
        self._value = 0
 
    def read(self, addr):
        """读端口（组合）：按地址读一个字节，地址自动截断。"""
        return self.data[addr & self.addr_mask]
 
    def write(self, addr, value):
        """写端口（登记）：请求在下一个时钟沿写入。"""
        self._addr = addr & self.addr_mask
        self._value = value & self.value_mask
        self._we = 1
 
    def tick(self):
        """时钟沿：提交登记的写请求。"""
        if self._we:
            self.data[self._addr] = self._value
            self._we = 0
 
    def load_program(self, program, base=0):
        """烧写：把字节序列写入以 base 起始的单元，直接生效。"""
        for i, byte in enumerate(program):
            self.data[(base + i) & self.addr_mask] = byte & self.value_mask
```

## 忠实度盘点：RAM 算实现了吗？

先看三条路径各自的忠实度——它们其实并不相同：

- `read()` 是组合直查（`data[addr & mask]`）；
- `write()` **不是** `data[addr] = v`——它把地址、数据、写使能登记进三个内部寄存器（`_addr/_value/_we`），等 `tick()` 时钟沿才提交，且单写端口语义下多次登记以末次为准；
- `load_program()` 是烧写，文档明标"不经时钟、仅限初始化"。

①+② 的组合恰好对应一个真实的芯片品类：**异步读、同步写的 SRAM**。行为级糊弄的是内部，严守的是契约——这个 RAM 对 CPU 可观察的一切行为，逐条有测试作保。于是"算实现了吗"要分三层回答：

| 判定层 | 结论 | 依据 |
| --- | --- | --- |
| 契约层 | **算实现** | 读组合（写打拍前读旧值）、写在时钟沿提交、写使能一次性消费、末次登记生效、地址/值截断与高位回绕——逐条对应 test_ram.py 的断言 |
| 结构层 | **不算实现** | 256×8 = 2048 个存储单元、行译码器（word line）、列选择阵列（及真实芯片的敏感放大器）全部委托给 Python 列表——`data[addr]` 这一步就是被抽象掉的整个存储机制 |
| 知识层 | **没丢** | 寄存器堆 read 端口的 decode + AND-OR 阵列，就是 RAM 内部"行译码 + 列选择"的 8×8 微缩版——门级存储器在本机其实实现了，叫寄存器堆；知识在 COMB/SEQ 里教，本体在 MEM/ 里用 |

为什么这样取舍？目标函数自始至终是**教学价值/可读性**，三条判据：

1. **结构还看得清吗**——8 格的寄存器堆每根 one-hot 线都能指着讲；2048 格的门级 RAM 是一面没人能读的墙；
2. **还有新知识吗**——把 8×8 放大 32 倍到 256×8，学不到任何新东西：**规模不是洞见**，第 2048 个 DFF 说不出前 8 个没说过的话；
3. **契约保住了吗**——无论哪级忠实，"读旧值 → 声明 → tick 提交"的时序纪律寸步不让。

工业界早已按同一标准投票：芯片厂商给客户发布的仿真模型（Verilog/VHDL 行为级模型）就是这个忠实度——总线契约精确、内部一行门都没有。RTL 层"实现"一词的本义，就是接口行为正确。

结论收拢成一句话：按"造出存储**机制**"的标准，**不算**（机制委托给了列表）；按"实现存储**器这个部件**"的标准（它在总线上的契约、它对时序的服从），**算**——11 项断言作保。部件与机制，一个词之差，问的是两个问题。

