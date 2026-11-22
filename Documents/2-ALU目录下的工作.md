[TOC]

# 早期ALU回顾 

**`full_adder.py` 目前并不是 8 位的**——它是参数化的（位宽由调用者传入 `num`），从来没有写死 8。

除此之外还有4 个问题，其中两个对搭 ALU 是致命的：

1. **只打印不返回**：`full_adder_1` 把结果 `print` 出来就结束了，函数返回 `None`——结果无法被上层（ALU）使用
2. **减法是错的**：注释说 `CI=1` 表示减法，但代码没有对 B 取反，实际算的是 `A+B+1`。正确的减法是补码：`A−B = A + ~B + 1`
3. **静默截断**：输入超过 `num` 位时多余的高位被直接丢弃，不报错，结果悄悄出错
4. **变量遮蔽**：`full_adder_1` 里 `num=int(str1,2)` 把参数 `num` 覆盖掉，还残留调试 `print`



# ALU的重写和完善

## `full_adder.py`的重写

```
8 位行波进位加减法器：
结构：半加器(semi_adder_one) → 一位全加器(full_adder_one) → 行波进位链(ripple_add)。
减法通过补码实现：A - B = A + ~B + 1。
```

当前函数：

- `semi_adder_one`：一位半加器，输入$x_1$，$x_2$，返回本位和$s$、向高位的进位$co​$
- `full_adder_one`：一位全加器，输入$x_1​$，$x_2​$，$x_3​$【地位上来的】，返回本位和$s​$、向高位的进位$co​$
- `to_bits`：整数 → 低位在前的位列表。超出 n 位的高位丢弃（对齐硬件位宽）。
- `from_bits`：低位在前的位列表 → 整数。

> **位列表低位在前（LSB first）**。原因是进位从 bit0 向 bit7 传播，LSB 在前意味着“列表从头到尾”恰好就是“信号从低位到高位”的处理顺序，后面所有循环都因此变成朴素的正序遍历。
>
> `to_bits` 同时承担截断职责——超出 `n` 位的部分直接丢弃，把旧版“静默截断”的行为显式化为文档化的约定。

- `ripple_add`：行波进位加法链，位列表均低位在前。 返回 (和的位列表, 各级进位输出列表, 最高位进位 C)。

> 名字来自“行波进位”（ripple-carry）：第 1 位要等第 0 位的进位，第 2 位要等第 1 位……进位像波一样逐级向上传。
>
> ```python
> def ripple_add(a_bits, b_bits, ci=0):
>     sum_bits, carries = [], []
>     for x, y in zip(a_bits, b_bits):
>         s, ci = full_adder_one(x, y, ci)   #  注意 ci 的循环复用
>         sum_bits.append(s)
>         carries.append(ci)
>     return sum_bits, carries, ci
> ```
>
>  `ci` 这一个变量**既是上一轮的输出又是这一轮的输入**——这正好就是电路里那根串起所有全加器的进位线。
>
> 返回值有三样，其中 `carries`（每一级的进位输出）是特意保留的：`carries[-2]` 是“进入最高位 bit7 的进位”，它是后面计算溢出标志 V 的原料。**在加法器层就把中间信号引出来，ALU 层才不用重新推导。**
>
> 
>
> `carries` 是**每一级全加器的进位输出**组成的列表：`carries[i]` = 第 i 位加完之后向第 i+1 位送出的进位。
>
> ```
> carries = [c0, c1, c2, c3, c4, c5, c6, c7]
> 索引:      0   1   2   3   4   5   6   7
> 负索引:                            -2  -1
> ```
>
> c6 （-2）与 C/c7（-1） 不一致就是溢出。

- `add8`：8 位加法：a + b + cin → (和, 进位 C, 进入 bit7 的进位 c6)。
- `sub8`：8 位减法：a - b = a + ~b + 1 → (差, C, c6)。 C 为"借位取反"惯例：C=1 表示够减（无借位），C=0 表示发生了借位。

> ```python
> def add8(a, b, cin=0):
>     sum_bits, carries, co = ripple_add(to_bits(a), to_bits(b), cin)
>     return from_bits(sum_bits), co, carries[-2]
> 
> def sub8(a, b):
>     b_not = [NOT(x) for x in to_bits(b)]      # ① 减数逐位取反（NOT 门）
>     sum_bits, carries, co = ripple_add(to_bits(a), b_not, 1)   # ② 初始进位置 1
>     return from_bits(sum_bits), co, carries[-2]
> ```
>
> 在 8 位世界里 ~B = 255 − B，所以 ~B + 1 = 256 − B，加回去正好实现减法（模 256）。
>
> C 标志沿用“借位取反”惯例（6502/ARM 风格）：够减时加法产生最高进位 C=1，不够减时 C=0。



##  `alu.py`

```
8 位 ALU：算术、逻辑、移位、乘法运算与标志位。
 
全部运算基于 gate.py 的门电路与 full_adder.py 的加法器实现。
 
标志位定义（对齐主流 8 位 CPU 惯例）：
  Z — 结果为 0（用 NOR 门对全部位或之后取反得到）
  N — 结果最高位 bit7 为 1
  C — 加法进位；减法"借位取反"（C=1 表示无借位）；移位时为移出的那一位；
      MUL 时表示积超出 8 位（高字节非 0）
  V — 有符号溢出，仅 ADD/SUB 有意义，其余恒为 0
```

### 标志位的基础设施

- `_zero_flag`：Z = NOR(b0..bn)，所有位 OR 起来再取反。
- `_mkflags`：由结果的位列表生成完整标志位。bits 低位在前、恰好 8 位。【Z,N,C,V】

```python
def _zero_flag(bits):
    return NOT(reduce(OR, bits))     # Z = NOR(b0..b7)

def _mkflags(bits, c=0, v=0):
    return {"Z": _zero_flag(bits), "N": bits[-1], "C": c, "V": v}
```



### 算术操作

```python
def alu_add(a, b):
    s, c, c6 = add8(a, b)
    return s, _mkflags(to_bits(s), c, XOR(c6, c))    # V = c6 ⊕ c7
```

- `alu_add`：V 用的是教科书判定：**进入符号位的进位（c6）与离开符号位的进位（C）不相等，即溢出**。
- `alu_sub`：`alu_sub` 结构完全相同，只是换用 `sub8`。
- ` alu_mul`：乘法，移位相加。





### 逻辑操作

```python
def _bitwise(a, b, gate):
    bits = [gate(x, y) for x, y in zip(to_bits(a), to_bits(b))]
    return from_bits(bits), _mkflags(bits)
```

- `_bitwise`：AND/OR/XOR 共用这一个骨架，`gate` 参数传不同的门函数——**把“哪种门”作为参数**，避免重复代码。`alu_not` 是单目版本。逻辑运算 C=V=0（硬件惯例：逻辑指令不产生进位和溢出）。
- `alu_and`：与
- ` alu_or`：或
-  `alu_xor`：异或
- `alu_not`：非



### 移位 / 循环移位 

LSB-first 表示在这里展现了第二个好处——**移位操作退化成朴素的列表操作**。

“掉出去的那一位进 C”是移位指令的标准语义（也是 C 语言的源头：`KC = (unsigned char)(K << 1);` 丢掉的位硬件里就落在进位上）。

- `alu_shl`：逻辑左移，低位补 0，bit7 移出进 C
- `alu_shr`：逻辑右移，高位补 0，bit0 移出进 C
- `alu_rol`：循环左移， bit7 绕回 bit0，[bits[-1]] + bits[:-1]
- `alu_ror`：循环右移， bit0 绕回 bit7，bits[1:] + [bits[0]]

```python
def alu_shl(a):
    bits = to_bits(a)
    out = [0] + bits[:-1]        # 低位补 0，bit7 移出进 C
    return from_bits(out), _mkflags(out, c=bits[-1])
 
 
def alu_shr(a):
    bits = to_bits(a)
    out = bits[1:] + [0]         # 逻辑右移，高位补 0，bit0 移出进 C
    return from_bits(out), _mkflags(out, c=bits[0])
 
 
def alu_rol(a):
    bits = to_bits(a)
    out = [bits[-1]] + bits[:-1]  # bit7 绕回 bit0
    return from_bits(out), _mkflags(out, c=bits[-1])
 
 
def alu_ror(a):
    bits = to_bits(a)
    out = bits[1:] + [bits[0]]    # bit0 绕回 bit7
    return from_bits(out), _mkflags(out, c=bits[0])
```

> 后注：ROL/ROR 后在指令化一站升级为穿 C 链式旋转（`out = [cin] + bits[:-1]`，多字节移位链 SHL lo / ROL hi 的原语）——本节描述的是 ALU 站当时的实现。
>
> ```python
> def alu_rol(a, b=0, cin=0):
>     bits = to_bits(a)
>     out = [cin] + bits[:-1]      # C 绕入 bit0，bit7 转出回 C
>     return from_bits(out), _mkflags(out, c=bits[-1])
> 
> 
> def alu_ror(a, b=0, cin=0):
>     bits = to_bits(a)
>     out = bits[1:] + [cin]       # C 绕入 bit7，bit0 转出回 C
>     return from_bits(out), _mkflags(out, c=bits[0])
> 
> ```
>
> 旧版的 `alu_rol` 是**字节内自转**，bit7 绕回 bit0 走的是“内部捷径”，C 标志只是**旁观看一眼**（记下转出的位），不参与传送。
>
> 而 `SHL lo / ROL hi` 这条多字节移位链需要的是**穿 C 旋转**——bit7 先**出去到 C**，C 里的旧值**进来当 bit0**。
>
> | 变体       | 语义                 | 代表                                          |
> | ---------- | -------------------- | --------------------------------------------- |
> | 字节内自转 | b7→b0 直通，C 只旁观 | x86 的 ROL/ROR、Z80 的 RLCA/RRCA              |
> | 穿 C 旋转  | b7→C→b0，C 是传送带  | 6502 的 ROL/ROR、x86 的 RCL/RCR、Z80 的 RL/RR |
>
> 穿 C 之后有个值得注意的行为：**一个位从 bit7 走到 bit0 需要两次 ROL**——第一次 ROL 它出去进 C（结果位里没有它），第二次 ROL 它才从 C 进来。



### 分发层

字典把操作码映射到函数，`alu()` 做两件事：把输入截断到 8 位（模拟硬件忽略超宽输入），然后以**统一签名 (a, b)、统一返回 (结果, 标志字典)** 的格式调用。

这个“统一签名”的约定也是后面测试抓出 bug 的地方。

```python
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
```

ALU操作选择：

```python
WORD = 8
MASK = 0xFF

def alu(op, a, b=0):
    """执行运算，返回 (结果, 标志位字典)。MUL 结果 16 位，其余 8 位。
 
    输入自动截断到 8 位（对齐硬件：超出位宽的输入被忽略）。
    """
    return OPS[op](a & MASK, b & MASK)
```





##  `test_alu.py`

穷举测试，所有运算都和 Python 原生结果逐对对照（每类运算 256×256 = 65536 组输入）。





# 完成的工作

**`ALU/full_adder.py`（重构）**：保留门级的半加器→全加器→行波进位链结构，新增 `add8` / `sub8`（补码减法 `A + ~B + 1`），全部返回结果；`ripple_add` 同时返回各级进位，供溢出判断使用；旧的 `full_adder(num,CI,A,B)` 接口保留但现在返回值。

**`ALU/alu.py`（新建）**：统一入口 `alu(op, a, b)`，涵盖——
- 算术：ADD、SUB、MUL（8×8→16 位移位相加，用 AND 门做部分积选择、16 位行波加法器累加）
- 逻辑：AND、OR、XOR、NOT（逐位调用 `gate.py` 的门）
- 移位：SHL、SHR、ROL、ROR（移出位进 C）
- 标志位：**Z**（用 NOR 门对全位取反）、**N**、**C**（减法为“借位取反”惯例）、**V**（`XOR(c6, C)` 门级推导）

**`ALU/test_alu.py`（新建）**：11 种运算 × 全部 65536 组输入，连标志位一起与 Python 原生结果逐项对照。中途抓到并修掉了 `alu_not`/移位函数的单参数签名 bug（分发器统一传两个参数）。

**`README.md`**：补充了结构说明、运行方式、标志位约定和路线图。





# 状态确认与后续工作【组合逻辑完成时】

“组合逻辑全部完成”（门 → 加法器 → ALU → 穷举测试），接下来就进入**时序逻辑阶段**——这也是本项目从“电路仿真”变成“CPU”的分水岭。

## 阶段一：时序骨架

实现 `DFlipFlop` → `Register` → 时钟 `tick()` 这条线，核心就是“current/next 二分 + 统一提交”的纪律。

验收标准也很明确：**寄存器在两次 tick 之间保持值不变，只在 tick 时刻采纳新值**——用测试证明“记忆”这件事真的发生了。这步完成意味着 SR 锁存器那个“反馈环”问题被正式解决。

## 阶段二：存储部件

- **寄存器堆**：比如 R0~R7，带两个读端口、一个写端口——读端口就是 MUX，写端口的地址选择就是译码器，正好补上之前讨论缺失的那两个组合部件
- **内存（RAM）**：一个字节数组 + 地址寻址
- **PC（程序计数器）**：特殊寄存器，支持“自增 1”和“跳转时装载”两种 next 来源

## 阶段三：指令集与控制器

这是设计决策最多的一步：

1. **定义指令集**：取数/存数、ALU 运算（复用现成的 `alu.py`）、比较（CMP，本质是 SUB 但不写回，只更新标志位）、条件跳转（消费 Z/N/C/V 标志——标志位为什么重要到这一步就体现出来了）
2. **译码器**：操作码 → 控制信号
3. **选择微架构**：一拍一条指令（简单直接），还是 FETCH→DECODE→EXECUTE 的多周期状态机（更接近真实硬件，也更能发挥阶段一的时钟设计）。我的建议是**先用“一拍一条”跑通，再演化成状态机**，避免第一次就同时调试两个新东西

## 阶段四：整机与验证

`CPU` 类挂上 `step()` / `run()`，写一个小测试程序（比如“用循环加法模拟乘法”或“斐波那契数列”），把执行结果和 Python 直接算的结果对照——给 CPU 也做一套“差分测试”，风格上和 `test_alu.py` 一脉相承。如果到时还想更有仪式感，可以加一个迷你汇编器（助记符 → 机器码）。





# 包结构改造

目录下新增`__init__.py`。

ALU：组合算术部件包（门 → 加法器 → ALU）。

