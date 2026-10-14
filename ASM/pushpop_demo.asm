; PUSH/POP 演示：定义直译版阶乘（乘法在递归返回之后）
; 对照 fifth/fact 讨论里"算出 0"的失败版——两个 PUSH/POP 正是救命的差异
; 运行：python -m ASM.asm ASM/pushpop_demo.asm --run
        LDI R5, #0          ; 常数 0
        LDI R0, #5          ; n = 5
        LDI R1, #1          ; 累乘器
        CALL fact
        HALT                ; 期望 R1 = 120

fact:
        CMP  R0, R5         ; n == 0？
        JZ   done
        PUSH R0             ; ★ 存本层 n（递归会毁掉它）
        DEC  R0
        CALL fact           ; 先算 fact(n-1)
        POP  R0             ; ★ 取回本层 n
        MUL  R1, R0         ; 再乘——此刻 R0 是完璧归赵的本层 n
done:   RET
