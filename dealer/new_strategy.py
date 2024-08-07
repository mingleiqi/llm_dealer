# coding:utf-8

# 单策略独立进程是指每个策略拥有自己独立的进程，策略之间互不影响
# 在qmt内部使用单策略独立进程模式需要勾选上右侧的独立python进程
# 也在外部IDE使用该模式，此时需要把bin.x64/Lib/site-packages/xtquant复制到自己的python环境变量下


def init(C):
    return


def handlebar(C):
    print(C)
    return


# 使用外部IDE时也可以用以下方式初始化
# if __name__ == '__main__':
#     import sys
#     from xtquant.qmttools import run_strategy_file
#
#     # 参数定义方法一，如果使用方法二定义参数，run_strategy_file的param参数可不传
#     param = {
#         'stock_code': '000001.SZ',  # 驱动handlebar的代码,
#         'period': '1d',  # 策略执行周期 即主图周期
#         'start_time': '2023-01-01 00:00:00',
#         'end_time': '2023-06-01 23:59:59',
#         'trade_mode': 'backtest',  # simulation': 模拟, 'trading':实盘, 'backtest':回测
#         'quote_mode': 'history',  # handlebar模式，'realtime':仅实时行情（不调用历史行情的handlebar）,'history':仅历史行情, 'all'：所有，即history+realtime
#      }
#     # user_script = os.path.basename(__file__)  # 当前脚本路径，相对路径，绝对路径均可,此处为相对路径的方法
#     user_script = sys.argv[0] # 当前脚本路径，相对路径，绝对路径均可，此处为绝对路径的方法
#     run_strategy_file(user_script, param=param)




