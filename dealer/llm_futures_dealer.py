import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import pytz
from dealer.futures_provider import MainContractProvider
from dealer.llm_dealer import LLMDealer

class LLMMultiContractDealer:
    def __init__(self, llm_client, symbols: List[str], data_provider: MainContractProvider, trade_rules: str = "",
                 max_daily_bars: int = 60, max_hourly_bars: int = 30, max_minute_bars: int = 240,
                 backtest_date: Optional[str] = None, compact_mode: bool = False,
                 max_position: int = 1):
        self.llm_client = llm_client
        self.symbols = symbols
        self.data_provider = data_provider
        self.trade_rules = trade_rules
        self.max_daily_bars = max_daily_bars
        self.max_hourly_bars = max_hourly_bars
        self.max_minute_bars = max_minute_bars
        self.backtest_date = backtest_date
        self.compact_mode = compact_mode
        self.max_position = max_position

        self.dealers = {symbol: LLMDealer(llm_client, symbol, data_provider, trade_rules,
                                          max_daily_bars, max_hourly_bars, max_minute_bars,
                                          backtest_date, compact_mode, max_position) 
                        for symbol in symbols}

        self.beijing_tz = pytz.timezone('Asia/Shanghai')
    def update_news(self):
        for symbol, dealer in self.dealers.items():
            dealer._update_news(datetime.now(self.beijing_tz))

    def get_total_profit(self) -> float:
        return sum(dealer.total_profit for dealer in self.dealers.values())

    def get_all_positions(self) -> Dict[str, int]:
        return {symbol: dealer.position_manager.get_current_position() for symbol, dealer in self.dealers.items()}

    def close_all_positions(self):
        for dealer in self.dealers.values():
            dealer._close_all_positions(dealer.data_provider.get_latest_price(dealer.symbol), datetime.now(self.beijing_tz))

    def run_daily_update(self):
        for dealer in self.dealers.values():
            dealer.run_daily_update()

    def get_performance_summary(self) -> str:
        summary = "性能摘要:\n"
        for symbol, dealer in self.dealers.items():
            profits = dealer.position_manager.calculate_profits(dealer.data_provider.get_latest_price(symbol))
            summary += f"{symbol}:\n"
            summary += f"  总盈亏: {profits['total_profit']:.2f}\n"
            summary += f"  实现盈亏: {profits['realized_profit']:.2f}\n"
            summary += f"  未实现盈亏: {profits['unrealized_profit']:.2f}\n"
            summary += f"  当前仓位: {dealer.position_manager.get_current_position()}\n\n"
        summary += f"总盈亏: {self.get_total_profit():.2f}\n"
        return summary

    def analyze_correlations(self) -> pd.DataFrame:
        # 分析不同期货合约之间的相关性
        prices = {}
        for symbol, dealer in self.dealers.items():
            prices[symbol] = dealer.today_minute_bars['close']
        df = pd.DataFrame(prices)
        return df.corr()

    def identify_arbitrage_opportunities(self) -> List[str]:
        # 识别潜在的套利机会
        corr = self.analyze_correlations()
        opportunities = []
        for i in range(len(corr.columns)):
            for j in range(i+1, len(corr.columns)):
                if abs(corr.iloc[i, j]) > 0.8:  # 高相关性阈值
                    opportunities.append(f"Potential arbitrage between {corr.columns[i]} and {corr.columns[j]}")
        return opportunities

    def rebalance_portfolio(self):
        # 根据各个期货的表现重新平衡投资组合
        total_profit = self.get_total_profit()
        if total_profit <= 0:
            return  # 如果总盈利为负或零,不进行重新平衡

        for symbol, dealer in self.dealers.items():
            dealer_profit = dealer.total_profit
            if dealer_profit < 0:
                # 对于亏损的期货,减少最大持仓
                dealer.max_position = max(1, dealer.max_position - 1)
            elif dealer_profit / total_profit > 0.3:  # 如果某个期货贡献了超过30%的利润
                # 增加表现好的期货的最大持仓
                dealer.max_position += 1

    def generate_trading_report(self, start_date: datetime, end_date: datetime) -> str:
        report = f"交易报告 ({start_date.date()} 到 {end_date.date()}):\n\n"
        for symbol, dealer in self.dealers.items():
            report += f"{symbol} 报告:\n"
            report += dealer.generate_trading_report(start_date, end_date)
            report += "\n\n"
        report += f"总体表现:\n"
        report += f"总盈亏: {self.get_total_profit():.2f}\n"
        report += f"当前持仓: {self.get_all_positions()}\n"
        return report