; ============ dec_io：十进制 I/O 程序库（项目第一个库文件） ============
; 调用约定（与 tenth_acceptance 同款微 ABI）：
;   R0        参数/返回值，传参即消耗
;   R1-R4     草稿区，被调方自保存（序言 PUSH / 尾声 POP）
;   R5/R6/R7  全局常数 0/10/48（驱动开头设置，全员只读）
; 端口：0xFC 读键（空 = 0 哨兵，破坏性读取）；0xFE 写字符（13 = 换行）
; 拼接法：驱动文本在前（机器从地址 0 启动），本库在后：
;   assemble(driver + open("ASM/dec_io.asm").read())

; ---- div10（内部）：R0/10 -> R0=商, R2=余数(0..9)；用 R4 ----
; 例外子程序：R2 出余数，仅被 print_dec 调用，不守草稿自保存约
div10:
    LDI R4, #0              ; 商清零
d10_loop:
    CMP R0, R6              ; R0>=10? 本机 C=1 <=> 够减（借位取反）
    JC  d10_sub             ; 够减 -> 再减一轮
    MOV R2, R0              ; 不够减：余数 = 剩余
    MOV R0, R4              ; 返回商
    RET
d10_sub:
    SUB R0, R6
    INC R4
    JMP d10_loop

; ---- print_dec（公开）：R0 = 0..255 -> 0xFE 逐字符；R0 消耗 ----
; 反复除 10，余数 PUSH 进栈、POP 出来恰好逆序（栈的算法性用法）
print_dec:
    PUSH R2
    PUSH R3
    PUSH R4
    LDI R3, #0              ; 数字个数
pd_split:
    CALL div10
    ADD R2, R7              ; +48 -> ASCII
    PUSH R2                 ; * 低位先压栈
    INC R3
    CMP R0, R5              ; 商 == 0？
    JNZ pd_split
pd_pop:
    POP R0                  ; * 后进先出 = 高位先出
    ST  R0, [0xFE]
    DEC R3
    JNZ pd_pop
    POP R4
    POP R3
    POP R2
    RET

; ---- parse_dec（公开）：阻塞读键直到回车 CR(13)；R0 = 键入值 ----
; 每键实时回显（含回车）——真终端行为：屏幕上的输入是有人"还给你"的
parse_dec:
    PUSH R2
    PUSH R3
    LDI R3, #0              ; value = 0
prd_loop:
    LD  R0, [0xFC]          ; 读键（队列空 = 0 哨兵）
    CMP R0, R5
    JZ  prd_loop            ; 忙等（真机轮询；--play 模式设备会阻塞等输入）
    ST  R0, [0xFE]          ; * 回显
    LDI R2, #13
    CMP R0, R2
    JZ  prd_done            ; 回车 -> 收工
    SUB R0, R7              ; ASCII - 48 -> 数位
    MUL R3, R6              ; value *= 10
    ADD R3, R0              ; value += 数位（mod 256，超界回绕）
    JMP prd_loop
prd_done:
    MOV R0, R3
    POP R3
    POP R2
    RET

; ---- lfsr（公开）：R0 = 状态 -> R0 = 新状态（Galois，抽头 0xB8） ----
; 周期 255（0 是不动点，种子勿取 0）；要随机流则把状态存格循环调用
lfsr:
    PUSH R2
    PUSH R3
    LDI R2, #1
    AND R2, R0              ; 取 bit0
    SHR R0                  ; >> 1
    LDI R3, #0xB8
    CMP R2, R5              ; bit0 == 0？
    JZ  lfsr_save           ;   是 -> 只移位
    XOR R0, R3              ;   否 -> 异或抽头
lfsr_save:
    POP R3
    POP R2
    RET
