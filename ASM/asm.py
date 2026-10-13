"""迷你汇编器：汇编文本 → 机器码字节列表（两遍扫描）。

语法（刻意最小化）：
    标号       name:            可独占一行，也可与指令同行（l: DEC R0）
    注释       ; 到行尾
    寄存器     R0~R7（大小写不敏感）
    立即数     #5 / #0x1F / #0b101
    内存地址   [0x80] 或 [标号]
    跳转目标   标号名或数字
    伪指令     .org 0x80        其后内容放到该地址（中间补 0，只许前进）
               .db 1,2,"AB"     直接放数据/字符串（ASCII 展开；串内勿含逗号）
    指令       与 isa.MNEMONICS 一致的 24 条（大小写不敏感）

两遍扫描：第一遍定位（位置计数器 LC 数地址、建符号表），第二遍生成
（查表填跳转目标）。编码规则的单一事实源在 isa.py——本模块全部经
isa.I_* 编码，不重复实现任何编码。程序映像从地址 0 开始。
"""
import re

from CPU import isa


class AsmError(Exception):
    """汇编错误（消息含行号，在汇编期拦截，不等到上机）。"""


class _Stmt:
    """一条解析后的语句：标号 + 助记符 + 操作数字符串列表。"""
    __slots__ = ("no", "label", "mnemonic", "ops")

    def __init__(self, no, label, mnemonic, ops):
        self.no, self.label, self.mnemonic, self.ops = no, label, mnemonic, ops


# ---------- 指令签名表：助记符 → (各操作数形态, 编码器) ----------

_SIGS = {
    "LDI": (("reg", "imm"), isa.I_LDI),
    "MOV": (("reg", "reg"), isa.I_MOV),
    "LD":  (("reg", "addr"), isa.I_LD),
    "ST":  (("reg", "addr"), isa.I_ST),
}
_SIGS.update({name: (("reg", "reg"), lambda r, s, _n=name: isa.I_ALU(_n, r, s))
              for name in isa.ALU_OPS})
_SIGS.update({name: (("reg",), lambda r, _n=name: isa.I_UN(_n, r))
              for name in isa.UN_OPS})
_SIGS.update({name: (("target",), lambda t, _n=name: isa.I_JMP(_n, t))
              for name in isa.JUMPS})
_SIGS["CALL"] = (("target",), isa.I_CALL)
_SIGS["RET"] = ((), isa.I_RET)
_SIGS["HALT"] = ((), isa.I_HALT)

_LABEL_RE = re.compile(r"^([A-Za-z_]\w*)\s*:\s*(.*)$")
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")


# ---------- 解析 ----------

def _parse(source):
    """源文本 → 语句列表（剥注释、提标号、拆助记符与操作数）。"""
    stmts = []
    for no, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip()
        if not text:
            continue
        label = None
        m = _LABEL_RE.match(text)
        if m:
            label, text = m.group(1), m.group(2).strip()
        if not text:
            stmts.append(_Stmt(no, label, None, []))
            continue
        parts = text.split(None, 1)
        mnemonic = parts[0].upper()
        ops = [o.strip() for o in parts[1].split(",")] if len(parts) > 1 else []
        stmts.append(_Stmt(no, label, mnemonic, ops))
    return stmts


def _num(no, tok):
    try:
        return int(tok, 0)                     # 自动识别 0x / 0b / 十进制
    except ValueError:
        raise AsmError(f"第 {no} 行：非法数字 {tok!r}") from None


def _reg(no, tok):
    m = re.fullmatch(r"[Rr]([0-7])", tok)
    if not m:
        raise AsmError(f"第 {no} 行：非法寄存器 {tok!r}（应为 R0~R7）")
    return int(m.group(1))


def _db_bytes(no, item):
    """.db 的单项：带引号按字符串展开，否则按数字。"""
    if len(item) >= 2 and item[0] == '"' and item[-1] == '"':
        return [ord(c) & 0xFF for c in item[1:-1]]
    return [_num(no, item) & 0xFF]


# ---------- 第一遍：定位（建符号表） ----------

def _pass1(stmts):
    symbols = {}
    lc = 0
    for st in stmts:
        if st.label is not None:
            if st.label in symbols:
                raise AsmError(f"第 {st.no} 行：标号 {st.label!r} 重复定义")
            symbols[st.label] = lc             # 标号 = 此刻的 LC，本身占 0 字节
        if st.mnemonic is None:
            continue
        if st.mnemonic == ".ORG":
            if len(st.ops) != 1:
                raise AsmError(f"第 {st.no} 行：.org 恰需一个地址")
            addr = _num(st.no, st.ops[0])
            if addr < lc:
                raise AsmError(f"第 {st.no} 行：.org 只许前进（{addr} < {lc}）")
            lc = addr
        elif st.mnemonic == ".DB":
            for item in st.ops:
                lc += len(_db_bytes(st.no, item))
        elif st.mnemonic in _SIGS:
            kinds = _SIGS[st.mnemonic][0]
            if len(st.ops) != len(kinds):
                raise AsmError(f"第 {st.no} 行：{st.mnemonic} 恰需 "
                               f"{len(kinds)} 个操作数，得到 {len(st.ops)} 个")
            lc += 2                            # 统一双字节：步长恒为 2
        else:
            raise AsmError(f"第 {st.no} 行：未知助记符 {st.mnemonic!r}")
    return symbols


# ---------- 第二遍：生成（查表编码） ----------

def _operand(no, kind, tok, symbols):
    if kind == "reg":
        return _reg(no, tok)
    if kind == "imm":
        if not tok.startswith("#"):
            raise AsmError(f"第 {no} 行：立即数需要 # 前缀（如 #5），得到 {tok!r}")
        return _num(no, tok[1:])
    if kind == "addr":
        if not (tok.startswith("[") and tok.endswith("]")):
            raise AsmError(f"第 {no} 行：地址需要方括号（如 [0x80]），得到 {tok!r}")
        inner = tok[1:-1].strip()
        if _IDENT_RE.fullmatch(inner):         # [标号] 也允许
            if inner not in symbols:
                raise AsmError(f"第 {no} 行：未定义标号 {inner!r}")
            return symbols[inner]
        return _num(no, inner)
    # kind == "target"
    if _IDENT_RE.fullmatch(tok):
        if tok not in symbols:
            raise AsmError(f"第 {no} 行：未定义标号 {tok!r}")
        return symbols[tok]
    return _num(no, tok)


def _pass2(stmts, symbols):
    out = []
    for st in stmts:
        if st.mnemonic is None:
            continue
        if st.mnemonic == ".ORG":
            addr = _num(st.no, st.ops[0])
            out.extend([0] * (addr - len(out)))     # 前进补零
            continue
        if st.mnemonic == ".DB":
            for item in st.ops:
                out.extend(_db_bytes(st.no, item))
            continue
        kinds, enc = _SIGS[st.mnemonic]
        args = [_operand(st.no, k, t, symbols) for k, t in zip(kinds, st.ops)]
        out.extend(enc(*args))
    return out


def assemble(source):
    """汇编源文本 → 机器码字节列表（映像从地址 0 起）。"""
    stmts = _parse(source)
    return _pass2(stmts, _pass1(stmts))


def assemble_file(path):
    with open(path, encoding="utf-8") as f:
        return assemble(f.read())


if __name__ == "__main__":
    # CLI：python -m ASM.asm 源文件.asm [--run]
    #   默认：汇编并打印机器码 + 反汇编（只翻译，不执行）
    #   --run：翻译后直接上机执行（带指令跟踪），打印最终状态
    import sys

    from CPU.isa import disasm

    run = "--run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("用法：python -m ASM.asm 源文件.asm [--run]")
        sys.exit(2)

    code = assemble_file(args[0])

    if run:
        from CPU.cpu import CPU

        cpu = CPU(code)
        n, halted = cpu.run(trace=True)
        print(f"\n执行 {n} 条指令，停机={halted}")
        print(f"寄存器：{[cpu.rf.read(i) for i in range(8)]}")
        print(f"标志：  {cpu.flags()}")
        sys.exit(0)

    print(" 地址   机器码     反汇编")
    for i in range(0, len(code) - 1, 2):
        op, arg = code[i], code[i + 1]
        try:
            text = disasm(op, arg)
        except ValueError:
            text = "（数据/非法）"
        print(f"{i:#06x}:  {op:02X} {arg:02X}     {text}")
