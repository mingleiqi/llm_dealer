# coding:utf-8
import time
import datetime
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from dealer.llm_dealer import LLMDealer
from dealer.futures_provider import MainContractProvider
import pandas as pd
from datetime import datetime, timedelta
import re
import logging
import pytz

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置北京时区
beijing_tz = pytz.timezone('Asia/Shanghai')


# coding:utf-8
import time
import datetime
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from dealer.llm_dealer import LLMDealer
from dealer.futures_provider import MainContractProvider
import pandas as pd
from datetime import datetime, timedelta
import re
import logging
import pytz

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置北京时区
beijing_tz = pytz.timezone('Asia/Shanghai')

class LLMQMTFuturesStrategy(XtQuantTraderCallback):
    def __init__(self, path, session_id, account_id, symbol, llm_client, start_time=None):
        self.path = path
        self.session_id = session_id
        self.account_id = account_id
        self.symbol = symbol
        match = re.match(r"([a-zA-Z]+)\d{4}\.[A-Z]+", symbol)
        self.symbol_name = match.group(1).upper() if match else symbol
        self.data_provider = MainContractProvider()
        self.llm_dealer = LLMDealer(llm_client, self.symbol_name, self.data_provider)
        self.long_position_today = 0
        self.long_position_history = 0
        self.short_position_today = 0
        self.short_position_history = 0
        self.last_trade_time = None
        self.last_msg = ""
        self.xt_trader = None
        self.account = None
        self.last_processed_minute = None
        self.last_processed_time = None
        self.current_bar_data = None
        
        # 使用北京时间
        current_time = datetime.now(beijing_tz)
        self.start_time = start_time or (current_time - timedelta(hours=1))
        if self.start_time.tzinfo is None:
            self.start_time = beijing_tz.localize(self.start_time)
        
        logger.info(f"Strategy initialized with start time: {self.start_time}")

    def start(self):
        logger.info("Starting LLMQMTFuturesStrategy")
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
        
        # 建立交易连接，返回0表示连接成功
        connect_result = self.xt_trader.connect()
        logger.info(f"Connection result: {connect_result}")
        if connect_result != 0:
            logger.error("Failed to establish trading connection")
            return False
        
        # 对交易回调进行订阅，订阅后可以收到交易主推，返回0表示订阅成功
        subscribe_result = self.xt_trader.subscribe(self.account)
        logger.info(f"Subscribe result: {subscribe_result}")
        if subscribe_result != 0:
            logger.error("Failed to subscribe to trading callbacks")
            return False
        
        # 订阅行情数据
        self.subscribe_market_data()
        
        logger.info("LLMQMTFuturesStrategy started successfully")
        return True

    def subscribe_market_data(self):
        """订阅实时行情数据"""
        start_time_str = self.start_time.strftime("%Y%m%d%H%M%S")
        logger.info(f"Attempting to subscribe to data from: {start_time_str}")
        
        try:
            xtdata.subscribe_quote(self.symbol, period='1m', start_time=start_time_str, callback=self.on_bar_data)
            logger.info(f"Subscribed to 1-minute bar data for {self.symbol} starting from {start_time_str}")
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}")

    def on_bar_data(self, data):
        """处理实时行情数据的回调函数"""
        if self.symbol in data:
            bar_data = data[self.symbol][0]
            logger.debug(f"Received raw bar data: {bar_data}")
            try:
                current_time = self.parse_timestamp(bar_data['time'])
                
                # 更新当前bar数据
                self.current_bar_data = pd.Series({
                    'datetime': current_time,
                    'open': bar_data['open'],
                    'high': bar_data['high'],
                    'low': bar_data['low'],
                    'close': bar_data['close'],
                    'volume': bar_data['volume'],
                    'amount': bar_data['amount'],
                    'hold': bar_data['openInterest']
                })

                # 只在新的一分钟开始时处理数据
                if self.last_processed_time is None or current_time.minute != self.last_processed_time.minute:
                    logger.info(f"Processing new bar data for time: {current_time}")
                    if current_time >= self.start_time:
                        self.process_bar(self.current_bar_data)
                        self.last_processed_time = current_time
                    else:
                        logger.info(f"Skipping bar data before start time: {current_time}")
                else:
                    logger.debug(f"Updating current bar data for time: {current_time}")
            except Exception as e:
                logger.error(f"Error processing bar: {str(e)}")
                logger.error(f"Problematic bar data: {bar_data}")
        else:
            logger.warning(f"Received data does not contain information for {self.symbol}")

    def parse_timestamp(self, timestamp):
        """解析时间戳"""
        logger.debug(f"Attempting to parse timestamp: {timestamp}")
        try:
            # 尝试多种可能的时间戳格式
            if isinstance(timestamp, (int, float)):
                # 如果时间戳是以毫秒为单位
                if timestamp > 1e12:
                    # 检查时间戳是否超出合理范围（2262年之后）
                    if timestamp > 9999999999999:
                        logger.warning(f"Abnormally large timestamp detected: {timestamp}")
                        # 尝试将其解释为纳秒级时间戳
                        try:
                            return pd.Timestamp(timestamp, unit='ns').tz_localize(beijing_tz)
                        except Exception:
                            logger.error(f"Failed to parse abnormally large timestamp: {timestamp}")
                            return datetime.now(beijing_tz)
                    return datetime.fromtimestamp(timestamp / 1000, tz=beijing_tz)
                # 如果时间戳是以秒为单位
                else:
                    return datetime.fromtimestamp(timestamp, tz=beijing_tz)
            elif isinstance(timestamp, str):
                # 尝试使用dateutil解析字符串格式的时间戳
                return parser.parse(timestamp).astimezone(beijing_tz)
            elif isinstance(timestamp, pd.Timestamp):
                return timestamp.tz_localize(beijing_tz) if timestamp.tz is None else timestamp.tz_convert(beijing_tz)
            elif isinstance(timestamp, datetime):
                return timestamp.astimezone(beijing_tz) if timestamp.tzinfo else beijing_tz.localize(timestamp)
            else:
                raise ValueError(f"Unexpected timestamp type: {type(timestamp)}")
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp}: {str(e)}")
            # 如果所有方法都失败，返回当前时间作为后备选项
            logger.warning("Using current time as fallback")
            return datetime.now(beijing_tz)

    def is_new_minute(self, current_time):
        """检查是否是新的一分钟"""
        if self.last_processed_minute is None or current_time.minute != self.last_processed_minute.minute:
            self.last_processed_minute = current_time
            return True
        return False


    def process_bar(self, bar_data):
        """处理单个 bar 的数据"""
        if not self.is_trading_time(bar_data['datetime']):
            logger.info(f"Not trading time: {bar_data['datetime']}")
            return

        logger.info(f"Processing bar data: {bar_data}")
        news = self.get_latest_news()
        trade_instruction, quantity, next_msg = self.llm_dealer.process_bar(bar_data, news)

        logger.info(f"LLM decision: {trade_instruction}, quantity: {quantity}")

        if trade_instruction != 'hold':
            self.execute_trade(trade_instruction, quantity, bar_data['close'])

        self.last_trade_time = bar_data['datetime']
        self.last_msg = next_msg

    def is_trading_time(self, current_time):
        # 调整为考虑日期的版本
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

    # Callback methods
    def on_disconnected(self):
        logger.warning('连接断开回调')

    def on_stock_order(self, order):
        logger.info(f'委托回调 投资备注 {order.order_remark}')

    def on_stock_trade(self, trade):
        logger.info(f'成交回调 {trade.order_remark}, 委托方向(48买 49卖) {trade.offset_flag} 成交价格 {trade.traded_price} 成交数量 {trade.traded_volume}')
        self.update_positions(trade)

    def on_order_error(self, order_error):
        logger.error(f"委托报错回调 {order_error.order_remark} {order_error.error_msg}")

    def on_cancel_error(self, cancel_error):
        logger.error(f"撤单错误 {cancel_error}")

    def on_order_stock_async_response(self, response):
        logger.info(f"异步委托回调 投资备注: {response.order_remark}")

    def on_cancel_order_stock_async_response(self, response):
        logger.info(f"异步撤单回调 {response}")

    def on_account_status(self, status):
        logger.info(f"账户状态更新: {status}")

    def update_positions(self, trade):
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
        logger.info(f"Updated positions: Long Today {self.long_position_today}, Long History {self.long_position_history}, Short Today {self.short_position_today}, Short History {self.short_position_history}")

    def get_latest_news(self):
        news_df = self.data_provider.get_futures_news(self.symbol, page_num=0, page_size=1)
        if news_df is not None and not news_df.empty:
            return news_df.iloc[0]['summary']
        return ""

    def execute_trade(self, instruction, quantity, price):
        logger.info(f"Executing trade: {instruction}, quantity: {quantity}, price: {price}")
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
            logger.warning(f"Unknown instruction: {instruction}")

    def run_strategy(self):
        """运行策略"""
        logger.info("Strategy is now running. Waiting for market data...")
        self.xt_trader.run_forever()


if __name__ == "__main__":
    from core.llms.mini_max_client import MiniMaxClient
    path = r'D:\app\迅投\userdata'
    import random

    def generate_six_digit_random_number():
        return random.randint(100000, 999999)

    from core.config import get_key
    account_id=get_key('account_id')
    if not account_id:
        exit(1)
    symbol = get_key('symbol')
    if not symbol:
        symbol = 'sc2409.INE'
    session_id = generate_six_digit_random_number()
    account_id = account_id
      # Example futures contract code
    llm_client = MiniMaxClient()  # You need to provide an actual LLM client here
    
    # 设置起始时间为当前北京时间前1小时
    start_time = datetime.now(beijing_tz) - timedelta(hours=1)

    strategy = LLMQMTFuturesStrategy(path, session_id, account_id, symbol, llm_client, start_time)
    if strategy.start():
        strategy.run_strategy()
    else:
        logger.error("Failed to start strategy")