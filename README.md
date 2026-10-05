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
- `知识存档.md` — 从组合逻辑到时序逻辑的设计笔记
- `后续工作.md` — 路线图与技术债

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

