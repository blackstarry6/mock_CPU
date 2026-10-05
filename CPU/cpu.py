"""8 位 CPU 整机：部件接线 + 一拍一条指令的执行引擎。

"一拍"是对机器周期的抽象：取指、译码、执行、PC 更新在一拍内完成
（行为级 RAM 允许一拍内组合读两个字节；真机每拍只能访存一次）。
一拍内严格走时序纪律：读旧值 → 组合计算 → d()/write() 声明 →
clk.tick() 统一提交——同拍一致性由结构保证。

HALT 的语义是"停时钟"：仿真层布尔标志，不经时钟纪律。
"""
from ALU.alu import alu
from ALU.full_adder import add8
from SEQ.dff import DFlipFlop, Clock
from SEQ.pc import ProgramCounter
from SEQ.register_file import RegisterFile
from MEM.ram import RAM
from . import isa, control


class CPU:
    def __init__(self, program=None, base=0):
        self.clk = Clock()
        self.pc = ProgramCounter()
        self.rf = RegisterFile()
        self.ram = RAM()
        self.flag_z, self.flag_n = DFlipFlop(), DFlipFlop()
        self.flag_c, self.flag_v = DFlipFlop(), DFlipFlop()
        self.halted = False
        self.instr_count = 0
        if program:
            self.ram.load_program(program, base)
        self.clk.attach(self.pc, self.rf, self.ram,
                        self.flag_z, self.flag_n, self.flag_c, self.flag_v)

    # ---- 状态观察（组合读） ----

    def flags(self):
        return {"Z": self.flag_z.q, "N": self.flag_n.q,
                "C": self.flag_c.q, "V": self.flag_v.q}

    def state(self):
        """整机状态快照（调试/测试用）。"""
        return {
            "pc": self.pc.value,
            "regs": [self.rf.read(i) for i in range(8)],
            "flags": self.flags(),
            "halted": self.halted,
            "instrs": self.instr_count,
        }

    # ---- 执行 ----

    def step(self):
        """执行一条指令（取指→译码→执行→PC→统一提交）。已停机返回 False。"""
        if self.halted:
            return False
        # ① 取指：组合读两个字节（统一双字节格式）
        op = self.ram.read(self.pc.value)
        arg = self.ram.read(self.pc.value + 1)
        # ② 译码：ISA 字段 + 控制信号
        name, reg, other = isa.decode(op, arg)
        sig = control.signals(name)
        # ③ 执行：取操作数 → ALU/直通 → 声明写
        result, fl = self._pick_a(sig, reg, other), None
        if sig.alu_op is not None:
            b = self._pick_b(sig, other)
            result, fl = alu(sig.alu_op, result, b)
            if sig.flags:
                self._stage_flags(fl)
        if sig.dest == "RF":
            self.rf.write(reg, result)
        elif sig.dest == "MEM":
            self.ram.write(other, result)
        # ④ PC 下一拍：停机 / 跳转 / 顺序 +2（经加法器，255 回绕）
        if sig.jump == "HALT":
            self.halted = True
            return False
        elif sig.jump is not None and control.condition_met(sig.jump, self.flags()):
            self.pc.load(other)
        else:
            nxt, _, _ = add8(self.pc.value, 2)
            self.pc.load(nxt)
        # ⑤ 统一提交
        self.clk.tick()
        self.instr_count += 1
        return True

    def run(self, max_instr=10000, trace=False):
        """执行到 HALT 或指令数上限（防死循环）。返回 (执行指令数, 是否正常停机)。"""
        n = 0
        while n < max_instr:
            if trace:
                op = self.ram.read(self.pc.value)
                arg = self.ram.read(self.pc.value + 1)
                print(f"[{self.pc.value:3d}] {isa.disasm(op, arg):<15} "
                      f"regs={[self.rf.read(i) for i in range(8)]} {self.flags()}")
            if not self.step():
                break
            n += 1
        return n, self.halted

    # ---- 内部：操作数选择与标志登记 ----

    def _pick_a(self, sig, reg, other):
        if sig.a_from == "IMM":
            return other
        if sig.a_from == "MEM":
            return self.ram.read(other)
        if sig.a_from == "RF_SELF":
            return self.rf.read(reg)
        if sig.a_from == "RF_OTHER":
            return self.rf.read(other & 7)
        return None

    def _pick_b(self, sig, other):
        if sig.b_from == "ONE":
            return 1
        if sig.b_from == "RF_OTHER":
            return self.rf.read(other & 7)
        return 0

    def _stage_flags(self, fl):
        self.flag_z.d(fl["Z"])
        self.flag_n.d(fl["N"])
        self.flag_c.d(fl["C"])
        self.flag_v.d(fl["V"])


if __name__ == "__main__":
    # 演示：1+2+...+5 = 15（累加循环，带指令跟踪）
    prog = (isa.I_LDI(0, 5) + isa.I_LDI(1, 0) +
            isa.I_ALU("ADD", 1, 0) +     # 0x04: R1 += R0
            isa.I_UN("DEC", 0) +         # 0x06
            isa.I_JMP("JNZ", 0x04) +     # 0x08
            isa.I_HALT())                # 0x0A
    cpu = CPU(prog)
    n, halted = cpu.run(trace=True)
    print(f"\n执行 {n} 条指令，停机={halted}，R1={cpu.rf.read(1)}（期望 15）")
