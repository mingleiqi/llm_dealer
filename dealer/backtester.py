import logging
import time
import pandas as pd
from typing import List, Tuple, Union
from datetime import datetime, timedelta

from tqdm import tqdm
from dealer.futures_provider import MainContractProvider
from dealer.llm_dealer import LLMDealer

class Backtester:
    def __init__(self, symbol: str, start_date: str, end_date: str, llm_client, data_provider: MainContractProvider,
                 compact_mode=False,
                  max_position: int = 5):
        self.symbol = symbol
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d')
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d')
        self.llm_client = llm_client
        self.data_provider = data_provider
        self.max_position = max_position  # 添加 max_position 属性
        self.compact_mode = compact_mode
        
        self.trades: List[Tuple[str, int, float, datetime]] = []  # (action, quantity, price, timestamp)
        self.open_trades = 0
        self.close_trades = 0
        self.profit_loss = 0
        self.position = 0
        self.max_position = max_position 
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def run_backtest(self):
        total_days = (self.end_date - self.start_date).days + 1
        current_date = self.start_date

        with tqdm(total=total_days, desc="Overall Progress") as pbar:
            while current_date <= self.end_date:
                print(f"\nProcessing trading date: {current_date.strftime('%Y-%m-%d')}")
                
                dealer = LLMDealer(self.llm_client, self.symbol, self.data_provider, 
                                   backtest_date=current_date.strftime('%Y-%m-%d'),
                                   max_position=self.max_position)
                
                # Get data for the current trading day (including previous night session)
                trading_day_data = self.data_provider.get_bar_data(self.symbol, '1', current_date.strftime('%Y-%m-%d'))
                
                # Filter data to include only the current trading day and after the start_date
                filtered_data = trading_day_data[
                    (trading_day_data['trading_date'] == current_date) & 
                    (trading_day_data['datetime'] >= self.start_date)
                ]

                if filtered_data.empty:
                    print(f"No data available for trading date {current_date.strftime('%Y-%m-%d')}")
                else:
                    for i, (_, bar) in enumerate(filtered_data.iterrows(), 1):
                        trade_instruction, quantity, _ = dealer.process_bar(bar)
                        self._record_trade(trade_instruction, quantity, bar['close'], bar['datetime'])
                        
                        if i % 50 == 0:
                            print(f"Processed {i}/{len(filtered_data)} bars for trading date {current_date.strftime('%Y-%m-%d')}")

                current_date += timedelta(days=1)
                pbar.update(1)

        self._calculate_performance()
        print("\nBacktest completed!")



    def _record_trade(self, instruction: str, quantity: Union[int, str], price: float, timestamp: datetime):
        if instruction in ['buy', 'short']:
            actual_quantity = self.max_position - abs(self.position) if quantity == 'all' else min(int(quantity), self.max_position - abs(self.position))
            self.trades.append((instruction, actual_quantity, price, timestamp))
            self.open_trades += 1
            self.position += actual_quantity if instruction == 'buy' else -actual_quantity
        elif instruction in ['sell', 'cover']:
            actual_quantity = abs(self.position) if quantity == 'all' else min(int(quantity), abs(self.position))
            if self.position != 0:
                pl = (price - self.trades[-1][2]) * actual_quantity * (1 if self.position > 0 else -1)
                self.profit_loss += pl
                self.trades.append((instruction, actual_quantity, price, timestamp))
                self.close_trades += 1
                self.position += actual_quantity if instruction == 'cover' else -actual_quantity

    def _calculate_performance(self):
        print(f"回测结果 ({self.start_date.strftime('%Y-%m-%d')} 到 {self.end_date.strftime('%Y-%m-%d')}):")
        print(f"开仓次数: {self.open_trades}")
        print(f"平仓次数: {self.close_trades}")
        print(f"最终盈亏点数: {self.profit_loss:.2f}")
        
        if self.open_trades > 0:
            win_rate = (self.close_trades / self.open_trades) * 100
            print(f"胜率: {win_rate:.2f}%")
        
        if self.close_trades > 0:
            avg_profit = self.profit_loss / self.close_trades
            print(f"平均每笔交易盈亏: {avg_profit:.2f}")

    def get_trade_history(self) -> pd.DataFrame:
        return pd.DataFrame(self.trades, columns=['Action', 'Quantity', 'Price', 'Timestamp'])

# 使用示例
if __name__ == "__main__":
    symbol = "SC"
    start_date = "2023-01-01"
    end_date = "2023-12-31"
    
    data_provider = MainContractProvider()
    llm_client = None  # 替换为实际的 LLM 客户端
    
    backtester = Backtester(symbol, start_date, end_date, llm_client, data_provider)
    backtester.run_backtest()
    
    # 获取详细的交易历史
    trade_history = backtester.get_trade_history()
    print(trade_history)