[TOC]

# 概述

```
mock_CPU/
├── ALU/          # 组合算术部件（已完成）
│   ├── gate.py / full_adder.py / alu.py / test_alu.py
├── SEQ/          # 时序部件：阶段一建这个
│   ├── dff.py          # DFlipFlop：current/next + tick
│   ├── register.py     # 8 位寄存器，同拍读写纪律
│   ├── test_seq.py     # "两次 tick 之间保持、tick 时刻更新"的行为测试
│   └── (阶段二再添 register_file.py、pc.py等)
├── MEM/          # 阶段二：内存
├── CPU/          # 阶段三四：指令集与整机集成
└── README.md / 知识存档.md / .gitignore
```

**阶段一的 SEQ/ 不需要 import ALU/ 里的任何东西**——这是刻意的好消息。DFlipFlop 是行为级建模（显式状态变量 + tick），它不依赖任何门电路，天然是独立模块。

第一次跨文件夹引用要等到阶段三/四的 `CPU/` 集成（CPU 同时需要 ALU 和 SEQ），到那时再把导入方式改成从项目根目录运行的包风格（比如 `from ALU.alu import alu`）。



# SEQ下的工作

## dff.py【阶段一】

```
            CLK ──────┬─────────────┬──────  （时钟线同时喂两级，
                      │             │          但相位相反）
  D ═══════▶ ┌──────────────┐   ┌──────────────┐ ═══════▶ Q
  （输入侧）  │   主锁存器    │──▶│   从锁存器    │  （输出侧）
   "左边"     │ CLK=0 期间透明 │   │ CLK=1 期间透明 │   "右边"
             └──────────────┘   └──────────────┘
```

时序元件的最底层：D 触发器与时钟（行为级建模）。

- 显式状态变量：q 是"当前状态"（对应导线上的电压），_next 是组合逻辑
  算出的下一状态。q 是整个模块里唯一的"记忆"。
- 边沿触发：d() 只是声明"下一个时钟沿写入此值"，q 在 tick() 之前绝不变。
- 写使能一次性消费：d() 置位使能，tick() 消费后清零——之后即使继续打拍也保持，直到再次调用 d()。

```python
class DFlipFlop:
    """一位 D 触发器（上边沿触发），q 恒为 0/1。"""
 
    def __init__(self, init=0):
        self.q = init & 1       # 当前状态（"记忆"本体）
        self._next = self.q     # 时钟沿将采样的 D 输入
        self._en = 0            # 写使能：d() 置位，tick() 消费
 
    def d(self, value):
        """数据输入：声明下一个时钟沿写入 value（D 是导线，后调覆盖先调）。"""
        self._next = 1 if value else 0
        self._en = 1
 
    def tick(self):
        """时钟上边沿：使能时采样 D，否则保持原值。"""
        if self._en:
            self.q = self._next
            self._en = 0
 
 
class Clock:
    """时钟：驱动一批时序元件统一 tick，落实"算完再统一提交"。
 
    各元件在组合阶段各自调 d() 搭好下一状态，Clock.tick() 到来时
    全体同时翻转——模拟同一根时钟线连到所有触发器的 CLK 引脚。
    """
 
    def __init__(self):
        self.elements = []
        self.cycles = 0
 
    def attach(self, *elements):
        """把时序元件挂到时钟线上。"""
        self.elements.extend(elements)
        return self
 
    def tick(self, n=1):
        """打 n 拍。"""
        for _ in range(n):
            for e in self.elements:
                e.tick()
            self.cycles += 1
 
```

- `DFlipFlop`：`q` 是唯一的"记忆"（对应导线电压），`d(value)` 只是声明"下个时钟沿写入此值"，`tick()` 才采样。一个刻意的语义决策：**写使能一次性消费**——`d()` 置位使能、`tick()` 用掉后自动清零，之后哪怕继续打拍也保持。这对应真实时序电路"控制信号每拍由译码器重新生成"的用法，能防住"忘了撤销 WE 导致寄存器被反复重写"这类隐患。
- `Clock`：把一批时序元件挂到同一根"时钟线"上，`tick()` 让全体同时翻转——这就是"算完再统一提交"的全局版。

| 变量  | 硬件对应                   | 角色                               |
| ----- | -------------------------- | ---------------------------------- |
| q     | 触发器 Q 引脚上当前的电压  | 唯一的记忆——整个类只有它跨时间存活 |
| _next | D 输入导线上“现在摆着的值” | 等待边沿采样的候选值               |
| _en   | 写使能 WE                  | 声明“这个值要不要被写入”           |





## register.py【阶段一】

"8 位寄存器：由 8 个 D 触发器共享时钟组成（结构级组合）。

- 真实寄存器就是"一排 D 触发器 + 共用时钟线"，因此这里不自建状态变量，而是直接组合 DFlipFlop——沿用本项目"下层部件搭上层部件"的原则。


- 写使能语义：调用 d() 即声明本拍写入，不调用即保持（对应真实寄存器堆的 WE 控制信号：译码器每拍决定哪个寄存器的 WE 为 1）。

```python
from dff import DFlipFlop
 
 
class Register:
    """width 位寄存器，低位在前的 DFlipFlop 列表。"""
 
    def __init__(self, name="REG", width=8, init=0):
        self.name = name
        self.width = width
        
         self.bits = [DFlipFlop(init=(init >> i) & 1) for i in range(width)]
        #mask = (1 << width) - 1
        #self.bits = [DFlipFlop(init=(init & mask) >> i & 1) for i in range(width)]
 
    @property
    def value(self):
        """当前输出：各触发器 q 的组装。打拍前永远读到旧值。"""
        return sum(b.q << i for i, b in enumerate(self.bits))
 
    def d(self, value):
        """数据输入：声明下一个时钟沿写入 value（自动截断到位宽）。"""
        for i, b in enumerate(self.bits):
            b.d((value >> i) & 1)
 
    def tick(self):
        """时钟上边沿：8 个触发器同时采样。"""
        for b in self.bits:
            b.tick()
 
```

> 后注：代码块里的 `from dff import DFlipFlop` 是**包结构改造前的旧式导入**（当时把包目录加进 sys.path 直接 import，SEQ 站确实是这么写的）。后来 Stage 2 做了包结构改造：全部改为相对导入 `from .dff import DFlipFlop`，并统一在项目根目录用 `python -m SEQ.xxx` 运行——本节描述的是 SEQ 站当时的实现。

刻意**不自建任何状态变量**：寄存器就是 8 个 `DFlipFlop` 共享时钟的组合，`value` 属性实时从各触发器的 `q` 组装出来，`d()` 截断到位宽后逐位下发。沿用项目"下层部件搭上层部件"的原则，和当年"半加器搭全加器"是同一个思路。

> `@property` 是 Python 的一个**装饰器**，作用是把一个方法变成“**看起来像属性的成员**”——外部访问时不用加括号，但它背后其实是在执行函数。
>
> 在本份代码中，`@property` 的本质是：**读写接口伪装成字段，实现却是一段即时计算的代码**——所谓“计算属性”。





## test_seq.py【阶段一建立，后续持续更新】

**SEQ/test_seq.py** —— 7 组测试验证两条核心纪律：

| 纪律             | 测试                                                         |
| ---------------- | ------------------------------------------------------------ |
| 记忆存在         | 不调 d() 连打 5 拍，值不变                                   |
| 边沿纪律         | d() 之后 q/value 仍读旧值，tick() 后才翻转；末次 d() 覆盖先前的 |
| 一次性使能       | 写入后的第二拍保持                                           |
| 同拍读写（旗舰） | 用 Clock 交换 A、B 两个寄存器：组合阶段读到的必须是旧值，打拍后同时互换——正是知识存档 3.4 节"原地更新会交换失败"那个反例的正面证明 |

**① test_dff_hold——记忆存在的直接证明。** `init=1`，连打 5 拍不调 `d()`，断言 `q` 恒为 1。这一条回应了整个项目的起点：SR 锁存器那个“反馈环在软件里无法表达”的困境——现在，记忆第一次真实地在软件里发生了。

**② test_dff_edge——边沿纪律三段论。** 三个断言各卡一个时间点：`d(1)` 后 `q` 仍是 0（边沿**前**）、`tick()` 后 `q=1`（边沿**上**）、再打一拍仍是 1（使能**已消费**）。三段合起来完整框出了“边沿触发”的时序形状。

**③ test_dff_last_d_wins——D 是导线语义。** `d(1)` 后 `d(0)`，打拍得 0：边沿时刻只认导线上最后的电平。

**④ test_register_basic——组装与纪律的回归。** 初始 `0x0F`（验证 `__init__` 的逐位拆装和 `value` 的重组互为逆操作）、`len(bits)==8`（结构检查：确实是 8 个 DFF）、边沿前旧值/边沿后新值、无写入再打拍保持——把 ①② 的纪律在寄存器层重放一遍。

**⑤ test_register_mask——位宽截断。** `d(0x1FF)` 打拍后得 `0xFF`，验证截断发生在 `d()` 的逐位广播里。

**⑥ test_swap_with_clock——旗舰测试。** 交换 A(5)、B(9) 两个寄存器：

```python
va, vb = a.value, b.value   # 组合阶段：先把两个旧值读进局部变量
a.d(vb)
b.d(va)
clk.tick()                  # 统一提交
```

这也是反例（`regs[0]=regs[1]; regs[1]=regs[0]` 原地交换失败）的正面版本。断言卡住四个时间点：打拍**前** A、B 都必须是旧值（如果 `d()` 会立刻改 `q`，这两条立刻失败），打拍**后**同时互换，外加 `cycles==1`。这个测试证明的不只是“交换成功了”，而是“**同拍读旧写新**的纪律被整个体系遵守”——将来 CPU 的每一拍（取指、执行、写回）都依赖这条纪律。

**⑦ test_clock_multi——CPU 主循环的最小预演。** 3 拍循环“读旧值 → `d(旧值+1)` → 打拍”，值 1→2→3→4，`cycles==3`。这个“每拍读旧算新再提交”的结构，就是未来 CPU `step()`（fetch → decode → execute → 提交）的缩影。