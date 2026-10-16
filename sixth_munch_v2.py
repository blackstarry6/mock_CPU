"""sixth_munch 的间接寻址版（v2）：同一张 XOR 表，两种机制，逐字节差分。

- 旧版（自修改）：ST 的地址字节每格被程序自己改写——指针住在指令里
  （third_hello/munch 时代的标准手法，见 sixth_munch.py，本文件不改原程序）
- 新版（LDX/STX 寄存器间接）：地址 = 指针寄存器 R6 的内容，STX 一条顶
  ST+补丁两条——指针是寄存器里的普通数据，程序不再改写自己

验收标准：两版各跑一遍，帧缓冲 0xC0~0xFF 的 64 字节必须完全相同；
指令数从 547 降到 483（每格省 1 条，64 格共省 64 条）。
"""
import time

from CPU import isa
from CPU.cpu import CPU

FB = 0xC0

# —— 旧版（与 sixth_munch.py 完全相同的核心，原文件保持不动）——
old_prog = (
    isa.I_LDI(5, 8) +               # 0x00
    isa.I_LDI(1, 0) +               # 0x02
    isa.I_LDI(6, FB) +              # 0x04
    isa.I_LDI(0, 0) +               # 0x06: y 头
    isa.I_MOV(3, 0) +               # 0x08: x 头
    isa.I_ALU("XOR", 3, 1) +        # 0x0A
    isa.I_ST(3, FB) +               # 0x0C ← 自修改目标
    isa.I_UN("INC", 6) +            # 0x0E
    isa.I_ST(6, 0x0D) +             # 0x10 ← 补丁：指针刻回指令
    isa.I_UN("INC", 0) +            # 0x12
    isa.I_ALU("CMP", 0, 5) +        # 0x14
    isa.I_JMP("JNZ", 0x08) +        # 0x16
    isa.I_UN("INC", 1) +            # 0x18
    isa.I_ALU("CMP", 1, 5) +        # 0x1A
    isa.I_JMP("JNZ", 0x06) +        # 0x1C
    isa.I_HALT()                    # 0x1E
)

# —— 新版：STX 顶掉 ST+补丁，循环体 8 条 → 7 条 ——
new_prog = (
    isa.I_LDI(5, 8) +               # 0x00
    isa.I_LDI(1, 0) +               # 0x02
    isa.I_LDI(6, FB) +              # 0x04
    isa.I_LDI(0, 0) +               # 0x06: y 头
    isa.I_MOV(3, 0) +               # 0x08: x 头
    isa.I_ALU("XOR", 3, 1) +        # 0x0A
    isa.I_STX(3, 6) +               # 0x0C ★ 间接存储：mem[R6] ← R3，无补丁
    isa.I_UN("INC", 6) +            # 0x0E: 指针 +1——普通数据操作
    isa.I_UN("INC", 0) +            # 0x10
    isa.I_ALU("CMP", 0, 5) +        # 0x12
    isa.I_JMP("JNZ", 0x08) +        # 0x14
    isa.I_UN("INC", 1) +            # 0x16
    isa.I_ALU("CMP", 1, 5) +        # 0x18
    isa.I_JMP("JNZ", 0x06) +        # 0x1A
    isa.I_HALT()                    # 0x1C
)

cpu_old = CPU(old_prog)
n_old, h_old = cpu_old.run()
cpu_new = CPU(new_prog)
n_new, h_new = cpu_new.run()

fb_old = [cpu_old.ram.read(FB + i) for i in range(64)]
fb_new = [cpu_new.ram.read(FB + i) for i in range(64)]

print(f"旧版（自修改）  ：{n_old} 条指令，停机={h_old}")
print(f"新版（LDX/STX） ：{n_new} 条指令，停机={h_new}")
print(f"省 {n_old - n_new} 条（每格省 1 条 × 64 格）")
print(f"帧缓冲 64 字节逐字节比对：{'完全一致 ✓' if fb_old == fb_new else '不一致 ✗'}")


def render(cpu, threshold):
    print("+" + "-" * 8 + "+")
    for y in range(8):
        row = "".join("#" if cpu.ram.read(FB + y * 8 + x) < threshold else "·"
                      for x in range(8))
        print("|" + row + "|")
    print("+" + "-" * 8 + "+")


print("\n间接版算出的同一张表（t=4，四象限帧）：")
render(cpu_new, 4)
time.sleep(0.3)
