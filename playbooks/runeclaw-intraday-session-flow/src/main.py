"""Entry point: python -m src.main

The platform injects the evaluation mode.  Historical runs replay the Nautilus
strategy in ``strategy.py``; live runs emit one decision per symbol and let the
managed follow-trade gate decide whether ``execution.py`` places orders.
"""
from getagent import runtime


def run() -> None:
    if runtime.is_historical():
        from . import main_backtest

        main_backtest.run()
        return
    if runtime.is_live():
        from . import main_live

        main_live.run()
        return
    raise ValueError(f"unsupported evaluation_mode={runtime.evaluation_mode!r}")


if __name__ == "__main__":
    run()
