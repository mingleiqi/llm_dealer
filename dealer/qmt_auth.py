# coding:utf8


import csv
import os
import sys
from datetime import datetime
import time
import re
from threading import Timer

import pandas as pd
import numpy as np
import json
from xtquant import xtconstant
from xtquant import xtdata
# 依赖库
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback


def print_attr(obj):
    attr_dict = {}
    for attr in dir(obj):
        try:
            if attr[:2] == 'm_':
                attr_dict[attr] = getattr(obj, attr)
        except:
            pass
    return attr_dict


class MyXtQuantTraderCallback(XtQuantTraderCallback):
    def on_disconnected(self):
        """
        连接断开
        :return:
        """
        print(datetime.datetime.now(), '连接断开回调')

    def on_stock_order(self, order):
        """
        委托回报推送
        :param order: XtOrder对象
        :return:
        """
        # print(dir(order))
        if order.offset_flag == xtconstant.OFFSET_FLAG_OPEN:
            print(print_attr(order))
            print(order.order_id,  order.stock_code, '买入')
            print('===========')
            print(xt_trader.query_stock_orders(acc, ))

        # print('委托回调', print_attr(order))
        if order.offset_flag == xtconstant.OFFSET_FLAG_CLOSE:
            print(order.order_id,  order.stock_code, '卖出')

    def on_stock_trade(self, trade):
        """
        成交变动推送
        :param trade: XtTrade对象
        :return:
        """
        print('成交变动推送', trade.order_id, trade.offset_flag)
        # print('成交回调', print_attr(trade))

        xt_trader.order_stock_async(acc, '688001.SH', 23, 200, 11, 22.88, '测试下单', '测试下单')  # 正常



    def on_order_stock_async_response(self, response):
        """
        异步下单回报推送
        :param response: XtOrderResponse 对象
        :return:
        """

        print(f"异步委托回调 {response.order_remark}")



if __name__ == '__main__':

    from random import randint
    # xtdata.connect(port=58612)
    # print(xtdata.data_dir)
    xtdata.reconnect()

    path = r'I:\qmt投研\36576\迅投极速交易终端睿智融科版\userdata'
    stock_account_id = '2002360'  # 资金账号

    session_id = randint(100000, 999999)

    xt_trader = XtQuantTrader(path, session_id)
    xt_trader.set_relaxed_response_order_enabled(True)
    acc = StockAccount(stock_account_id, 'future')
    callback = MyXtQuantTraderCallback()
    xt_trader.register_callback(callback)
    xt_trader.start()
    connect_result = xt_trader.connect()
    print('建立交易连接，返回0表示连接成功', connect_result)
    subscribe_result = xt_trader.subscribe(acc)
    # print('对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功', subscribe_result)

    # todo 查询资金
    # assets = xt_trader.query_stock_asset(acc)
    # print(print_attr(assets))

    # todo 查询委托
    # for obj in xt_trader.query_stock_orders(acc):
    #     print(print_attr(obj))
    # todo 查询持仓
    # positions = xt_trader.query_stock_positions(acc)
    # positions = xt_trader.query_position_statistics(acc)
    # for obj in positions:
    #     print(print_attr(obj))
    # todo 下单
    # xt_trader.order_stock(acc, '159310.SZ', xtconstant.ETF_PURCHASE, 100, 5, -1, '测试下单', '测试下单')

    # xt_trader.order_stock(acc, '000628.SZ', 23, 200, xtconstant.MARKET_MINE_PRICE_FIRST, -1, '测试下单', '测试下单')


    # todo 下单返回订单编号
    # order_id =xt_trader.order_stock(acc, '600066.SH', 23, 200, 45,23.95,  '测试下单', '测试下单')
    # order_id = xt_trader.order_stock(acc, 'SM409.ZF', 23, 1, 5, -1, '测试下单', '测试下单')
    # todo 异步下单

    # xt_trader.order_stock_async(acc, '600066.SH', 23, 200, 11, 28, '测试下单', '测试下单') # 超单

    # xt_trader.order_stock_async(acc, '600475.SH', 23, 200, 11, 10.07, '测试下单', '测试下单') # 正常

    print('end')

    try:
        xt_trader.run_forever()

    except:
        pass






