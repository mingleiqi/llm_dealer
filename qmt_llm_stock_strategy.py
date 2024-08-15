# coding:utf-8
import time
import datetime
from xtquant import xtdata
from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
from xtquant.xttype import StockAccount
from xtquant import xtconstant
from dealer.llm_stock_dealer import LLMStockDealer,StockDataProvider
import pandas as pd
from datetime import datetime, timedelta
import re
import logging
import pytz
from dateutil import parser


# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 设置北京时区
beijing_tz = pytz.timezone('Asia/Shanghai')

def interact():
    """执行后进入repl模式"""
    import code
    code.InteractiveConsole(locals=globals()).interact()

class LLMQMTStockStrategy(XtQuantTraderCallback):
    def __init__(self, path, session_id, account_id, portfolios, llm_client, trade_rules="", use_market_order=False, price_tolerance=0.2):
        self.path = path
        self.session_id = session_id
        self.account_id = account_id
        self.portfolios = portfolios
        self.llm_client = llm_client
        self.trade_rules = trade_rules
        self.use_market_order = use_market_order
        self.price_tolerance = price_tolerance
        
        self.xt_trader = None
        self.account = None
        self.data_provider = StockDataProvider(llm_client)
        self.dealer = None
        
        self.initialize_dealers()

    def initialize_dealers(self):
        self.dealer = LLMStockDealer(self.llm_client, self.data_provider, self.trade_rules)
                

    def start(self):
        logger.info("Starting LLMQMTStockStrategy")
        self.xt_trader = XtQuantTrader(self.path, self.session_id)
        
        # 创建资金账号对象，股票账号为STOCK
        self.account = StockAccount(self.account_id, 'STOCK')
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
        
        logger.info("LLMQMTStockStrategy started successfully")
        return True

    def subscribe_market_data(self):
        """订阅实时行情数据"""
        for stock in self.dealers.keys():
            try:
                xtdata.subscribe_quote(stock, period='1m', callback=self.on_bar_data)
                logger.info(f"Subscribed to 1-minute bar data for {stock}")
            except Exception as e:
                logger.error(f"Error subscribing to market data for {stock}: {e}")

    def on_bar_data(self, data):
        """处理实时行情数据的回调函数"""
        for stock, bar_data in data.items():
            if stock in self.dealers:
                try:
                    bar = pd.Series({
                        'datetime': self.parse_timestamp(bar_data[0]['time']),
                        'open': bar_data[0]['open'],
                        'high': bar_data[0]['high'],
                        'low': bar_data[0]['low'],
                        'close': bar_data[0]['close'],
                        'volume': bar_data[0]['volume'],
                        'amount': bar_data[0]['amount'],
                        'hold': bar_data[0]['openInterest']
                    })
                    
                    news = self.get_latest_news(stock)
                    trade_instruction, quantity, next_msg = self.dealers[stock].process_bar(bar, news)
                    
                    if trade_instruction != 'hold':
                        self.execute_trade(stock, trade_instruction, quantity, bar['close'])
                    
                except Exception as e:
                    logger.error(f"Error processing bar data for {stock}: {e}")
            else:
                logger.warning(f"Received data for unsubscribed stock: {stock}")

    def parse_timestamp(self, timestamp):
        """解析时间戳"""
        try:
            if isinstance(timestamp, (int, float)):
                return datetime.fromtimestamp(timestamp / 1000, tz=beijing_tz)
            elif isinstance(timestamp, str):
                return parser.parse(timestamp).astimezone(beijing_tz)
            elif isinstance(timestamp, pd.Timestamp):
                return timestamp.tz_localize(beijing_tz) if timestamp.tz is None else timestamp.tz_convert(beijing_tz)
            elif isinstance(timestamp, datetime):
                return timestamp.astimezone(beijing_tz) if timestamp.tzinfo else beijing_tz.localize(timestamp)
            else:
                raise ValueError(f"Unexpected timestamp type: {type(timestamp)}")
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp}: {str(e)}")
            return datetime.now(beijing_tz)

    def get_latest_news(self, stock):
        """获取最新新闻"""
        # 这里可以使用 self.data_provider 来获取最新新闻
        # 为简化示例，这里返回空字符串
        return ""

    def execute_trade(self, stock, instruction, quantity, price):
        logger.info(f"执行交易: {stock} {instruction} {quantity} @ {price}")
        
        order_price = price
        order_type = xtconstant.FIX_PRICE

        if self.use_market_order:
            order_type = xtconstant.LATEST_PRICE
        else:
            if instruction in ['buy', 'cover']:
                order_price = price * (1 + self.price_tolerance)
            elif instruction in ['sell', 'short']:
                order_price = price * (1 - self.price_tolerance)

        if instruction == 'buy':
            order_id = self.xt_trader.order_stock(self.account, stock, xtconstant.STOCK_BUY, 
                                                  quantity, order_type, order_price, 'LLM_strategy', 'LLM_buy')
        elif instruction == 'sell':
            order_id = self.xt_trader.order_stock(self.account, stock, xtconstant.STOCK_SELL, 
                                                  quantity, order_type, order_price, 'LLM_strategy', 'LLM_sell')
        else:
            logger.warning(f"未知的交易指令: {instruction}")
            return

        logger.info(f"已发送订单: ID={order_id}, 股票={stock}, 指令={instruction}, 数量={quantity}, 价格类型={order_type}, 价格={order_price}")

    def run_strategy(self):
        """运行策略"""
        logger.info("Strategy is now running. Waiting for market data...")
        self.xt_trader.run_forever()

    # 以下是 XtQuantTraderCallback 的方法实现
    def on_disconnected(self):
        logger.warning('连接断开回调')

    def on_stock_order(self, order):
        logger.info(f'委托回调 投资备注 {order.order_remark}')

    def on_stock_trade(self, trade):
        logger.info(f'成交回调 {trade.order_remark}, 委托方向 {trade.order_type} 成交价格 {trade.traded_price} 成交数量 {trade.traded_volume}')

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



if __name__ == "__main__":
    code_list  = xtdata.get_stock_list_in_sector("沪深A股")
    print(code_list)
    exit(0) 
    print("start")
    import random

    def generate_six_digit_random_number():
        return random.randint(100000, 999999)
    
    from core.config import get_key

    account_id = get_key('stock_account_id')
    if not account_id:
        print("没有设置stock_account_id")
        exit(1)

    xuntou_path = get_key("xuntou_path")
    if not xuntou_path:
        print("没有设置讯投APP的路径")
        exit(1)

    portfolios = get_key('portfolios')
    if not portfolios:
        print("没有设置投资组合")
        exit(1)

    session_id = generate_six_digit_random_number()

    trade_rules = get_key('stock_trade_rules')
    if not trade_rules:
        trade_rules = ""
    
    llm_api = get_key('llm_api')
    if not llm_api:
        llm_api = "MiniMaxClient"

    from core.llms.llm_factory import LLMFactory
    factory = LLMFactory()

    llm_client = factory.get_instance(llm_api) 

    strategy = LLMQMTStockStrategy(xuntou_path, session_id, account_id, portfolios, llm_client, trade_rules)

    if strategy.start():
        strategy.run_strategy()
    else:
        logger.error("Failed to start strategy")