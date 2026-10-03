# mock_CPU

用软件自底向上模拟 8 位 CPU：感知机逻辑门 → 加法器 → ALU →（计划）时序电路 → CPU。

## 结构

- `ALU/gate.py` — 基本逻辑门（AND/NAND/OR/NOR/XOR/NOT，感知机实现）
- `ALU/full_adder.py` — 半加器 → 一位全加器 → 8 位行波进位加减法器（补码减法）
- `ALU/alu.py` — 8 位 ALU：ADD/SUB/MUL、AND/OR/XOR/NOT、SHL/SHR/ROL/ROR，带 Z/N/C/V 标志位
- `ALU/test_alu.py` — 穷举测试（全部 256x256 输入与 Python 原生运算对照）
- `知识存档.md` — 从组合逻辑到时序逻辑的设计笔记

## 运行

```bash
cd ALU
python test_alu.py   # 穷举测试（约 5 分钟，197 万项断言）
python alu.py        # ALU 演示
```

## ALU 标志位约定

| 标志 | 含义 |
|------|------|
| Z | 结果为 0 |
| N | 结果 bit7 为 1 |
| C | 加法进位 / 减法借位取反（1=无借位）/ 移位移出位 / 乘法积超出 8 位 |
| V | 有符号溢出（仅加减法有意义） |

乘法为 8x8 → 16 位（移位相加，16 位行波进位累加器）。

## 路线图

- [x] 逻辑门
- [x] 8 位加减法器
- [x] ALU（算术/逻辑/移位/乘法/标志位）
- [ ] 时序骨架：DFlipFlop → Register → 时钟 tick（见 知识存档.md）
- [ ] 寄存器堆、PC、指令译码与执行
