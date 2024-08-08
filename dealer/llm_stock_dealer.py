





from .stock_data_provider import StockDataProvider

import logging
from typing import List, Dict, Tuple, Optional, Union
import pandas as pd
from datetime import datetime, timedelta
import pytz
import os
import json

class LLMStockDealer:
    def __init__(self, llm_client, portfolio: List[str], indices: List[str], 
                 initial_positions: Dict[str, Dict[str, int]], data_provider: StockDataProvider,
                 available_funds: float, max_position_percent: float = 0.2):
        self._setup_logging()
        self.llm_client = llm_client
        self.portfolio = portfolio
        self.indices = indices
        self.positions = initial_positions
        self.data_provider = data_provider
        self.available_funds = available_funds
        self.max_position_percent = max_position_percent

        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        self.current_date = datetime.now(self.beijing_tz).date()

        self.historical_summary = self._summarize_historical_data()
        self.trade_logs = self._load_trade_logs()
        self.trade_summary = self._summarize_trade_logs()
        self.market_news = self._get_market_news()

        self.last_news_update = datetime.now(self.beijing_tz)
        self.last_processed_time = None

    def _setup_logging(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        os.makedirs('./output', exist_ok=True)
        file_handler = logging.FileHandler(f'./output/stock_dealer_log_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _summarize_historical_data(self) -> str:
        if len(self.portfolio) > 10:
            return self.data_provider.summarize_historical_data(self.portfolio)
        else:
            # Implement logic to summarize historical data for each stock
            pass

    def _load_trade_logs(self) -> Dict[str, List[Dict]]:
        trade_logs = {}
        for symbol in self.portfolio + list(self.positions.keys()):
            log_file = f'./output/trade_log_{symbol}.json'
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    trade_logs[symbol] = json.load(f)
            else:
                trade_logs[symbol] = []
        return trade_logs

    def _summarize_trade_logs(self) -> str:
        # Implement logic to summarize trade logs
        pass

    def _get_market_news(self) -> str:
        news = self.data_provider.get_market_news()
        # Implement logic to summarize market news
        pass

    def _update_news(self):
        current_time = datetime.now(self.beijing_tz)
        if (current_time - self.last_news_update).total_seconds() > 1800:  # Update every 30 minutes
            self.market_news = self._get_market_news()
            stock_news = self.data_provider.get_news_updates(self.portfolio)
            # Process and summarize stock_news
            self.last_news_update = current_time

    def process_bar(self, bar_data: Dict[str, pd.Series]) -> Dict[str, Tuple[str, int, str]]:
        self._update_news()
        
        decisions = {}
        for symbol, bar in bar_data.items():
            if symbol in self.indices:
                continue  # Skip processing for indices

            llm_input = self._prepare_llm_input(symbol, bar)
            llm_response = self.llm_client.one_chat(llm_input)
            trade_instruction, quantity, next_msg, trade_reason, stop_loss, target_price = self._parse_llm_output(llm_response)
            
            self._execute_trade(symbol, trade_instruction, quantity, bar['close'], trade_reason, stop_loss, target_price)
            self._log_trade(symbol, trade_instruction, quantity, bar['close'], trade_reason, stop_loss, target_price)
            
            decisions[symbol] = (trade_instruction, quantity, next_msg)
        
        return decisions

    def _prepare_llm_input(self, symbol: str, bar: pd.Series) -> str:
        # Implement logic to prepare input for LLM, including historical data, 
        # current positions, recent trades, news, available funds, etc.
        pass

    def _parse_llm_output(self, llm_response: str) -> Tuple[str, int, str, str, float, float]:
        # Implement logic to parse LLM output
        # Return: trade_instruction, quantity, next_msg, trade_reason, stop_loss, target_price
        pass

    def _execute_trade(self, symbol: str, instruction: str, quantity: int, price: float, 
                       reason: str, stop_loss: float, target_price: float):
        max_shares = int(self.available_funds * self.max_position_percent / price)
        current_position = self.positions.get(symbol, {}).get('available', 0)

        if instruction == 'buy' and symbol in self.portfolio:
            max_buy = min(max_shares, max_shares - current_position)
            actual_quantity = min(quantity, max_buy)
            if actual_quantity > 0:
                cost = actual_quantity * price
                if cost <= self.available_funds:
                    self.positions.setdefault(symbol, {})['available'] = current_position + actual_quantity
                    self.available_funds -= cost
                    self.logger.info(f"Bought {actual_quantity} shares of {symbol} at {price}. Reason: {reason}")
                    self.logger.info(f"Stop loss: {stop_loss}, Target price: {target_price}")
                else:
                    self.logger.warning(f"Insufficient funds to buy {actual_quantity} shares of {symbol}")
        elif instruction == 'sell':
            available_position = self.positions.get(symbol, {}).get('available', 0)
            actual_quantity = min(quantity, available_position)
            if actual_quantity > 0:
                self.positions[symbol]['available'] -= actual_quantity
                self.available_funds += actual_quantity * price
                self.logger.info(f"Sold {actual_quantity} shares of {symbol} at {price}. Reason: {reason}")

    def _log_trade(self, symbol: str, instruction: str, quantity: int, price: float, 
                   reason: str, stop_loss: float, target_price: float):
        log_entry = {
            'timestamp': datetime.now(self.beijing_tz).isoformat(),
            'instruction': instruction,
            'quantity': quantity,
            'price': price,
            'reason': reason,
            'stop_loss': stop_loss,
            'target_price': target_price
        }
        self.trade_logs.setdefault(symbol, []).append(log_entry)
        
        log_file = f'./output/trade_log_{symbol}.json'
        with open(log_file, 'w') as f:
            json.dump(self.trade_logs[symbol], f, indent=2)

    def get_positions(self) -> Dict[str, Dict[str, int]]:
        return self.positions

    def update_positions(self, new_positions: Dict[str, Dict[str, int]]):
        self.positions.update(new_positions)

    def get_available_funds(self) -> float:
        return self.available_funds

    def update_available_funds(self, amount: float):
        self.available_funds = amount