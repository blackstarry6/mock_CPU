"""指令集定义（ISA）：编码格式、操作码表、助记符与编解码。

统一双字节指令：[操作码][操作数字节]。
操作码按功能分段，寄存器编码进操作码低位（3 位，R0~R7）：

    0x00-0x07  LDI Ri, imm        立即数装载
    0x08-0x0F  MOV Rd, Rs         寄存器间传送
    0x10-0x17  LD  Rd, [addr]     从内存读
    0x18-0x1F  ST  Rs, [addr]     往内存写
    0x20-0x57  ADD/SUB/AND/OR/XOR/MUL/CMP Rd, Rs（7 种运算 × 8 目标寄存器）
    0x58-0x77  INC/DEC/SHL/SHR Ri（4 种单目 × 8 寄存器）
    0x78-0x7F  JMP/JZ/JNZ/JC/JNC/JN/JNN/JV [target]
    0x80-0x87  PUSH Ri                  压栈（SP-1 后写入）
    0x88-0x8F  POP Ri                   弹栈（读出后 SP+1）
    0x90-0x97  LDX Rd, [Rn]         读间接：Rd ← mem[Rn 的内容]
    0x98-0x9F  STX Rs, [Rn]         写间接：mem[Rn 的内容] ← Rs
    0xE0       CALL [target]       调用子程序（返回地址压栈）
    0xE1       RET                 返回（弹出返回地址装回 PC）
    0xF0       HALT
    0xF8       预留 DIV（对齐史实：8 位机无硬件除法）

编码约定：imm/addr/target 占满操作数字节；Rs 编码在操作数字节低 3 位。
"""

OP_HALT = 0xF0
OP_DIV_RESERVED = 0xF8        # 预留：将来扩展除法
OP_CALL, OP_RET = 0xE0, 0xE1  # 子程序：调用 / 返回

_LDI_BASE, _MOV_BASE, _LD_BASE, _ST_BASE = 0x00, 0x08, 0x10, 0x18
_ALU_BASE, _UN_BASE, _JMP_BASE = 0x20, 0x58, 0x78

_PUSH_BASE, _POP_BASE = 0x80, 0x88
_LDX_BASE, _STX_BASE = 0x90, 0x98

ALU_OPS = ("ADD", "SUB", "AND", "OR", "XOR", "MUL", "CMP")
UN_OPS = ("INC", "DEC", "SHL", "SHR")
JUMPS = ("JMP", "JZ", "JNZ", "JC", "JNC", "JN", "JNN", "JV")
MNEMONICS = ("LDI", "MOV", "LD", "ST", "LDX", "STX") + ALU_OPS + UN_OPS + JUMPS + ("PUSH", "POP", "CALL", "RET", "HALT")


# ---------- 汇编辅助：助记符 → 机器码（每条两字节） ----------

def I_LDI(rd, imm):
    return [_LDI_BASE | (rd & 7), imm & 0xFF]

def I_MOV(rd, rs):
    return [_MOV_BASE | (rd & 7), rs & 7]

def I_LD(rd, addr):
    return [_LD_BASE | (rd & 7), addr & 0xFF]

def I_ST(rs, addr):
    return [_ST_BASE | (rs & 7), addr & 0xFF]

def I_ALU(name, rd, rs):
    # 用加法而非按位或拼接：idx<<3 的高位可能与基址位重叠，或运算会踩踏
    return [_ALU_BASE + (ALU_OPS.index(name) << 3) + (rd & 7), rs & 7]

def I_UN(name, r):
    return [_UN_BASE + (UN_OPS.index(name) << 3) + (r & 7), 0]

def I_JMP(name, target):
    return [_JMP_BASE | JUMPS.index(name), target & 0xFF]

def I_CALL(target):
    return [OP_CALL, target & 0xFF]

def I_RET():
    return [OP_RET, 0]

def I_PUSH(rd):
    return [_PUSH_BASE | (rd & 7), 0]

def I_POP(rd):
    return [_POP_BASE | (rd & 7), 0]

def I_LDX(rd, rn):
    return [_LDX_BASE | (rd & 7), rn & 7]

def I_STX(rs, rn):
    return [_STX_BASE | (rs & 7), rn & 7]

def I_HALT():
    return [OP_HALT, 0]


# ---------- 译码：机器码 → 结构化字段 ----------

def decode(op, arg):
    """(操作码, 操作数字节) → (助记符, 寄存器, 其他字段)。

    其他字段的含义随类别变化：LDI=立即数，MOV=源寄存器，LD/ST=地址，
    ALU=源寄存器，单目=None，跳转=目标地址，HALT=None。
    非法操作码抛 ValueError。
    """
    if 0x00 <= op <= 0x07:
        return "LDI", op & 7, arg & 0xFF
    if 0x08 <= op <= 0x0F:
        return "MOV", op & 7, arg & 7
    if 0x10 <= op <= 0x17:
        return "LD", op & 7, arg & 0xFF
    if 0x18 <= op <= 0x1F:
        return "ST", op & 7, arg & 0xFF
    if _PUSH_BASE <= op <= _PUSH_BASE + 7:
        return "PUSH", op & 7, None
    if _POP_BASE <= op <= _POP_BASE + 7:
        return "POP", op & 7, None
    if _LDX_BASE <= op <= _LDX_BASE + 7:
        return "LDX", op & 7, arg & 7
    if _STX_BASE <= op <= _STX_BASE + 7:
        return "STX", op & 7, arg & 7
    if _ALU_BASE <= op <= _ALU_BASE + len(ALU_OPS) * 8 - 1:
        return ALU_OPS[(op - _ALU_BASE) >> 3], op & 7, arg & 7
    if _UN_BASE <= op <= _UN_BASE + len(UN_OPS) * 8 - 1:
        return UN_OPS[(op - _UN_BASE) >> 3], op & 7, None
    if _JMP_BASE <= op <= 0x7F:
        return JUMPS[op - _JMP_BASE], None, arg & 0xFF
    if op == OP_CALL:
        return "CALL", None, arg & 0xFF
    if op == OP_RET:
        return "RET", None, None
    if op == OP_HALT:
        return "HALT", None, None
    raise ValueError(f"非法操作码 0x{op:02X}")


def disasm(op, arg):
    """反汇编一行（调试/跟踪用）。"""
    name, reg, other = decode(op, arg)
    if name == "LDI":
        return f"LDI R{reg}, #{other}"
    if name == "MOV":
        return f"MOV R{reg}, R{other}"
    if name == "LD":
        return f"LD  R{reg}, [{other:#04x}]"
    if name == "ST":
        return f"ST  R{reg}, [{other:#04x}]"
    if name in ALU_OPS:
        return f"{name} R{reg}, R{other}"
    if name in UN_OPS:
        return f"{name} R{reg}"
    if name in JUMPS:
        return f"{name} {other:#04x}"
    if name == "CALL":
        return f"CALL {other:#04x}"
    if name == "RET":
        return "RET"
    if name == "PUSH":
        return f"PUSH R{reg}"
    if name == "POP":
        return f"POP R{reg}"
    if name == "LDX":
        return f"LDX R{reg}, [R{other}]"
    if name == "STX":
        return f"STX R{reg}, [R{other}]"
    return "HALT"
