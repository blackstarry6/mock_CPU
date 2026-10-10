# mock_CPU

用软件自底向上模拟 8 位 CPU：感知机逻辑门 → 加法器 → ALU → 时序部件 → 存储部件 → 指令集与整机（已跑通）。

## 结构

- `ALU/` — 组合算术部件
  - `gate.py` 基本逻辑门（AND/NAND/OR/NOR/XOR/NOT，感知机实现）
  - `full_adder.py` 半加器 → 全加器 → 8 位行波进位加减法器（补码减法）
  - `alu.py` 11 种运算 + Z/N/C/V 标志位
  - `test_alu.py` 穷举测试（197 万项断言）
- `COMB/` — 通用组合部件
  - `mux.py` 门级 2 选 1 / one-hot AND-OR 阵列 / 字级多路选择器
  - `decoder.py` n → 2^n one-hot 译码器（带使能端）
  - `test_comb.py`
- `SEQ/` — 时序部件
  - `dff.py` D 触发器 + 时钟（行为级：显式状态 + 边沿统一提交）
  - `register.py` 8 位寄存器（8 个 DFF 共享时钟组成）
  - `register_file.py` 8×8 位寄存器堆（双读端口 MUX + 单写端口译码器）
  - `pc.py` 程序计数器（incr 经加法器自增 / load 跳转装载）
  - `test_seq.py` / `test_register_file.py` / `test_pc.py`
- `MEM/` — 存储部件
  - `ram.py` 256 字节同步 RAM（读组合、写打拍、load_program 烧写）
  - `test_ram.py`
- `CPU/` — 指令集与整机（阶段三）
  - `isa.py` 统一双字节指令编码、24 种助记符、汇编辅助与反汇编
  - `control.py` 控制器（"微程序 ROM"查找表 + 跳转条件判断；CMP/INC/DEC 派生）
  - `cpu.py` 整机接线 + step()/run()（一拍一条指令，统一提交）
  - `test_cpu.py` 单指令 → 条件分支 → 循环程序差分（222 项断言）
- `first_program.py` — 入门示例：带指令跟踪的阶乘循环程序（见「第一个程序」）
- `second_hello.py` — 第二个示例：内存映射 I/O + 自修改代码打印字符串（见「第二个程序」）
- `third_screen.py` — 第三个示例：帧缓冲"屏幕" + 字符流/回车端口（见「第三个程序」）
- `fourth_multibyte.py` — 第四个示例：16 位多字节加减法，手工传递进位（见「第四个程序」）
- `fifth_division.py` — 第五个示例：软件除法（移位相减恢复余数法，121 组矩阵差分）（见「第五个程序」）
- `知识存档.md` — 从组合逻辑到时序逻辑的设计笔记
- `后续工作.md` — 路线图与技术债

## 架构与数据通路

分层依赖（自底向上搭建，箭头方向即 import 方向，永不反向）：

```
第 5 层 集成        CPU/cpu.py                          ← 唯一 import 四个部件包的文件（塔尖）
第 4 层 规格与语义   CPU/isa.py · CPU/control.py          ← 零依赖的纯定义（指令编码 / 微程序表）
第 3 层 系统部件     SEQ/register_file.py · SEQ/pc.py · MEM/ram.py
第 2 层 功能部件     SEQ/register.py · COMB/mux.py+decoder.py · ALU/full_adder.py · ALU/alu.py
第 1 层 原语        SEQ/dff.py（记忆之根）· ALU/gate.py（组合之根）
```

三条架构铁律：依赖严格单向（部件包不知道 CPU 的存在）；isa/control
不依赖任何部件（纯规格，换实现不动规格）；跨包 import 仅 6 条（耦合面刻意收窄）。

一条指令的旅程（`CPU.step()` 五步，声明与提交分离）：

```
PC ─地址→ RAM.read×2 ─op,arg→ isa.decode → control.signals（微码六信号）
                                             │
RF.read（门级 MUX 译码选择）─A,B→ ALU ─结果+标志┤
      │                             ├→ RF.write / RAM.write（声明）
      │                             └→ 4×DFF 标志位（声明）
      └→ PC 下一拍：add8(pc,2) 顺序 / load(目标) 跳转（声明）
                              ↓
                   clk.tick() ← 全机唯一提交点：PC、寄存器、RAM、标志同时翻转
```

测试金字塔：ALU 197 万项穷举打底，向上 COMB 109、SEQ 18+23+9、MEM 11、
CPU 222——底层全绿，上层失败只需查上层。

## 运行（包结构：全部在项目根目录、用 -m 运行）

```bash
python -m CPU.cpu           # 整机演示：带指令跟踪的累加循环
python -m CPU.test_cpu      # CPU 测试（含斐波那契等循环程序差分，约 10 秒）
python -m ALU.test_alu      # ALU 穷举测试（约 5 分钟）
python -m COMB.test_comb    # 组合部件测试（瞬时）
python -m SEQ.test_seq      # 时序行为测试（瞬时）
python -m SEQ.test_register_file
python -m SEQ.test_pc
python -m MEM.test_ram
```

## 第一个程序

`first_program.py` 是上手示例：用助记符辅助函数拼出"5! = 120"的阶乘循环，
带指令跟踪运行，结果写入内存 0x80。在项目根目录执行 `python first_program.py` 即可。
核心骨架（每条指令恰好 2 字节，第 k 条位于地址 2k——**注释标地址、跳转目标按此手算**，
这是手工汇编的基本功）：

```python
from CPU import isa
from CPU.cpu import CPU

prog = (isa.I_LDI(0, 5) +          # 0x00: R0 = n = 5
        isa.I_LDI(1, 1) +          # 0x02: R1 = acc = 1
        isa.I_ALU("MUL", 1, 0) +   # 0x04: acc *= n
        isa.I_UN("DEC", 0) +       # 0x06: n -= 1（更新标志）
        isa.I_JMP("JNZ", 0x04) +   # 0x08: n≠0 则回 0x04
        isa.I_ST(1, 0x80) +        # 0x0A: 结果写入内存 0x80
        isa.I_HALT())              # 0x0C

cpu = CPU(prog)
n, halted = cpu.run(trace=True)    # 逐条打印指令、寄存器与标志
print(cpu.rf.read(1), cpu.ram.read(0x80), cpu.flags())
```

写自己的程序就是这三步：**`isa.I_*` 拼字节 → `CPU(prog)` 装载 → `run(trace=True)` 执行**。
随时用 `cpu.rf.read(i)` / `cpu.ram.read(addr)` / `cpu.flags()` 观察状态；
单步调试可循环调用 `cpu.step()`。约定：程序放低地址、数据从 0x80 起，
256 字节共用一块内存。

## 第二个程序：让机器打印字符

`second_hello.py`（`python second_hello.py`，输出 `HELLO, MOCK_CPU!`，98 条指令）
**不给 CPU 增加任何东西**就实现了输出，靠两个经典概念：

- **内存映射 I/O**：约定地址 0xFE 是"控制台端口"，往它写字节就显示一个字符。
  程序继承 RAM 造了一颗带屏幕的内存（`ConsoleRAM`），CPU 以为自己只是在
  做普通的 ST——设备挂在总线上"冒充"内存，这正是真实计算机的 I/O 方式
  （C64 的屏幕、串口芯片的寄存器都是这么接的）
- **自修改代码**：本机 LD/ST 只有直接地址、没有指针寻址，无法遍历字符串。
  解法是循环里把新地址写回那条 LD 指令的地址字节（指令与数据同片内存，
  冯·诺依曼结构的本义）——程序运行中改写自己。这是早期程序员的日常，
  也是现代 CPU 的禁忌（指令缓存与流水线不一致，x86 遇到必须冲刷流水线）

## 第三个程序：帧缓冲"屏幕"

`third_screen.py`（`python third_screen.py`）造出了一块"真·屏幕"——同一个
程序里对照演示两种输出模型。设备约定（CPU 依然不知情）：`0x90~0x9F` 共
16 字节是**帧缓冲**（这片内存"就是"屏幕），`0xFE` 字符流端口打一个字符，
`0xFD` 回车端口换行。

- **teletype vs framebuffer**：标题 `DEMO:` 走流式端口——"写一个打一个"，
  输出是流水；进度条走帧缓冲——渲染器读内存的**当前状态**作画，屏幕显示
  "存着什么"而非"来过什么"，所以格子可以被反复改写、就地更新。这是显存
  相对打印机的本质能力（C64 屏幕内存、显卡显存同理）
- **刷新与写入异步解耦**：渲染不在写钩子里，而由驱动端的刷新循环按圈触发
  ——对应真实显卡"CPU 随便写、显示器按场频自己扫"的工作方式
- 填格子复用自修改代码技巧（指针写回 ST 指令的地址字节）

## 第四个程序：多字节加减法

`fourth_multibyte.py`（`python fourth_multibyte.py`）在没有 ADC/SBB 指令的机器上
做 16 位加减法，6 组差分用例全过（含进位链、16 位溢出、借位链）。核心问题：
**进位必须跨字节传递，但每条 ADD 都会覆盖 C 标志**。解法：

- **进位不放标志里，放寄存器里**（R2 传递）：每字节"带进位加"分两步——
  先 `ADD` 并趁 C 还在立即分支落进 R2；再补 cin：`R0==255` 时回绕并再置进位，
  否则安全 +1。进位输出 = 两股进位在寄存器里汇合
- 减法对偶：借位判定用 `JNC`（SUB 的 C 是借位取反），回绕检测 `R0==0` 再减
- 每字节 ~14 条指令——写完就懂了真实 CPU 为什么都有 `ADC`/`SBB`（1 条顶 14 条），
  这是本机 ISA 最有资格的扩展候选

## 第五个程序：软件除法

`fifth_division.py`（`python fifth_division.py`）用**移位相减（恢复余数法）**实现
8 位 ÷ 8 位 = 商 + 余数，8 组精选 + 11×11 全矩阵共 121 组差分全过。算法与
8086 `DIV` 指令的微码同构，21 条指令：

- 每轮处理被除数一位：`SHL R0` 把被除数最高位顶进 **C 标志（移位窗口）**，
  `SHL R1` 再把它从 bit0 注入余数（两次移位间 C 会被覆盖，需分支先落地）；
  然后 CMP 试减——够减则 SUB、商本位置 1，不够则跳过（"恢复"）
- **为什么 8 位机除法靠软件**：加减是并行链、乘法是单向阵列（部分积可一次
  展开，一拍完成），而除法每一位依赖上一位试减的结果——带反馈的迭代，
  硬件要么做多拍状态机、要么单拍级联 8 级比较减法拖慢全机时钟；加上晶体管
  预算紧（6502 约 3500 管）和除法需求稀少，历史选择就是软件子程序。
  6502/Z80/8051 均无 DIV，ARM 与 RISC-V 基础指令集也长期不含除法
- 开发花絮：手算跳转地址偏了 2 导致死循环——"该做汇编器"的活案例

## 指令集（统一双字节：操作码 + 操作数字节）

```
LDI/MOV/LD/ST   数据传送（立即数/寄存器/内存）
ADD SUB AND OR XOR MUL CMP   R0~R7 寄存器运算，CMP 只更新标志不写回
INC DEC SHL SHR 单目运算（INC/DEC 即 B=1 的 ADD/SUB）
JMP JZ JNZ JC JNC JN JNN JV 条件跳转（消费 Z/N/C/V）
HALT 停机；0xF8 预留 DIV
```

## 关键约定

- 8 位字宽、LSB-first 位列表、超出位宽自动截断
- 时序纪律：组合阶段"读旧值 + d()/write() 声明"，时钟沿 tick() 统一提交；
  同拍读到的永远是旧值
- 标志位 Z/N/C/V（减法 C 为借位取反）；乘法 8x8 → 16 位（存低字节，C=高字节非 0）
- 依赖方向自底向上：gate → full_adder → alu；dff → register → register_file/pc；
  部件包不知道 CPU 的存在

## 路线图

- [x] 逻辑门
- [x] 8 位加减法器
- [x] ALU（算术/逻辑/移位/乘法/标志位）
- [x] 时序骨架：DFlipFlop → Register → Clock
- [x] 存储部件：寄存器堆 / PC / RAM（MUX 与译码器首次登场）
- [x] 指令集与控制器：ISA / 微程序表 / 整机跑通循环程序
- [ ] 阶段四：整机增强与验证（变长指令、多周期状态机、迷你汇编器等可选扩展）

