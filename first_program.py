"""第一个 mock_CPU 程序：5! = 120，结果存到内存 0x80"""
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
n, halted = cpu.run(trace=True)    # trace=True 逐条打印指令和状态
print(f"\n执行 {n} 条指令，停机={halted}")
print(f"R1 = {cpu.rf.read(1)}（期望 120）")
print(f"内存[0x80] = {cpu.ram.read(0x80)}")
print(f"标志位 = {cpu.flags()}")