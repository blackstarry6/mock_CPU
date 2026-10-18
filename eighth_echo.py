"""第八个程序：回声机——输入端口 0xFC 开通，I/O 全家福凑齐。

第一块"全双工"外设：ConsoleKeyboardRAM 同时钩住 read（0xFC 取键）和
write（0xFE 打字符）——输出三件套的镜像补全。设备冒充内存，CPU 依旧零知情。

约定：
  0xFC 读 = 取一个键（破坏性读取，如真实键盘数据寄存器；队列空返回 0 = 无键）
  0xFE 写 = 打印一个字符
机器无中断，等键靠轮询（CMP/JZ）——1970-80 年代键盘的真实工作方式。
键码存字符的 ASCII 值：字符 '0' 是 48，与"无键"哨兵 0 互不相扰。
驱动端预投喂按键（剧本式输入），确定性保留、结果可复现。

两幕演示：
  第一幕：回声——读 5 键各回显一次（验收 读口+写口+轮询+汇编器 四件套）
  第二幕：分支——按 '1' 回 A、按 '2' 回 B、按 'Q' 退出（输入驱动控制流）
"""
from ASM.asm import assemble
from CPU.cpu import CPU
from MEM.ram import RAM


class ConsoleKeyboardRAM(RAM):
    """键盘 + 控制台一体内存：读 0xFC 取键，写 0xFE 打字符。"""

    PORT_KEY, PORT_OUT = 0xFC, 0xFE

    def __init__(self):
        super().__init__()
        self.queue = []                   # 待读按键（驱动端投喂）
        self.out = []                     # 收集回显（自校验用）

    def type(self, text):                 # 驱动端：模拟敲键
        self.queue.extend(ord(c) & 0xFF for c in text)

    def read(self, addr):                 # ★ 钩读入口（与 ScreenRAM 的 write 钩镜像）
        if (addr & 0xFF) == self.PORT_KEY:
            return self.queue.pop(0) if self.queue else 0   # 空 = 0 = 无键
        return super().read(addr)

    def write(self, addr, value):         # ★ 钩写入口（ConsoleRAM 同款）
        super().write(addr, value)
        if (addr & 0xFF) == self.PORT_OUT:
            ch = chr(value & 0xFF)
            self.out.append(ch)
            print(ch, end="", flush=True)


def run(src, feed):
    """装一台机器（键盘+控制台内存），投喂剧本，跑到 HALT。"""
    ram = ConsoleKeyboardRAM()
    ram.load_program(assemble(src))
    cpu = CPU()
    cpu.ram = ram
    cpu.clk.attach(ram)
    ram.type(feed)
    n, halted = cpu.run(5000)
    print()
    return ram.out, halted, n


# ---- 第一幕：回声机（读 5 键各回显一次）----
ACT1 = """
        LDI R5, #0        ; "无键"哨兵
        LDI R4, #5        ; 回显 5 个键
next:   LD  R0, [0xFC]    ; 读键
        CMP R0, R5
        JZ  next          ; 无键 → 轮询等待
        ST  R0, [0xFE]    ; 有键 → 回显
        DEC R4
        JNZ next
        HALT
"""
print("第一幕：回声机（投喂 HELLO，期望回声 HELLO）")
out1, halted1, n1 = run(ACT1, "HELLO")
ok1 = (out1, halted1) == (list("HELLO"), True)
print(f"自校验：回声 = {''.join(out1)}，停机 = {halted1}（{n1} 拍）"
      f" —— {'通过 ✓' if ok1 else '失败 ✗'}\n")

# ---- 第二幕：分支菜单（'1'→A，'2'→B，'Q'→退出）----
ACT2 = """
        LDI R5, #0        ; 无键哨兵
        LDI R6, #0x51     ; 'Q' 退出键
        LDI R7, #0x31     ; '1'
        LDI R4, #0x32     ; '2'
menu:   LD  R0, [0xFC]
        CMP R0, R5
        JZ  menu          ; 等键
        CMP R0, R6
        JZ  done          ; Q → 退出
        CMP R0, R7
        JZ  one           ; 1 → 回 A
        CMP R0, R4
        JZ  two           ; 2 → 回 B
        JMP menu          ; 其他键忽略
one:    LDI R0, #0x41
        ST  R0, [0xFE]
        JMP menu
two:    LDI R0, #0x42
        ST  R0, [0xFE]
        JMP menu
done:   HALT
"""
print("第二幕：按键分支（投喂 12Q1，期望输出 AB 后退出——Q 后的 1 不再消费）")
out2, halted2, n2 = run(ACT2, "12Q1")
ok2 = (out2, halted2) == (list("AB"), True)
print(f"自校验：输出 = {''.join(out2)}，停机 = {halted2}（{n2} 拍）"
      f" —— {'通过 ✓' if ok2 else '失败 ✗'}")

print("\n总判定：" + ("两幕全部通过 ✓" if ok1 and ok2 else "存在失败 ✗"))
