"""时序元件的最底层：D 触发器与时钟（行为级建模）。

设计依据见 ../知识存档.md 第三节，核心纪律：
- 显式状态变量：q 是"当前状态"（对应导线上的电压），_next 是组合逻辑
  算出的下一状态。q 是整个模块里唯一的"记忆"。
- 边沿触发：d() 只是声明"下一个时钟沿写入此值"，q 在 tick() 之前绝不变。
- 写使能一次性消费：d() 置位使能，tick() 消费后清零——之后即使继续打拍
  也保持，直到再次调用 d()。
"""
class DFlipFlop:
    """一位 D 触发器（上边沿触发），q 恒为 0/1。"""

    def __init__(self, init=0):
        self.q = init & 1       # 当前状态（"记忆"本体）
        self._next = self.q     # 时钟沿将采样的 D 输入
        self._en = 0            # 写使能：d() 置位，tick() 消费

    def d(self, value):
        """数据输入：声明下一个时钟沿写入 value（D 是导线，后调覆盖先调）。"""
        self._next = 1 if value else 0
        self._en = 1

    def tick(self):
        """时钟上边沿：使能时采样 D，否则保持原值。"""
        if self._en:
            self.q = self._next
            self._en = 0


class Clock:
    """时钟：驱动一批时序元件统一 tick，落实"算完再统一提交"。

    各元件在组合阶段各自调 d() 搭好下一状态，Clock.tick() 到来时
    全体同时翻转——模拟同一根时钟线连到所有触发器的 CLK 引脚。
    """

    def __init__(self):
        self.elements = []
        self.cycles = 0

    def attach(self, *elements):
        """把时序元件挂到时钟线上。"""
        self.elements.extend(elements)
        return self

    def tick(self, n=1):
        """打 n 拍。"""
        for _ in range(n):
            for e in self.elements:
                e.tick()
            self.cycles += 1


if __name__ == "__main__":
    dff = DFlipFlop()
    print(f"初始          q = {dff.q}")
    dff.d(1)
    print(f"d(1) 后打拍前 q = {dff.q}（边沿未到，输出不变）")
    dff.tick()
    print(f"打拍后        q = {dff.q}")
    dff.tick()
    print(f"再打一拍      q = {dff.q}（使能已消费，保持）")
