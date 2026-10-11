; 汇编器示例：累加 1..5，结果存 0x80
; 用法：python -m ASM.asm ASM/example.asm
        LDI R0, #5
        LDI R1, #0
loop:
        ADD R1, R0
        DEC R0
        JNZ loop
        ST  R1, [0x80]
        HALT
