# coding:utf-8
import time
import random
from typing import List, Dict
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from dealer.llm_futures_dealer import LLMFuturesDealer
from dealer.futures_provider import MainContractProvider
import pandas as pd
from datetime import datetime, timedelta
import logging
import pytz

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置北京时区
beijing_tz = pytz.timezone('Asia/Shanghai')

class LLMMultiFuturesStrategy(XtQuantTraderCallback):
    def __init__(self, path, session_id, account_id, futures_symbols, llm_client, trade_rules="", start_time=None, use_market_order=False, price_tolerance=0.2):
        self.path = path
        self.session_id = session_id
        self.account_id = account_id
        self.futures_symbols = futures_symbols.split(',')
        self.data_provider = MainContractProvider()
        self.use_market_order = use_market_order
        self.price_tolerance = price_tolerance

        self.xt_trader = None
        self.account = None
        self.last_processed_time = None

        # 使用北京时间
        current_time = datetime.now(beijing_tz)
        self.start_time = start_time or (current_time - timedelta(hours=1))
        if self.start_time.tzinfo is None:
            self.start_time = beijing_tz.localize(self.start_time)

        # 创建单个LLMFuturesDealer实例来处理所有合约
        self.dealer = LLMFuturesDealer(
            llm_client, 
            self.futures_symbols, 
            self.data_provider, 
            trade_rules,
            backtest_date=self.start_time.strftime('%Y-%m-%d')
        )

        logger.info(f"Strategy initialized with start time: {self.start_time} for symbols: {self.futures_symbols}")

    def start(self):
        logger.info("Starting LLMMultiFuturesStrategy")
        self.xt_trader = XtQuantTrader(self.path, self.session_id)
        
        # 创建资金账号对象，期货账号为FUTURE
        self.account = StockAccount(self.account_id, 'FUTURE')
        logger.info(f"Created account object for account ID: {self.account_id}")
        
        # 注册回调
        self.xt_trader.register_callback(self)
        logger.info("Registered callback")
        
        # 启动交易线程
        self.xt_trader.start()
        logger.info("Started trading thread")
        
        # 建立交易连接
        connect_result = self.xt_trader.connect()
        logger.info(f"Connection result: {connect_result}")
        if connect_result != 0:
            logger.error("Failed to establish trading connection")
            return False
        
        # 对交易回调进行订阅
        subscribe_result = self.xt_trader.subscribe(self.account)
        logger.info(f"Subscribe result: {subscribe_result}")
        if subscribe_result != 0:
            logger.error("Failed to subscribe to trading callbacks")
            return False
        
        # 订阅行情数据
        self.subscribe_market_data()
        
        logger.info("LLMMultiFuturesStrategy started successfully")
        return True

    def subscribe_market_data(self):
        """订阅实时行情数据"""
        start_time_str = self.start_time.strftime("%Y%m%d%H%M%S")
        logger.info(f"Attempting to subscribe to data from: {start_time_str}")
        
        for symbol in self.futures_symbols:
            try:
                xtdata.subscribe_quote(symbol, period='1m', start_time=start_time_str, callback=self.on_bar_data)
                logger.info(f"Subscribed to 1-minute bar data for {symbol} starting from {start_time_str}")
            except Exception as e:
                logger.error(f"Error subscribing to market data for {symbol}: {e}")

    def on_bar_data(self, data):
        """处理实时行情数据的回调函数"""
        bars = {}
        news = {}
        current_time = None
        
        for symbol, symbol_data in data.items():
            if symbol in self.futures_symbols:
                bar_data = symbol_data[0]
                logger.debug(f"Received raw bar data for {symbol}: {bar_data}")
                try:
                    current_time = pd.to_datetime(bar_data['time'], unit='ms', utc=True).tz_convert(beijing_tz)
                    
                    # 更新当前bar数据
                    new_bar_data = pd.Series({
                        'datetime': current_time,
                        'open': bar_data['open'],
                        'high': bar_data['high'],
                        'low': bar_data['low'],
                        'close': bar_data['close'],
                        'volume': bar_data['volume'],
                        'amount': bar_data['amount'],
                        'hold': bar_data['openInterest']
                    })
                    
                    bars[symbol] = new_bar_data
                    news[symbol] = self.get_latest_news(symbol)
                    
                except Exception as e:
                    logger.error(f"Error processing bar for {symbol}: {str(e)}")
                    logger.error(f"Problematic bar data: {bar_data}")
            else:
                logger.warning(f"Received data for unsubscribed symbol: {symbol}")

        if current_time and (self.last_processed_time is None or current_time.minute != self.last_processed_time.minute):
            logger.info(f"Processing new bar data for time: {current_time}")
            if current_time >= self.start_time:
                self.process_bars(bars, news)
            else:
                logger.info(f"Skipping bar data before start time: {current_time}")
            self.last_processed_time = current_time

    def process_bars(self, bars: Dict[str, pd.Series], news: Dict[str, str]):
        """处理多个合约的bar数据"""
        if not self.is_trading_time(bars[next(iter(bars))]['datetime']):
            logger.info(f"Not trading time: {bars[next(iter(bars))]['datetime']}")
            return

        logger.info(f"Processing bar data for {len(bars)} symbols")
        
        # 使用LLMFuturesDealer处理数据
        results = self.dealer.process_bars(bars, news)
        
        for symbol, result in results.items():
            trade_instruction, quantity, next_msg, trade_reason, trade_plan = result

            logger.info(f"LLM decision for {symbol}: {trade_instruction}, quantity: {quantity}")
            logger.info(f"Trade reason for {symbol}: {trade_reason}")
            logger.info(f"Trade plan for {symbol}: {trade_plan}")

            if trade_instruction != 'hold':
                self.execute_trade(symbol, trade_instruction, quantity, bars[symbol]['close'])

    def is_trading_time(self, current_time):
        # 实现交易时间判断逻辑
        # 这里需要根据具体的交易时间规则来实现
        # 例如：
        current_hour = current_time.hour
        current_minute = current_time.minute
        
        # 日盘交易时间：9:00-15:00
        if 9 <= current_hour < 15:
            return True
        
        # 夜盘交易时间：21:00-次日2:30
        if 21 <= current_hour <= 23:
            return True
        if 0 <= current_hour < 2:
            return True
        if current_hour == 2 and current_minute <= 30:
            return True
        
        return False

    def get_latest_news(self, symbol):
        news_df = self.data_provider.get_futures_news(symbol, page_num=0, page_size=1)
        if news_df is not None and not news_df.empty:
            return news_df.iloc[0]['summary']
        return ""

    def execute_trade(self, symbol, instruction, quantity, price):
        logger.info(f"尝试执行交易: 合约={symbol}, 指令={instruction}, 数量={quantity}, 价格={price}")

        try:
            order_price = price
            order_type = xtconstant.FIX_PRICE

            if self.use_market_order:
                order_type = xtconstant.MARKET_BEST
            else:
                if instruction in ['buy', 'cover']:
                    order_price = price * (1 + self.price_tolerance)
                elif instruction in ['sell', 'short']:
                    order_price = price * (1 - self.price_tolerance)

            if instruction == 'buy':
                order_id = self.xt_trader.order_stock(self.account, symbol, xtconstant.FUTURE_OPEN_LONG, 
                                                    quantity, order_type, order_price, 'LLM_strategy', 'LLM_buy')
            elif instruction == 'sell':
                order_id = self.xt_trader.order_stock(self.account, symbol, xtconstant.FUTURE_CLOSE_LONG_TODAY, 
                                                    quantity, order_type, order_price, 'LLM_strategy', 'LLM_sell')
            elif instruction == 'short':
                order_id = self.xt_trader.order_stock(self.account, symbol, xtconstant.FUTURE_OPEN_SHORT, 
                                                    quantity, order_type, order_price, 'LLM_strategy', 'LLM_short')
            elif instruction == 'cover':
                order_id = self.xt_trader.order_stock(self.account, symbol, xtconstant.FUTURE_CLOSE_SHORT_TODAY, 
                                                    quantity, order_type, order_price, 'LLM_strategy', 'LLM_cover')
            else:
                logger.warning(f"未知的交易指令: {instruction}")
                return

            logger.info(f"已发送订单: ID={order_id}, 合约={symbol}, 指令={instruction}, 数量={quantity}, 价格类型={order_type}, 价格={order_price}")

        except Exception as e:
            logger.error(f"执行交易时发生错误: {str(e)}", exc_info=True)

    # Implement other necessary methods (callbacks, etc.)

    def run_strategy(self):
        """运行策略"""
        logger.info("Strategy is now running. Waiting for market data...")
        self.xt_trader.run_forever()

if __name__ == "__main__":
    from core.config import get_key
    from core.llms.llm_factory import LLMFactory
    
    account_id = get_key('account_id')
    xuntou_path = get_key("xuntou_path")
    futures_symbols = get_key('futures_symbols')
    trade_rules = get_key('trade_rules', "")
    llm_api = get_key('llm_api', "MiniMaxClient")

    if not account_id or not xuntou_path or not futures_symbols:
        logger.error("Missing required configuration")
        exit(1)

    session_id = random.randint(100000, 999999)
    factory = LLMFactory()
    llm_client = factory.get_instance(llm_api)

    start_time = datetime.now(beijing_tz) - timedelta(hours=1)

    strategy = LLMMultiFuturesStrategy(xuntou_path, session_id, account_id, futures_symbols, llm_client, trade_rules, start_time)

    if strategy.start():
        strategy.run_strategy()
    else:
        logger.error("Failed to start strategy")