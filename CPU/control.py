"""控制器：助记符 → 控制信号（"微程序 ROM"的软件镜像）。

真实 CPU 的控制器是微程序 ROM 或 PLA 查表；本模块用一张查找表把
每条指令翻译成统一的一组控制信号，cpu.step() 作为通用执行引擎消费
它们——指令的全部"语义"浓缩在下表，一行就是一条指令。

控制信号的含义：
  a_from  A 操作数来源：IMM=操作数字节 / MEM=内存[操作数字节] /
          RF_SELF=操作码低 3 位指定的寄存器（读-改-写目的；ST 时为源寄存器）/
          RF_OTHER=操作数字节指定的寄存器 / POP=弹栈（取数即弹栈）/
          REG_IND=内存[指针寄存器]（操作数字节指定指针寄存器——寄存器间接读）
  alu_op  要做的 ALU 运算；None=数据直通（不经 ALU）
  b_from  B 操作数来源：ONE=常数 1 / RF_OTHER=寄存器 / None=不用
  dest    结果去向：RF=写回寄存器 / MEM=写内存 / PUSH=压栈（写即压栈）/
          MEM_IND=写内存[指针寄存器]（寄存器间接写）/ None=丢弃（如 CMP）
  flags   更新哪些标志位：True=四位置新 / False=不动 / "ZN"=只写 Z·N
          （INC/DEC 的"C 保持"——进位链中间可安全步进指针，
          对齐 x86 INC 保全 CF / 6502 INX 不碰 C 的设计）
  jump    PC 下一拍：None=顺序 +2 / 条件名 / "CALL"=压返回地址并跳 /
          "RET"=弹返回地址 / "HALT"=停机
  c_from  加法器/旋转器进位输入的 3 选 1：ZERO=接地（ADD）/ ONE=接电源
          （SUB 补码的 +1）/ FLAG=接 C 标志（ADC/SBB/ROL/ROR 的反馈线）/
          None=不关心
"""
from collections import namedtuple

# c_from 带默认值 None：既有微码行无需逐行补写（namedtuple 的默认值
# 只作用于最右侧字段），真正用进位输入的行显式给出
Signals = namedtuple("Signals", "a_from alu_op b_from dest flags jump c_from",
                     defaults=(None,))

MICROCODE = {
    # ---- 数据传送：直通，不动标志 ----
    "LDI": Signals("IMM",       None, None,      "RF",  False, None),
    "MOV": Signals("RF_OTHER",  None, None,      "RF",  False, None),
    "LD":  Signals("MEM",       None, None,      "RF",  False, None),
    "ST":  Signals("RF_SELF",   None, None,      "MEM", False, None),
    # ---- 算术逻辑：经 ALU，更新标志 ----
    # ADC 与 ADD 唯一差别是 c_from（SBB 与 SUB 同理）：带进位指令不是
    # 新电路，是同一加减法器换一个进位来源（0 / 1 / C 标志）
    "ADD": Signals("RF_SELF", "ADD", "RF_OTHER", "RF", True, None, "ZERO"),
    "ADC": Signals("RF_SELF", "ADD", "RF_OTHER", "RF", True, None, "FLAG"),
    "SUB": Signals("RF_SELF", "SUB", "RF_OTHER", "RF", True, None, "ONE"),
    "SBB": Signals("RF_SELF", "SUB", "RF_OTHER", "RF", True, None, "FLAG"),
    "AND": Signals("RF_SELF", "AND", "RF_OTHER", "RF", True, None),
    "OR":  Signals("RF_SELF", "OR",  "RF_OTHER", "RF", True, None),
    "XOR": Signals("RF_SELF", "XOR", "RF_OTHER", "RF", True, None),
    "MUL": Signals("RF_SELF", "MUL", "RF_OTHER", "RF", True, None),
    "CMP": Signals("RF_SELF", "SUB", "RF_OTHER", None, True, None, "ONE"),  # 减法不写回
    # ---- 单目：派生指令（复用 ALU；INC/DEC 把常数 1 接到 B 端）----
    # INC/DEC 只写 Z/N——C/V 保持是多精度循环的活路（指针步进不踩进位链）
    "INC": Signals("RF_SELF", "ADD", "ONE", "RF", "ZN", None, "ZERO"),
    "DEC": Signals("RF_SELF", "SUB", "ONE", "RF", "ZN", None, "ONE"),
    "SHL": Signals("RF_SELF", "SHL", None, "RF", True, None),
    "SHR": Signals("RF_SELF", "SHR", None, "RF", True, None),
    # ---- 位操作单目（ALU 早已实现，此处补 ISA 身份）----
    # NOT 无"转出的位"、C 对它无话可说——保链（同 INC/DEC，"ZN"）；
    # ROL/ROR 穿 C 旋转：cin 接 C（FLAG）、C 写回转出位——多字节移位链
    "NOT": Signals("RF_SELF", "NOT", None, "RF", "ZN", None),
    "ROL": Signals("RF_SELF", "ROL", None, "RF", True, None, "FLAG"),
    "ROR": Signals("RF_SELF", "ROR", None, "RF", True, None, "FLAG"),
    # ---- 跳转：无运算无写回，读当前标志定去留 ----
    "JMP": Signals(None, None, None, None, False, "JMP"),
    "JZ":  Signals(None, None, None, None, False, "JZ"),
    "JNZ": Signals(None, None, None, None, False, "JNZ"),
    "JC":  Signals(None, None, None, None, False, "JC"),
    "JNC": Signals(None, None, None, None, False, "JNC"),
    "JN":  Signals(None, None, None, None, False, "JN"),
    "JNN": Signals(None, None, None, None, False, "JNN"),
    "JV":  Signals(None, None, None, None, False, "JV"),
    # ---- 寄存器间接寻址：地址来自指针寄存器（自修改代码的硬件替代）----
    "LDX": Signals("REG_IND", None, None, "RF",      False, None),
    "STX": Signals("RF_SELF", None, None, "MEM_IND", False, None),
    # ---- 栈数据操作：PUSH/POP（保存/恢复现场，序言尾声的雏形）----
    "PUSH": Signals("RF_SELF", None, None, "PUSH", False, None),
    "POP":  Signals("POP",     None, None, "RF",   False, None),
    # ---- 子程序：CALL 压返回地址并跳，RET 弹回（硬件栈，6502 JSR/RTS 同构）----
    "CALL": Signals(None, None, None, None, False, "CALL"),
    "RET":  Signals(None, None, None, None, False, "RET"),
    # ---- 停机：把时钟关掉 ----
    "HALT": Signals(None, None, None, None, False, "HALT"),
}


def signals(name):
    """查"微程序表"。未知指令抛 ValueError。"""
    try:
        return MICROCODE[name]
    except KeyError:
        raise ValueError(f"未知指令 {name}") from None


def condition_met(cond, flags):
    """跳转条件判断（组合逻辑）：flags 为当前标志位字典。"""
    Z, N, C, V = flags["Z"], flags["N"], flags["C"], flags["V"]
    return {
        "JMP": True,
        "JZ": Z == 1, "JNZ": Z == 0,
        "JC": C == 1, "JNC": C == 0,
        "JN": N == 1, "JNN": N == 0,
        "JV": V == 1,
    }[cond]
