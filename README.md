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

