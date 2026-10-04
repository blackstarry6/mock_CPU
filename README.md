# mock_CPU

用软件自底向上模拟 8 位 CPU：感知机逻辑门 → 加法器 → ALU → 时序部件 → 存储部件 →（计划）指令集与整机。

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
- `知识存档.md` — 从组合逻辑到时序逻辑的设计笔记
- `后续工作.md` — 路线图与技术债

## 运行（包结构：全部在项目根目录、用 -m 运行）

```bash
python -m ALU.test_alu            # ALU 穷举测试（约 5 分钟）
python -m COMB.test_comb          # 组合部件测试（瞬时）
python -m SEQ.test_seq            # 时序行为测试（瞬时）
python -m SEQ.test_register_file  # 寄存器堆测试
python -m SEQ.test_pc             # PC 测试
python -m MEM.test_ram            # RAM 测试
```

## 关键约定

- 8 位字宽、LSB-first 位列表、超出位宽自动截断
- 时序纪律：组合阶段"读旧值 + d()/write() 声明"，时钟沿 tick() 统一提交；
  同拍读到的永远是旧值
- 标志位 Z/N/C/V（减法 C 为借位取反）；乘法 8x8 → 16 位
- 依赖方向自底向上：gate → full_adder → alu；dff → register → register_file/pc

## 路线图

- [x] 逻辑门
- [x] 8 位加减法器
- [x] ALU（算术/逻辑/移位/乘法/标志位）
- [x] 时序骨架：DFlipFlop → Register → Clock
- [x] 存储部件：寄存器堆 / PC / RAM（MUX 与译码器首次登场）
- [ ] 阶段三：指令集与控制器
- [ ] 阶段四：整机与验证
