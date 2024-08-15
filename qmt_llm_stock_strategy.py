# coding:utf-8
import time
import datetime
from typing import List
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

class XtCodeTrans:
    def __init__(self):
        self.dict = {}
        code_list = xtdata.get_stock_list_in_sector("沪深A股")
        for code in code_list:
            key, value = code.split(".")  # 拆分代码
            self.dict[key] = value 

    def __len__(self):
        """返回字典中键值对的数量"""
        return len(self.dict)

    def __getitem__(self, key):
        """通过键获取对应的值"""
        return self.dict[key]

    def __iter__(self):
        """返回一个迭代器，用于遍历字典中的键"""
        return iter(self.dict)

    def keys(self):
        """返回字典中所有键的列表"""
        return list(self.dict.keys())

    def values(self):
        """返回字典中所有值的列表"""
        return list(self.dict.values())

    def items(self):
        """返回字典中所有键值对的列表"""
        return list(self.dict.items())


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
        self.dealer = LLMStockDealer(self.llm_client, self.data_provider, self.trade_rules)
        
        # 初始化讯投交易环境
        self.initialize_xt_trader()
        
        # 更新投资组合
        self.update_portfolio(self.portfolios)
        
        # 同步账户信息
        self.sync_with_account()

    def initialize_xt_trader(self):
        self.xt_trader = XtQuantTrader(self.path, self.session_id)
        self.account = StockAccount(self.account_id, 'STOCK')

    def sync_with_account(self):
        """
        与账户同步持仓和资金信息
        """
        # 同步资金信息
        asset = self.xt_trader.query_stock_asset(self.account)
        if asset:
            self.dealer.update_cash(asset.cash)

        # 同步持仓信息
        positions = self.xt_trader.query_stock_positions(self.account)
        if positions:
            new_positions = []
            for pos in positions:
                new_position = {
                    "symbol": pos.stock_code,
                    "entry_price": pos.avg_price,
                    "quantity": pos.volume,
                    "entry_time": datetime.now().isoformat(),  # 使用当前时间，因为我们没有开仓时间的信息
                    "position_type": self.dealer.portfolio.get_stock(pos.stock_code)['type'] if pos.stock_code in self.dealer.portfolio.stocks else 'medium_term',
                    "available_quantity": pos.can_use_volume
                }
                new_positions.append(new_position)
            self.dealer.update_positions(new_positions)

    def update_portfolio(self, portfolios):
        """
        更新投资组合
        """
        self.dealer.update_portfolio(portfolios)
        logger.info(f"Updated portfolio: {portfolios}")

    def update_portfolio_from_setting(self, new_stocks: List[str]):
        """
        从设置文件更新投资组合
        """
        self.dealer.update_portfolio(new_stocks)
        self.sync_with_account()

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
        # 获取投资组合和当前持仓的股票集合
        stocks_to_subscribe = set(self.dealer.portfolio.get_all_stocks().keys())  # 投资组合
        
        # 添加当前持仓的股票，并过滤重复
        for position in self.dealer.positions:
            if not position.is_closed():  # 只添加未平仓的持仓
                stocks_to_subscribe.add(position.symbol)

        for stock in stocks_to_subscribe:
            try:
                xtdata.subscribe_quote(stock, period='1m', callback=self.on_bar_data)
                logger.info(f"Subscribed to 1-minute bar data for {stock}")
            except Exception as e:
                logger.error(f"Error subscribing to market data for {stock}: {e}")

        logger.info(f"Total subscribed stocks: {len(stocks_to_subscribe)}")

    def on_bar_data(self, data):
        """处理实时行情数据的回调函数"""
        bars = {}
        news = {}
        
        for stock, bar_data in data.items():
            if stock in self.dealer.portfolio.get_all_stocks():
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
                    bars[stock] = bar
                    
                    # 获取该股票的最新新闻
                    news[stock] = self.get_latest_news(stock)
                    
                except Exception as e:
                    logger.error(f"Error processing bar data for {stock}: {e}")
            else:
                logger.warning(f"Received data for unsubscribed stock: {stock}")
        
        if bars:
            try:
                # 处理所有收到的bar数据
                results = self.dealer.process_bar(bars, news)
                
                # 执行交易指令
                for stock, (trade_instruction, quantity, next_msg) in results.items():
                    if trade_instruction != 'hold':
                        self.execute_trade(stock, trade_instruction, quantity, bars[stock]['close'])
                    
            except Exception as e:
                logger.error(f"Error in batch processing of bar data: {e}")

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

    def get_latest_news(self, symbol: str, num: int = 5) -> str:
        """
        获取指定股票的最新新闻。

        参数:
        symbol (str): 股票代码
        num (int): 需要获取的新闻数量，默认为5条

        返回:
        str: 包含最新新闻的字符串
        """
        try:
            # 使用 get_one_stock_news 方法获取最新新闻
            news_list = self.data_provider.get_one_stock_news(symbol, num=num)
            
            if not news_list:
                return f"没有找到股票 {symbol} 的最新新闻。"

            # 格式化新闻信息
            formatted_news = []
            for news in news_list:
                formatted_news.append(
                    f"标题: {news['title']}\n"
                    f"内容: {news['content']}\n"
                    f"时间: {news['datetime']}\n"
                    f"链接: {news['url']}\n"
                    "----------------------"
                )

            return "\n".join(formatted_news)

        except Exception as e:
            return f"获取股票 {symbol} 的新闻时发生错误: {str(e)}"

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
        
        # 更新可用资金
        asset = self.xt_trader.query_stock_asset(self.account)
        if asset is not None:
            self.dealer.update_cash(asset.cash)
        else:
            logger.warning("Failed to update available cash: Unable to query asset information")

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
    import random

    xt_trans = XtCodeTrans()
    
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
    if portfolios:
        split_list = portfolios.split(",")
        code_list = [xt_trans[code] for code in split_list]
    else:
        code_list = []
    
    split_list = portfolios.split(",")
    code_list=[ xt_trans[code] for code in split_list ]
    
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

    strategy = LLMQMTStockStrategy(xuntou_path, session_id, account_id, code_list, llm_client, trade_rules)

    if strategy.start():
        strategy.run_strategy()
    else:
        logger.error("Failed to start strategy")