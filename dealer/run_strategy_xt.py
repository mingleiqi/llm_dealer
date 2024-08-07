from xtquant.qmttools import run_strategy_file



def run_strategy():
    file_name = "./dealer/new_strategy.py"
    param = {
    'stock_code': 'sc2409.INE',  # 驱动handlebar的代码,
    'period': '1m',  # 策略执行周期 即主图周期
    'start_time': '2024-08-07 00:00:00',
    'end_time': '2024-08-09 23:59:59',
    'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
    'quote_mode': 'handlebar',  # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realti
    }
    run_strategy_file(file_name, param)


if __name__ == '__main__':
    run_strategy()