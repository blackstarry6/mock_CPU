; 子程序演示：递归求和 1..n（硬件栈版）
; 运行：python -m ASM.asm ASM/sub_demo.asm --run
        LDI R0, #10         ; n = 10
        LDI R1, #0          ; 结果累加器
        LDI R5, #0          ; 常数 0
        CALL sum            ; R1 = 1+2+...+10 = 55
        ST  R1, [0x80]      ; 结果存入内存
        HALT

sum:                        ; sum(n)：下降前先累加，n==0 直达 RET
        CMP R0, R5
        JZ  done
        ADD R1, R0
        DEC R0
        CALL sum            ; 递归：每层返回地址自动压栈
done:
        RET                 ; 逐层弹栈回家
