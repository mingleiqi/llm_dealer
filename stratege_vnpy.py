

from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from dealer.llm_dealer import LLMDealer
from dealer.futures_provider import MainContractProvider
from datetime import datetime, timedelta
import pandas as pd
from core.llms.mini_max_client import MiniMaxClient

class LLMDealerStrategy(CtaTemplate):
    author = "Assistant"

    # 策略参数
    symbol = ""
    llm_client = None
    max_position = 5

    # 策略变量
    last_msg = ""
    current_date = None
    last_trade_date = None

    parameters = ["symbol", "max_position"]
    variables = ["last_msg", "current_date", "last_trade_date"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.bg = BarGenerator(self.on_bar)
        self.am = ArrayManager()
        
        self.llm_client = MiniMaxClient()
        # 初始化 LLMDealer 和 MainContractProvider
        self.data_provider = MainContractProvider()
        self.llm_dealer = LLMDealer(
            self.llm_client,
            self.symbol,
            self.data_provider,
            max_position=self.max_position
        )

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.load_bar(10)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        self.am.update_bar(bar)
        if not self.am.inited:
            return

        # 将 vnpy 的 BarData 转换为 LLMDealer 期望的格式
        llm_bar = {
            'datetime': bar.datetime,
            'open': bar.open_price,
            'high': bar.high_price,
            'low': bar.low_price,
            'close': bar.close_price,
            'volume': bar.volume,
            'hold': bar.open_interest
        }

        # 使用 LLMDealer 处理 bar 数据
        # 注意：我们不再传递 news 参数，因为 LLMDealer 会在内部处理新闻更新
        trade_instruction, quantity, next_msg = self.llm_dealer.process_bar(pd.Series(llm_bar))

        # 执行交易指令
        self.execute_trade(trade_instruction, quantity, bar)

        # 更新上一条消息
        self.last_msg = next_msg

        self.put_event()

    def execute_trade(self, trade_instruction: str, quantity: int, bar: BarData):
        """
        执行 LLMDealer 给出的交易指令
        """
        if trade_instruction == "buy":
            self.buy(bar.close_price, quantity)
        elif trade_instruction == "sell":
            self.sell(bar.close_price, quantity)
        elif trade_instruction == "short":
            self.short(bar.close_price, quantity)
        elif trade_instruction == "cover":
            self.cover(bar.close_price, quantity)

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass