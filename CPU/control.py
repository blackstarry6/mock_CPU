"""控制器：助记符 → 控制信号（"微程序 ROM"的软件镜像）。

真实 CPU 的控制器是微程序 ROM 或 PLA 查表；本模块用一张查找表把
每条指令翻译成统一的一组控制信号，cpu.step() 作为通用执行引擎消费
它们——指令的全部"语义"浓缩在下表，一行就是一条指令。

控制信号的含义：
  a_from  A 操作数来源：IMM=操作数字节 / MEM=内存[操作数字节] /
          RF_SELF=操作码低 3 位指定的寄存器（读-改-写目的；ST 时为源寄存器）/
          RF_OTHER=操作数字节指定的寄存器
  alu_op  要做的 ALU 运算；None=数据直通（不经 ALU）
  b_from  B 操作数来源：ONE=常数 1 / RF_OTHER=寄存器 / None=不用
  dest    结果去向：RF=写回寄存器 / MEM=写内存 / None=丢弃（如 CMP）
  flags   是否更新标志位
  jump    跳转条件名；None=顺序执行（PC+2）；"HALT"=停机
"""
from collections import namedtuple

Signals = namedtuple("Signals", "a_from alu_op b_from dest flags jump")

MICROCODE = {
    # ---- 数据传送：直通，不动标志 ----
    "LDI": Signals("IMM",       None, None,      "RF",  False, None),
    "MOV": Signals("RF_OTHER",  None, None,      "RF",  False, None),
    "LD":  Signals("MEM",       None, None,      "RF",  False, None),
    "ST":  Signals("RF_SELF",   None, None,      "MEM", False, None),
    # ---- 算术逻辑：经 ALU，更新标志 ----
    "ADD": Signals("RF_SELF", "ADD", "RF_OTHER", "RF", True, None),
    "SUB": Signals("RF_SELF", "SUB", "RF_OTHER", "RF", True, None),
    "AND": Signals("RF_SELF", "AND", "RF_OTHER", "RF", True, None),
    "OR":  Signals("RF_SELF", "OR",  "RF_OTHER", "RF", True, None),
    "XOR": Signals("RF_SELF", "XOR", "RF_OTHER", "RF", True, None),
    "MUL": Signals("RF_SELF", "MUL", "RF_OTHER", "RF", True, None),
    "CMP": Signals("RF_SELF", "SUB", "RF_OTHER", None, True, None),  # 减法不写回
    # ---- 单目：派生指令（复用 ALU；INC/DEC 把常数 1 接到 B 端）----
    "INC": Signals("RF_SELF", "ADD", "ONE", "RF", True, None),
    "DEC": Signals("RF_SELF", "SUB", "ONE", "RF", True, None),
    "SHL": Signals("RF_SELF", "SHL", None, "RF", True, None),
    "SHR": Signals("RF_SELF", "SHR", None, "RF", True, None),
    # ---- 跳转：无运算无写回，读当前标志定去留 ----
    "JMP": Signals(None, None, None, None, False, "JMP"),
    "JZ":  Signals(None, None, None, None, False, "JZ"),
    "JNZ": Signals(None, None, None, None, False, "JNZ"),
    "JC":  Signals(None, None, None, None, False, "JC"),
    "JNC": Signals(None, None, None, None, False, "JNC"),
    "JN":  Signals(None, None, None, None, False, "JN"),
    "JNN": Signals(None, None, None, None, False, "JNN"),
    "JV":  Signals(None, None, None, None, False, "JV"),
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
