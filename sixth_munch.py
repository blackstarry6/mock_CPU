"""第六个程序：Munching Squares（咀嚼方阵，1962，PDP-1 / HAKMEM）——最古老的 demo。

历史：MIT 黑客在 PDP-1 上发现"把 x XOR y 铺满屏幕"会产生分形感的方阵花纹，
让阈值流动后花纹仿佛在"啃"屏幕——demoscene 由此发源（收录于 HAKMEM 备忘录）。

本机实现（8 位机正好装下 8×8 版：x, y ∈ 0..7，x XOR y ∈ 0..7）：
- 机器程序：双重循环把 64 格的 x^y 值算进帧缓冲 0xC0~0xFF（约 530 条指令）。
  遍历用 fifth/hello 同款自修改指针：ST 的地址字节每格被程序自己改写。
- 显示器（Python 驱动端）：帧缓冲不是 0/1，而是"本格的 XOR 值"——渲染时
  以阈值 t 扫描：值 < t 的格点亮。t 逐帧上升，花纹层层生长、全亮、坍缩重来，
  就是当年那口"啃"。程序与显示异步解耦 = PDP-1 的 CRT 持续刷新、程序只写内存。
"""
import time

from CPU import isa
from CPU.cpu import CPU

FB = 0xC0          # 帧缓冲基址：8 行 × 8 列 = 64 格，占 0xC0~0xFF

prog = (
    isa.I_LDI(5, 8) +               # 0x00: R5 = 常数 8
    isa.I_LDI(1, 0) +               # 0x02: R1 = y
    isa.I_LDI(6, FB) +              # 0x04: R6 = 写入指针
    isa.I_LDI(0, 0) +               # 0x06: y 循环头：x = 0
    isa.I_MOV(3, 0) +               # 0x08: x 循环头：R3 = x
    isa.I_ALU("XOR", 3, 1) +        # 0x0A: R3 = x XOR y
    isa.I_ST(3, FB) +               # 0x0C: 存入当前格 ← 自修改目标
    isa.I_UN("INC", 6) +            # 0x0E: 指针 +1
    isa.I_ST(6, 0x0D) +             # 0x10: ★ 把新指针写回 0x0D（上面 ST 的地址字节）
    isa.I_UN("INC", 0) +            # 0x12
    isa.I_ALU("CMP", 0, 5) +        # 0x14: x == 8？
    isa.I_JMP("JNZ", 0x08) +        # 0x16
    isa.I_UN("INC", 1) +            # 0x18: y + 1
    isa.I_ALU("CMP", 1, 5) +        # 0x1A: y == 8？
    isa.I_JMP("JNZ", 0x06) +        # 0x1C
    isa.I_HALT()                    # 0x1E
)


def render(cpu, threshold=None):
    """渲染一帧：threshold=None 显示原始十六进制值，否则值 < threshold 的格点亮。"""
    print("+" + "-" * 8 + "+")
    for y in range(8):
        row = ""
        for x in range(8):
            v = cpu.ram.read(FB + y * 8 + x)
            row += f"{v:x}" if threshold is None else ("#" if v < threshold else "·")
        print("|" + row + "|")
    print("+" + "-" * 8 + "+")


cpu = CPU(prog)
n, halted = cpu.run()
print(f"机器用 {n} 条指令算完 64 格 XOR 表（停机={halted}）\n")

print("原始数据（每格 = x XOR y 的十六进制值）：")
render(cpu)
time.sleep(0.5)

print("\n阈值扫描（值 < t 点亮；t 逐帧上升 → 花纹生长、全亮、坍缩）：")
for cycle in range(3):
    for t in range(1, 10):
        print(f"—— t = {t} ——")
        render(cpu, threshold=t)
        time.sleep(0.12)
