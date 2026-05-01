"""
时序参数集中管理模块 v2.2.0
提供所有绘图相关的时间参数，支持运行时动态修改。
用户可调参数：
    key_interval_ms  - 所有按键的总间隔 (默认 100)
    wait_interval_ms - 特殊操作的额外等待 (默认 100)
    draw_ms          - 落笔绘制的单独间隔 (默认 100)
    press_hold_ms   - 按键实际保持时间 (默认 30)
"""


class TimingConfig:
    key_interval_ms: int = 100
    sv_key_interval_ms: int = 200
    wait_interval_ms: int = 100
    draw_ms: int = 100
    press_hold_ms: int = 30

    @classmethod
    def set_params(
        cls,
        key_interval=None,
        sv_key_interval=None,
        wait_interval=None,
        draw=None,
        press_hold=None,
    ):
        if key_interval is not None:
            cls.key_interval_ms = key_interval
        if sv_key_interval is not None:
            cls.sv_key_interval_ms = sv_key_interval
        if wait_interval is not None:
            cls.wait_interval_ms = wait_interval
        if draw is not None:
            cls.draw_ms = draw
        if press_hold is not None:
            cls.press_hold_ms = press_hold
