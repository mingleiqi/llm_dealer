





import re
from .stock_data_provider import StockDataProvider

import json
import os
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Tuple, Literal, Optional, Union
import logging


class StockPosition:
    def __init__(self, symbol: str, entry_price: float, quantity: int, entry_time: datetime, position_type: str):
        self.symbol = symbol
        self.entry_price = entry_price
        self.total_quantity = quantity
        self.available_quantity = 0
        self.today_quantity = quantity
        self.entry_time = entry_time
        self.position_type = position_type  # 'short_term', 'medium_term', 'long_term'
        self.exit_price = None
        self.exit_time = None

    def update_available_quantity(self):
        """在每个交易日开始时调用此方法"""
        self.available_quantity += self.today_quantity
        self.today_quantity = 0

    def close_position(self, exit_price: float, exit_time: datetime, quantity: int):
        if quantity > self.available_quantity:
            raise ValueError(f"Cannot close more than available quantity. Available: {self.available_quantity}, Requested: {quantity}")
        
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.available_quantity -= quantity
        self.total_quantity -= quantity

        if self.total_quantity == 0:
            return None  # Position fully closed
        elif self.total_quantity > 0:
            return self  # Position partially closed
        else:
            raise ValueError("Total quantity became negative after closing position")

    def calculate_profit(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.total_quantity

    def is_closed(self) -> bool:
        return self.total_quantity == 0

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "total_quantity": self.total_quantity,
            "available_quantity": self.available_quantity,
            "today_quantity": self.today_quantity,
            "entry_time": self.entry_time.isoformat(),
            "position_type": self.position_type,
            "exit_price": self.exit_price,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None
        }

    @classmethod
    def from_dict(cls, data):
        position = cls(
            data['symbol'],
            data['entry_price'],
            data['total_quantity'],
            datetime.fromisoformat(data['entry_time']),
            data['position_type']
        )
        position.available_quantity = data['available_quantity']
        position.today_quantity = data['today_quantity']
        if data['exit_price']:
            position.exit_price = data['exit_price']
            position.exit_time = datetime.fromisoformat(data['exit_time'])
        return position

class Portfolio:
    def __init__(self):
        self.stocks: Dict[str, Dict] = {}

    def update_portfolio(self, new_stocks: List[str]):
        """
        更新整个投资组合
        """
        self.stocks.clear()
        for symbol in new_stocks:
            self.add_stock(symbol)

    def add_stock(self, symbol: str, stock_type: str = "medium_term", target_price: Optional[float] = None, stop_loss: Optional[float] = None):
        self.stocks[symbol] = {
            "type": stock_type,
            "target_price": target_price,
            "stop_loss": stop_loss
        }

    def remove_stock(self, symbol: str):
        if symbol in self.stocks:
            del self.stocks[symbol]

    def get_stock(self, symbol: str) -> Optional[Dict]:
        return self.stocks.get(symbol)

    def get_all_stocks(self) -> Dict[str, Dict]:
        return self.stocks

    def update_stock(self, symbol: str, **kwargs):
        if symbol in self.stocks:
            self.stocks[symbol].update(kwargs)
    
    def to_dict(self):
        return self.stocks
    
    @staticmethod
    def from_dict(value):
        p=Portfolio()
        p.stocks = value
        return p

class LLMStockDealer:
    def __init__(self, llm_client, data_provider, trade_rules: str = "", 
                 max_position_percentage: float = 0.2, data_file: str = "./output/stock_dealer_data.json"):
        self.llm_client = llm_client
        self.data_provider = data_provider
        self.trade_rules = trade_rules
        self.max_position_percentage = max_position_percentage
        self.data_file = data_file

        self.portfolio = Portfolio()
        self.positions = []
        self.available_cash = 0

        self.last_trade_date=datetime.now()
        self.last_msg=""
        
        self.logger = self._setup_logging()
        self._load_data()

    def _setup_logging(self):
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        os.makedirs('./output', exist_ok=True)
        file_handler = logging.FileHandler(f'./output/stock_dealer_log_{datetime.now().strftime("%Y%m%d")}.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _save_data(self):
        data = {
            "portfolio": self.portfolio.to_dict(),
            "positions": [position.to_dict() for position in self.positions],
            "last_trade_date": self.last_trade_date.isoformat() if self.last_trade_date else None,
            "last_msg": self.last_msg
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f)

    def _load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                data = json.load(f)
            self.portfolio = Portfolio.from_dict(data['portfolio'])
            self.positions = [StockPosition.from_dict(pos) for pos in data['positions']]
            self.last_trade_date = datetime.fromisoformat(data['last_trade_date']) if data['last_trade_date'] else None
            self.last_msg = data['last_msg']

    def update_portfolio(self, new_stocks: List[str]):
        """
        更新整个投资组合
        """
        self.portfolio.update_portfolio(new_stocks)
        self._save_data()

    def update_positions(self, new_positions: List[Dict]):
        """
        更新持仓信息
        """
        self.positions = [StockPosition.from_dict(pos) for pos in new_positions]
        self._save_data()

    def update_cash(self, available_cash: float):
        """
        更新可用资金
        """
        self.available_cash = available_cash
        self._save_data()

    def remove_from_portfolio(self, symbol: str):
        self.portfolio.remove_stock(symbol)
        self._save_data()

    def get_position(self, symbol: str) -> int:
        return sum(pos.quantity for pos in self.positions if pos.symbol == symbol and not pos.is_closed())

    def get_all_positions(self) -> Dict[str, int]:
        positions = {}
        for pos in self.positions:
            if not pos.is_closed():
                positions[pos.symbol] = positions.get(pos.symbol, 0) + pos.quantity
        return positions

    def process_bar(self, bars: Dict[str, pd.Series], news: Dict[str, str] = {}) -> Dict[str, Tuple[str, Union[int, str], str, str, str]]:
        results = {}
        for symbol, bar in bars.items():
            try:
                llm_input, max_buyable_quantity = self._prepare_llm_input(symbol, bar, news.get(symbol, ""))
                llm_response = self.llm_client.one_chat(llm_input)
                self.logger.debug(f"LLM response for {symbol}: {llm_response}")  # 添加这行来记录原始响应
                trade_instruction, quantity, next_msg, trade_reason, trade_plan = self._parse_llm_output(llm_response, max_buyable_quantity)
                results[symbol] = (trade_instruction, quantity, next_msg, trade_reason, trade_plan)
            except Exception as e:
                self.logger.error(f"Error processing bar for {symbol}: {e}", exc_info=True)
                results[symbol] = ('hold', 0, '', f"Error: {str(e)}", '')
        return results

    def calculate_total_assets(self) -> float:
        """
        计算总资产，包括可用现金和所有持仓的当前市值。

        返回:
        float: 总资产值
        """
        total_assets = self.available_cash

        for position in self.positions:
            if not position.is_closed():
                try:
                    current_price = self.data_provider.get_latest_price(position.symbol)
                    position_value = position.total_quantity * current_price
                    total_assets += position_value
                except Exception as e:
                    self.logger.error(f"Error calculating value for position {position.symbol}: {str(e)}")
                    # 如果无法获取最新价格，我们可以选择使用上次已知的价格，或者跳过这个持仓
                    # 这里我们选择使用持仓的入场价格作为后备
                    total_assets += position.total_quantity * position.entry_price

        self.logger.info(f"Total assets calculated: {total_assets:.2f}")
        return total_assets

    def _prepare_llm_input(self, symbol: str, bar: pd.Series, news: str) -> str:
        portfolio_info = "\n".join([f"{s}: {info}" for s, info in self.portfolio.get_all_stocks().items()])
        positions_info = "\n".join([f"{pos.symbol}: {pos.quantity}" for pos in self.positions if not pos.is_closed()])

        # 计算当前持有的该股票的市值
        current_holding_value = sum(pos.quantity * bar['close'] for pos in self.positions if pos.symbol == symbol and not pos.is_closed())
        
        # 计算可用于购买该股票的最大金额
        total_assets = self.calculate_total_assets()
        max_position_value = total_assets * self.max_position_percentage
        available_for_symbol = min(max_position_value - current_holding_value, self.available_cash)
        
        # 计算可购买的最大数量，并调整为100的倍数
        max_buyable_quantity = int(available_for_symbol / bar['close'] / 100) * 100

        input_template = f"""
        你是一位经验丰富的股票交易员，熟悉股票市场规律，擅长把握交易机会并控制风险。请根据以下信息为股票 {symbol} 做出交易决策：

        交易规则：{self.trade_rules}

        当前投资组合：
        {portfolio_info}

        当前持仓：
        {positions_info}

        可用资金：{self.available_cash:.2f}
        
        {symbol} 当前可买入的最大数量（已调整为100的倍数）：{max_buyable_quantity}

        {symbol} 最新行情数据：
        时间: {bar['datetime']}
        开盘: {bar['open']:.2f}
        最高: {bar['high']:.2f}
        最低: {bar['low']:.2f}
        收盘: {bar['close']:.2f}
        成交量: {bar['volume']}

        {symbol} 最新新闻：
        {news}

        上一次的消息: {self.last_msg}

        请注意：
        1. 今天买入的股票不能在当天卖出（T+1交易规则）。
        2. 交易指令格式：
        - 买入：'buy 数量 股票代码'（例如：'buy 100 AAPL'）
        - 卖出：'sell 数量 股票代码'（例如：'sell 100 AAPL'）
        - 不交易：'hold'
        3. 买入数量不能超过 {max_buyable_quantity}，且必须是100的倍数。
        4. 卖出数量不能超过当前持有的数量。
        5. 请提供交易理由和交易计划（包括止损价格和目标价格）。
        6. 即使选择持仓不变（hold），也可以根据最新行情修改交易计划。

        请根据以上信息，给出交易指令或选择不交易（hold），并提供下一次需要的消息。
        请以JSON格式输出，包含以下字段：
        - trade_instruction: 交易指令（字符串，例如 "buy 100 AAPL", "sell 100 AAPL" 或 "hold"）
        - next_message: 下一次需要的消息（字符串）
        - trade_reason: 此刻交易的理由（字符串）
        - trade_plan: 交易计划，包括止损价格和目标价格，可以根据最新行情进行修改（字符串）

        请确保输出的JSON格式正确。
        """
        return input_template, max_buyable_quantity

    def _parse_llm_output(self, llm_response: str, max_buyable_quantity: int) -> Tuple[str, Union[int, str], str, str, str]:
        # 首先尝试提取 JSON 部分
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', llm_response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = llm_response

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            self.logger.warning(f"Failed to parse JSON. Attempting to extract information from text response.")
            data = self._extract_info_from_text(llm_response)

        trade_instruction = data.get('trade_instruction', 'hold').lower()
        next_msg = data.get('next_message', '')
        trade_reason = data.get('trade_reason', '')
        trade_plan = data.get('trade_plan', '')

        instruction_parts = trade_instruction.split()
        action = instruction_parts[0]
        symbol = instruction_parts[-1] if len(instruction_parts) > 2 else ''

        if action not in ['buy', 'sell', 'hold']:
            self.logger.warning(f"Invalid trade instruction: {action}. Defaulting to 'hold'.")
            return "hold", 0, next_msg, trade_reason, trade_plan

        if action == 'buy':
            quantity = int(instruction_parts[1]) if len(instruction_parts) > 1 else 0
            quantity = min(quantity, max_buyable_quantity)
            quantity = (quantity // 100) * 100  # Ensure quantity is a multiple of 100
        elif action == 'sell':
            current_position = sum(pos.quantity for pos in self.positions if pos.symbol == symbol and not pos.is_closed())
            quantity = int(instruction_parts[1]) if len(instruction_parts) > 1 else current_position
            quantity = min(quantity, current_position)
        else:  # hold
            quantity = 0

        return f"{action} {symbol}", quantity, next_msg, trade_reason, trade_plan

    def _extract_info_from_text(self, text: str) -> Dict[str, str]:
        data = {}
        patterns = {
            'trade_instruction': r'交易指令[:：]\s*(.+)',
            'next_message': r'下一次需要的消息[:：]\s*(.+)',
            'trade_reason': r'交易理由[:：]\s*(.+)',
            'trade_plan': r'交易计划[:：]\s*(.+)'
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                data[key] = match.group(1).strip()
        return data

    def _execute_trade(self, trade_instruction: str, quantity: Union[int, str], bar: pd.Series, trade_reason: str, trade_plan: str):
        action, symbol = trade_instruction.split()
        current_price = bar['close']
        current_datetime = bar['datetime']

        if action == 'buy':
            self._open_position(symbol, current_price, quantity, current_datetime, trade_plan)
        elif action == 'sell':
            self._close_position(symbol, current_price, quantity, current_datetime)

    def _open_position(self, symbol: str, price: float, quantity: Union[int, str], datetime: datetime, trade_plan: str):
        if symbol not in self.portfolio.get_all_stocks():
            self.logger.warning(f"Cannot open position for {symbol}: not in portfolio")
            return

        stock_info = self.portfolio.get_stock(symbol)
        current_position = self.get_position(symbol)
        current_holding_value = current_position * price

        # 计算可用于购买该股票的最大金额
        total_assets = self.calculate_total_assets()
        max_position_value = total_assets * self.max_position_percentage
        available_for_symbol = min(max_position_value - current_holding_value, self.available_cash)

        # 计算可以购买的最大数量
        max_buyable_quantity = int(available_for_symbol / price)

        if quantity == 'all':
            quantity = max_buyable_quantity
        else:
            quantity = min(int(quantity), max_buyable_quantity)

        if quantity <= 0:
            self.logger.warning(f"Cannot open position for {symbol}: insufficient funds or invalid quantity")
            return

        # 确保购买数量是100的整数倍（如果适用于您的交易规则）
        quantity = (quantity // 100) * 100

        if quantity > 0:
            new_position = StockPosition(symbol, price, quantity, datetime, stock_info['type'])
            self.positions.append(new_position)
            
            # 更新可用资金
            self.available_cash -= quantity * price
            
            self.logger.info(f"Opened position: {symbol}, Quantity: {quantity}, Price: {price}, Remaining cash: {self.available_cash:.2f}")
        else:
            self.logger.warning(f"Cannot open position for {symbol}: quantity after rounding to 100-share lots is 0")

    def _close_position(self, symbol: str, price: float, quantity: Union[int, str], datetime: datetime):
        open_positions = [pos for pos in self.positions if pos.symbol == symbol and not pos.is_closed()]
        
        if not open_positions:
            self.logger.warning(f"No open positions for {symbol}")
            return

        if quantity == 'all':
            quantity = sum(pos.quantity for pos in open_positions)
        else:
            quantity = min(int(quantity), sum(pos.quantity for pos in open_positions))

        remaining_quantity = quantity
        for position in open_positions:
            if remaining_quantity <= 0:
                break
            if remaining_quantity >= position.quantity:
                position.close_position(price, datetime)
                remaining_quantity -= position.quantity
            else:
                new_position = StockPosition(symbol, position.entry_price, position.quantity - remaining_quantity, position.entry_time, position.position_type)
                self.positions.append(new_position)
                position.quantity = remaining_quantity
                position.close_position(price, datetime)
                remaining_quantity = 0

        self.logger.info(f"Closed position: {symbol}, Quantity: {quantity}, Price: {price}")

    def _close_all_positions(self, bars: Dict[str, pd.Series]):
        for position in self.positions:
            if not position.is_closed():
                if position.symbol in bars:
                    price = bars[position.symbol]['close']
                    position.close_position(price, bars[position.symbol]['datetime'])
                    self.available_cash += position.quantity * price
        self.logger.info("Closed all positions")

    def _log_trade(self, symbol: str, bar: pd.Series, news: str, trade_instruction: str, quantity: Union[int, str], trade_reason: str, trade_plan: str):
        log_msg = f"""
        股票: {symbol}
        时间: {bar['datetime']}, Bar Index: {self._get_today_bar_index(bar['datetime'])}
        价格: 开 {bar['open']:.2f}, 高 {bar['high']:.2f}, 低 {bar['low']:.2f}, 收 {bar['close']:.2f}
        成交量: {bar['volume']}, 持仓量: {bar.get('open_interest', bar.get('hold', 'N/A'))}
        新闻: {news[:200] + '...' if news else '无新闻数据'}
        交易指令: {trade_instruction} {quantity}
        交易理由: {trade_reason}
        交易计划: {trade_plan}
        当前持仓: {self.get_all_positions()}
        可用资金: {self.available_cash:.2f}
        盈亏情况:
        {self._calculate_profits(bar['close'])}
        {self._get_position_details()}
        """
        self.logger.debug(log_msg)

        if trade_instruction.lower() != 'hold':
            console_msg = f"股票: {symbol}, 时间: {bar['datetime']}, 价格: {bar['close']:.2f}, 交易指令: {trade_instruction} {quantity}, 交易理由: {trade_reason[:50]}..., 当前持仓: {self.get_all_positions()}, 可用资金: {self.available_cash:.2f}"
            self.logger.info(console_msg)

    def _get_today_bar_index(self, timestamp: pd.Timestamp, bar_interval: int = 1) -> int:
        from time import time
        beijing_time = timestamp.tz_convert('Asia/Shanghai').time()
        morning_start = time(9, 30)
        morning_end = time(11, 30)
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)

        if morning_start <= beijing_time <= morning_end:
            minutes = (beijing_time.hour - 9) * 60 + beijing_time.minute - 30
        elif afternoon_start <= beijing_time <= afternoon_end:
            minutes = (beijing_time.hour - 13) * 60 + beijing_time.minute + 120
        elif beijing_time > afternoon_end:
            return 240 // bar_interval  # 交易日结束后返回最后一个bar的索引
        else:
            return 0  # 交易日开始前返回0

        return minutes // bar_interval

    def _calculate_profits(self, current_price: float) -> str:
        realized_profit = sum(pos.calculate_profit(pos.exit_price) for pos in self.positions if pos.is_closed())
        unrealized_profit = sum(pos.calculate_profit(current_price) for pos in self.positions if not pos.is_closed())
        total_profit = realized_profit + unrealized_profit
        return f"实现盈亏: {realized_profit:.2f}\n未实现盈亏: {unrealized_profit:.2f}\n总盈亏: {total_profit:.2f}"

    def _get_position_details(self) -> str:
        details = "持仓明细:\n"
        for pos in self.positions:
            if not pos.is_closed():
                details += f"  股票: {pos.symbol}, 数量: {pos.quantity}, 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}, 类型: {pos.position_type}\n"
        return details

    def analyze_performance(self, start_date: datetime, end_date: datetime) -> str:
        """Analyze trading performance over a specific period"""
        closed_positions = [pos for pos in self.positions if pos.is_closed() and start_date <= pos.entry_time <= end_date]
        
        if not closed_positions:
            return "在指定时间段内没有已平仓的交易。"

        total_trades = len(closed_positions)
        profitable_trades = sum(1 for pos in closed_positions if pos.calculate_profit(pos.exit_price) > 0)
        total_profit = sum(pos.calculate_profit(pos.exit_price) for pos in closed_positions)
        max_profit = max(pos.calculate_profit(pos.exit_price) for pos in closed_positions)
        max_loss = min(pos.calculate_profit(pos.exit_price) for pos in closed_positions)
        
        avg_holding_time = sum((pos.exit_time - pos.entry_time).days for pos in closed_positions) / total_trades

        performance_summary = f"""
        交易性能分析 ({start_date.date()} 到 {end_date.date()}):
        总交易次数: {total_trades}
        盈利交易次数: {profitable_trades}
        亏损交易次数: {total_trades - profitable_trades}
        胜率: {(profitable_trades / total_trades) * 100:.2f}%
        总盈亏: {total_profit:.2f}
        最大单笔盈利: {max_profit:.2f}
        最大单笔亏损: {max_loss:.2f}
        平均持仓时间: {avg_holding_time:.2f} 天
        """
        return performance_summary

    def generate_trading_report(self, start_date: datetime, end_date: datetime) -> str:
        """Generate a comprehensive trading report"""
        performance_analysis = self.analyze_performance(start_date, end_date)
        
        closed_positions = [pos for pos in self.positions if pos.is_closed() and start_date <= pos.entry_time <= end_date]
        open_positions = [pos for pos in self.positions if not pos.is_closed() and pos.entry_time <= end_date]

        closed_positions_details = "已平仓交易:\n"
        for pos in closed_positions:
            profit = pos.calculate_profit(pos.exit_price)
            closed_positions_details += f"  股票: {pos.symbol}, 数量: {pos.quantity}, 开仓价: {pos.entry_price:.2f}, 平仓价: {pos.exit_price:.2f}, 盈亏: {profit:.2f}, 持仓时间: {(pos.exit_time - pos.entry_time).days} 天\n"

        open_positions_details = "未平仓交易:\n"
        for pos in open_positions:
            open_positions_details += f"  股票: {pos.symbol}, 数量: {pos.quantity}, 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}, 类型: {pos.position_type}\n"

        report = f"""
        交易报告 ({start_date.date()} 到 {end_date.date()}):

        {performance_analysis}

        {closed_positions_details}

        {open_positions_details}

        当前投资组合:
        {self._get_portfolio_summary()}
        """
        return report

    def _get_portfolio_summary(self) -> str:
        summary = ""
        for symbol, info in self.portfolio.get_all_stocks().items():
            summary += f"  股票: {symbol}, 类型: {info['type']}, 目标价: {info['target_price']:.2f}, 止损价: {info['stop_loss']:.2f}\n"
        return summary

    def update_trade_plan(self, symbol: str, new_target_price: float, new_stop_loss: float):
        """Update the trade plan for a specific stock in the portfolio"""
        if symbol in self.portfolio.get_all_stocks():
            self.portfolio.add_stock(symbol, self.portfolio.get_stock(symbol)['type'], new_target_price, new_stop_loss)
            self.logger.info(f"Updated trade plan for {symbol}: Target Price: {new_target_price}, Stop Loss: {new_stop_loss}")
            self._save_data()
        else:
            self.logger.warning(f"Cannot update trade plan: {symbol} not in portfolio")

    def get_portfolio_risk(self) -> float:
        """Calculate the overall portfolio risk based on current positions and stock volatility"""
        # This is a simplified risk calculation. In a real-world scenario, you would use more sophisticated methods.
        total_value = sum(pos.quantity * self.data_provider.get_latest_price(pos.symbol) for pos in self.positions if not pos.is_closed())
        weighted_volatility = sum(pos.quantity * self.data_provider.get_stock_volatility(pos.symbol) / total_value for pos in self.positions if not pos.is_closed())
        return weighted_volatility * 100  # Return as percentage

    def rebalance_portfolio(self):
        """Rebalance the portfolio based on current market conditions and risk tolerance"""
        current_risk = self.get_portfolio_risk()
        target_risk = 15  # Example target risk percentage

        if current_risk > target_risk:
            # Reduce positions in high-volatility stocks
            high_vol_positions = sorted(self.positions, key=lambda p: self.data_provider.get_stock_volatility(p.symbol), reverse=True)
            for pos in high_vol_positions:
                if current_risk <= target_risk:
                    break
                if not pos.is_closed():
                    reduce_quantity = int(pos.quantity * 0.2)  # Reduce position by 20%
                    if reduce_quantity > 0:
                        self._close_position(pos.symbol, self.data_provider.get_latest_price(pos.symbol), reduce_quantity, datetime.now())
                        current_risk = self.get_portfolio_risk()
            self.logger.info(f"Rebalanced portfolio. New risk: {current_risk:.2f}%")
        else:
            self.logger.info(f"Portfolio risk ({current_risk:.2f}%) is within acceptable range. No rebalancing needed.")

    def run_daily_update(self):
        """Perform daily updates and generate reports"""
        today = datetime.now().date()
        self.rebalance_portfolio()
        self._save_data()
        
        # Generate and log daily report
        start_of_day = datetime.combine(today, datetime.min.time())
        end_of_day = datetime.combine(today, datetime.max.time())
        daily_report = self.generate_trading_report(start_of_day, end_of_day)
        self.logger.info(f"Daily Report:\n{daily_report}")

        # Update portfolio based on new market data or news
        for symbol in self.portfolio.get_all_stocks().keys():
            latest_data = self.data_provider.get_latest_stock_data(symbol)
            news = self.data_provider.get_one_stock_news(symbol)
            self._update_portfolio_based_on_data(symbol, latest_data, news)

    def _update_portfolio_based_on_data(self, symbol: str, latest_data: Dict, news: str):
        """Update portfolio based on latest data and news"""
        prompt = f"""
        请根据以下最新数据和新闻，为股票 {symbol} 更新交易计划：

        最新数据：
        {json.dumps(latest_data, indent=2)}

        最新新闻：
        {news}

        当前交易计划：
        {json.dumps(self.portfolio.get_stock(symbol), indent=2)}

        请提供更新后的目标价格和止损价格，并说明理由。
        输出格式应为 JSON，包含以下字段：
        - target_price: 新的目标价格
        - stop_loss: 新的止损价格
        - reason: 更新理由
        """

        response = self.llm_client.one_chat(prompt)
        try:
            update_data = json.loads(response)
            self.update_trade_plan(symbol, update_data['target_price'], update_data['stop_loss'])
            self.logger.info(f"Updated trade plan for {symbol}. Reason: {update_data['reason']}")
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse LLM response for {symbol} trade plan update")