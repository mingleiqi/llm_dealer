#coding=utf-8
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from xtquant import xtdata
from dealer.llm_dealer import LLMDealer
from dealer.futures_provider import MainContractProvider
import pandas as pd
from datetime import datetime, timedelta

class LLMQMTFuturesStrategy(XtQuantTraderCallback):
    def __init__(self, path, session_id, account_id, symbol, llm_client):
        self.xt_trader = XtQuantTrader(path, session_id)
        self.account = StockAccount(account_id)
        self.symbol = symbol
        self.data_provider = MainContractProvider()
        self.llm_dealer = LLMDealer(llm_client, symbol, self.data_provider)
        self.long_position_today = 0
        self.long_position_history = 0
        self.short_position_today = 0
        self.short_position_history = 0
        self.last_trade_time = None
        self.last_msg = ""

    def start(self):
        self.xt_trader.register_callback(self)
        self.xt_trader.start()
        connect_result = self.xt_trader.connect()
        print(f"Connection result: {connect_result}")
        subscribe_result = self.xt_trader.subscribe(self.account)
        print(f"Subscribe result: {subscribe_result}")

    def on_disconnected(self):
        print("Connection lost")

    def on_stock_order(self, order):
        print(f"Order callback: {order.stock_code}, {order.order_status}, {order.order_sysid}")

    def on_stock_trade(self, trade):
        print(f"Trade callback: {trade.account_id}, {trade.stock_code}, {trade.order_id}")
        # Update positions based on the trade
        if trade.order_type == xtconstant.FUTURE_OPEN_LONG:
            self.long_position_today += trade.traded_volume
        elif trade.order_type == xtconstant.FUTURE_CLOSE_LONG_TODAY:
            self.long_position_today -= trade.traded_volume
        elif trade.order_type == xtconstant.FUTURE_CLOSE_LONG_HISTORY:
            self.long_position_history -= trade.traded_volume
        elif trade.order_type == xtconstant.FUTURE_OPEN_SHORT:
            self.short_position_today += trade.traded_volume
        elif trade.order_type == xtconstant.FUTURE_CLOSE_SHORT_TODAY:
            self.short_position_today -= trade.traded_volume
        elif trade.order_type == xtconstant.FUTURE_CLOSE_SHORT_HISTORY:
            self.short_position_history -= trade.traded_volume

    def on_order_error(self, order_error):
        print(f"Order error: {order_error.order_id}, {order_error.error_id}, {order_error.error_msg}")

    def on_cancel_error(self, cancel_error):
        print(f"Cancel error: {cancel_error.order_id}, {cancel_error.error_id}, {cancel_error.error_msg}")

    def on_order_stock_async_response(self, response):
        print(f"Async order response: {response.account_id}, {response.order_id}, {response.seq}")

    def on_account_status(self, status):
        print(f"Account status: {status.account_id}, {status.account_type}, {status.status}")

    def get_current_bar_data(self):
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=1)
        df = xtdata.get_local_data(self.symbol, start_time, end_time, period='1m')
        if df.empty:
            return None
        latest_bar = df.iloc[-1]
        return pd.Series({
            'datetime': pd.to_datetime(latest_bar.time),
            'open': latest_bar.open,
            'high': latest_bar.high,
            'low': latest_bar.low,
            'close': latest_bar.close,
            'volume': latest_bar.volume,
            'hold': latest_bar.position  # Assuming 'position' represents open interest
        })

    def get_latest_news(self):
        news_df = self.data_provider.get_futures_news(self.symbol, page_num=0, page_size=1)
        if news_df is not None and not news_df.empty:
            return news_df.iloc[0]['summary']
        return ""

    def execute_trade(self, instruction, quantity, price):
        if instruction == 'buy':
            order_id = self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_OPEN_LONG, 
                                                  quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_buy')
        elif instruction == 'sell':
            # Close long positions, prioritize closing today's positions
            today_quantity = min(quantity, self.long_position_today)
            if today_quantity > 0:
                self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_CLOSE_LONG_TODAY, 
                                           today_quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_sell_today')
            history_quantity = min(quantity - today_quantity, self.long_position_history)
            if history_quantity > 0:
                self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_CLOSE_LONG_HISTORY, 
                                           history_quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_sell_history')
        elif instruction == 'short':
            order_id = self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_OPEN_SHORT, 
                                                  quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_short')
        elif instruction == 'cover':
            # Close short positions, prioritize closing today's positions
            today_quantity = min(quantity, self.short_position_today)
            if today_quantity > 0:
                self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_CLOSE_SHORT_TODAY, 
                                           today_quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_cover_today')
            history_quantity = min(quantity - today_quantity, self.short_position_history)
            if history_quantity > 0:
                self.xt_trader.order_stock(self.account, self.symbol, xtconstant.FUTURE_CLOSE_SHORT_HISTORY, 
                                           history_quantity, xtconstant.FIX_PRICE, price, 'LLM_strategy', 'LLM_cover_history')
        else:
            print(f"Unknown instruction: {instruction}")

    def run_strategy(self):
        while True:
            current_time = datetime.now()
            
            if not self.is_trading_time(current_time):
                continue

            bar_data = self.get_current_bar_data()
            if bar_data is None:
                continue

            news = self.get_latest_news()

            trade_instruction, quantity, next_msg = self.llm_dealer.process_bar(bar_data, news)

            if trade_instruction != 'hold':
                self.execute_trade(trade_instruction, quantity, bar_data['close'])

            self.last_trade_time = current_time
            self.last_msg = next_msg

    def is_trading_time(self, current_time):
        # Implement logic to check if it's trading time
        # This is a simplified version, you should adjust it based on actual trading hours
        return (9 <= current_time.hour < 15) or (21 <= current_time.hour < 23)

if __name__ == "__main__":
    from core.llms.mini_max_client import MiniMaxClient
    path = r'D:\app\迅投\userdata'
    import random

    def generate_six_digit_random_number():
        return random.randint(100000, 999999)

    session_id = generate_six_digit_random_number()
    account_id = '101777'
    symbol = 'SC2307.INE'  # Example futures contract code
    llm_client = MiniMaxClient()  # You need to provide an actual LLM client here

    strategy = LLMQMTFuturesStrategy(path, session_id, account_id, symbol, llm_client)
    strategy.start()
    strategy.run_strategy()
    