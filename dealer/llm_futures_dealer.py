import logging
import json
import os
import re
import pandas as pd
import pytz
from typing import Dict, List, Tuple, Literal, Optional, Union
from datetime import datetime, timedelta, time as dt_time
from enum import Enum

import ta
from dealer.trade_time import get_trading_end_time
from dealer.futures_provider import MainContractProvider

# 设置北京时区
beijing_tz = pytz.timezone('Asia/Shanghai')

class PositionType(Enum):
    LONG = 1
    SHORT = 2

class TradePosition:
    def __init__(self, entry_price: float, position_type: PositionType, entry_time: pd.Timestamp):
        self.entry_price = entry_price
        self.position_type = position_type
        self.entry_time = entry_time
        self.exit_price = None
        self.exit_time = None
        self.highest_profit = 0
        self.lowest_profit = 0

    def close_position(self, exit_price: float, exit_time: pd.Timestamp):
        self.exit_price = exit_price
        self.exit_time = exit_time

    def calculate_profit(self, current_price: float) -> float:
        price_diff = current_price - self.entry_price if self.position_type == PositionType.LONG else self.entry_price - current_price
        if self.exit_price is not None:
            price_diff = self.exit_price - self.entry_price if self.position_type == PositionType.LONG else self.entry_price - self.exit_price
        
        if not self.is_closed():
            self.highest_profit = max(self.highest_profit, price_diff)
            self.lowest_profit = min(self.lowest_profit, price_diff)
        
        return price_diff

    def is_closed(self) -> bool:
        return self.exit_price is not None

class TradePositionManager:
    def __init__(self):
        self.positions: List[TradePosition] = []

    def open_position(self, price: float, quantity: int, is_long: bool, entry_time: pd.Timestamp):
        position_type = PositionType.LONG if is_long else PositionType.SHORT
        for _ in range(quantity):
            self.positions.append(TradePosition(price, position_type, entry_time))

    def close_positions(self, price: float, quantity: int, is_long: bool, exit_time: pd.Timestamp) -> int:
        position_type = PositionType.LONG if is_long else PositionType.SHORT
        closed = 0
        for position in self.positions:
            if closed >= quantity:
                break
            if position.position_type == position_type and not position.is_closed():
                position.close_position(price, exit_time)
                closed += 1
        return closed

    def calculate_profits(self, current_price: float) -> Dict[str, float]:
        realized_profit = sum(pos.calculate_profit(current_price) for pos in self.positions if pos.is_closed())
        unrealized_profit = sum(pos.calculate_profit(current_price) for pos in self.positions if not pos.is_closed())
        
        highest_unrealized_profit = sum(pos.highest_profit for pos in self.positions if not pos.is_closed())
        lowest_unrealized_profit = sum(pos.lowest_profit for pos in self.positions if not pos.is_closed())
        
        return {
            "realized_profit": realized_profit,
            "unrealized_profit": unrealized_profit,
            "total_profit": realized_profit + unrealized_profit,
            "highest_unrealized_profit": highest_unrealized_profit,
            "lowest_unrealized_profit": lowest_unrealized_profit
        }

    def get_current_position(self) -> int:
        long_positions = sum(1 for pos in self.positions if pos.position_type == PositionType.LONG and not pos.is_closed())
        short_positions = sum(1 for pos in self.positions if pos.position_type == PositionType.SHORT and not pos.is_closed())
        return long_positions - short_positions

    def get_position_details(self) -> str:
        long_positions = [pos for pos in self.positions if pos.position_type == PositionType.LONG and not pos.is_closed()]
        short_positions = [pos for pos in self.positions if pos.position_type == PositionType.SHORT and not pos.is_closed()]
        
        details = "持仓明细:\n"
        if long_positions:
            details += "多头:\n"
            for i, pos in enumerate(long_positions, 1):
                details += f"  {i}. 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}, 最高盈利: {pos.highest_profit:.2f}, 最低盈利: {pos.lowest_profit:.2f}\n"
        if short_positions:
            details += "空头:\n"
            for i, pos in enumerate(short_positions, 1):
                details += f"  {i}. 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}, 最高盈利: {pos.highest_profit:.2f}, 最低盈利: {pos.lowest_profit:.2f}\n"
        return details

class ContractState:
    def __init__(self, symbol: str, max_position: int):
        self.symbol = symbol
        self.max_position = max_position
        self.position_manager = TradePositionManager()
        self.daily_history = pd.DataFrame()
        self.hourly_history = pd.DataFrame()
        self.minute_history = pd.DataFrame()
        self.today_minute_bars = pd.DataFrame()
        self.last_msg = ""
        self.last_trade_date = None
        self.current_date = None
        self.total_profit = 0
        self.night_closing_time = None

class LLMFuturesDealer:
    def __init__(self, llm_client, symbols: List[str], data_provider: MainContractProvider, trade_rules: str = "",
                 max_daily_bars: int = 60, max_hourly_bars: int = 30, max_minute_bars: int = 240,
                 backtest_date: Optional[str] = None, compact_mode: bool = False,
                 max_positions: Dict[str, int] = None):
        self._setup_logging()
        self.trade_rules = trade_rules
        self.symbols = symbols
        self.data_provider = data_provider
        self.llm_client = llm_client
        self.last_news_time = None
        self.news_summary = ""
        self.is_backtest = backtest_date is not None
        self.max_daily_bars = max_daily_bars
        self.max_hourly_bars = max_hourly_bars
        self.max_minute_bars = max_minute_bars
        self.compact_mode = compact_mode
        self.backtest_date = backtest_date or datetime.now().strftime('%Y-%m-%d')

        self.contract_states = {}
        for symbol in symbols:
            max_position = max_positions.get(symbol, 1) if max_positions else 1
            self.contract_states[symbol] = ContractState(symbol, max_position)
            self.contract_states[symbol].night_closing_time = self._get_night_closing_time(symbol)

        self.trading_hours = [
            (dt_time(9, 0), dt_time(11, 30)),
            (dt_time(13, 0), dt_time(15, 0)),
            (dt_time(21, 0), dt_time(23, 59)),
            (dt_time(0, 0), dt_time(2, 30))
        ]

    def _setup_logging(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        os.makedirs('./output', exist_ok=True)
        file_handler = logging.FileHandler(f'./output/log_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _get_night_closing_time(self, symbol: str) -> Optional[dt_time]:
        night_end = get_trading_end_time(symbol, 'night')
        if isinstance(night_end, str) and ':' in night_end:
            hour, minute = map(int, night_end.split(':'))
            return dt_time(hour, minute)
        return None

    def _get_latest_news(self, symbol: str):
        if self.is_backtest:
            return pd.DataFrame()
        news_df = self.data_provider.get_futures_news(symbol, page_num=0, page_size=20)
        if news_df is not None and not news_df.empty:
            return news_df.sort_values('publish_time', ascending=False)
        return pd.DataFrame()

    def _summarize_news(self, news_df):
        if news_df.empty:
            return ""

        news_text = "\n".join(f"- {row['title']}" for _, row in news_df.iterrows())
        prompt = f"请将以下新闻整理成不超过200字的今日交易提示简报：\n\n{news_text}"
        
        summary = self.llm_client.one_chat(prompt)
        return summary[:200]

    def _update_news(self, symbol: str, current_datetime):
        if self.is_backtest:
            return False

        try:
            news_df = self._get_latest_news(symbol)
            if news_df.empty:
                self.logger.info(f"No new news available for {symbol}")
                return False

            def safe_parse_time(time_str):
                try:
                    return pd.to_datetime(int(time_str) / 1000, unit='s', utc=True).tz_convert(beijing_tz)
                except ValueError:
                    try:
                        return pd.to_datetime(time_str).tz_localize(beijing_tz)
                    except:
                        self.logger.error(f"Failed to parse news time: {time_str}")
                        return None

            latest_news_time = safe_parse_time(news_df['publish_time'].iloc[0])
            
            if latest_news_time is None:
                self.logger.warning("Failed to parse latest news time, skipping news update")
                return False

            if self.last_news_time is None or latest_news_time > self.last_news_time:
                self.last_news_time = latest_news_time
                new_summary = self._summarize_news(news_df)
                if new_summary != self.news_summary:
                    self.news_summary = new_summary
                    self.logger.info(f"Updated news summary for {symbol}: {self.news_summary[:100]}...")
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error in _update_news for {symbol}: {str(e)}", exc_info=True)
            return False

    def _is_trading_time(self, dt: datetime) -> bool:
        t = dt.time()
        for start, end in self.trading_hours:
            if start <= t <= end:
                return True
        return False

    def _filter_trading_data(self, df: pd.DataFrame) -> pd.DataFrame:
        def is_trading_time(dt):
            t = dt.time()
            return any(start <= t <= end for start, end in self.trading_hours)
        
        mask = df['datetime'].apply(is_trading_time)
        filtered_df = df[mask]
        
        self.logger.debug(f"Trading hours filter: {len(df)} -> {len(filtered_df)} rows")
        return filtered_df

    def _get_today_data(self, symbol: str, date: datetime.date) -> pd.DataFrame:
        self.logger.info(f"Fetching data for {symbol} on date: {date}")

        if self.is_backtest:
            today_data = self.data_provider.get_bar_data(symbol, '1', date.strftime('%Y-%m-%d'))
        else:
            today_data = self.data_provider.get_akbar(symbol, '1m')
            today_data = today_data[today_data.index.date == date]
            today_data = today_data.reset_index()

        self.logger.info(f"Raw data fetched for {symbol}: {len(today_data)} rows")

        if today_data.empty:
            self.logger.warning(f"No data returned from data provider for {symbol} on date {date}")
            return pd.DataFrame()

        today_data = today_data.rename(columns={'open_interest': 'hold'})

        if self.is_backtest:
            filtered_data = today_data[today_data['trading_date'] == date]
        else:
            filtered_data = today_data[today_data['datetime'].dt.date == date]

        if filtered_data.empty:
            self.logger.warning(f"No data found for {symbol} on date {date} after filtering.")
        else:
            self.logger.info(f"Filtered data for {symbol}: {len(filtered_data)} rows")

        return filtered_data

    def _validate_and_prepare_data(self, df: pd.DataFrame, date: str) -> pd.DataFrame:
        original_len = len(df)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df[df['datetime'].dt.date == pd.to_datetime(date).date()]
        df = self._filter_trading_data(df)
        
        self.logger.info(f"Bars for date {date}: Original: {original_len}, After filtering: {len(df)}")
        
        if len(df) > self.max_minute_bars:
            self.logger.warning(f"Unusually high number of bars ({len(df)}) for date {date}. Trimming to {self.max_minute_bars} bars.")
            df = df.tail(self.max_minute_bars)
        
        return df

    def _preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.fillna(method='ffill').fillna(method='bfill')

        for col in numeric_columns:
            df[col] = df[col].clip(lower=0)

        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 5:
            return df
        
        try:
            df['sma_10'] = df['close'].rolling(window=min(10, len(df))).mean()
            df['ema_20'] = df['close'].ewm(span=min(20, len(df)), adjust=False).mean()
            df['rsi'] = ta.momentum.RSIIndicator(close=df['close'], window=min(14, len(df))).rsi()
            
            macd = ta.trend.MACD(close=df['close'], window_slow=min(26, len(df)), window_fast=min(12, len(df)), window_sign=min(9, len(df)))
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            
            bollinger = ta.volatility.BollingerBands(close=df['close'], window=min(20, len(df)), window_dev=2)
            df['bollinger_high'] = bollinger.bollinger_hband()
            df['bollinger_mid'] = bollinger.bollinger_mavg()
            df['bollinger_low'] = bollinger.bollinger_lband()
            
            df['atr'] = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=min(14, len(df))).average_true_range()
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {str(e)}")
        
        return df

    def _format_indicators(self, indicators: pd.Series) -> str:
        def format_value(value):
            if isinstance(value, (int, float)):
                return f"{value:.2f}"
            return str(value)

        if self.compact_mode:
            return f"""
            SMA10: {format_value(indicators.get('sma_10', 'N/A'))}
            EMA20: {format_value(indicators.get('ema_20', 'N/A'))}
            RSI: {format_value(indicators.get('rsi', 'N/A'))}
            MACD: {format_value(indicators.get('macd', 'N/A'))}
            BB高: {format_value(indicators.get('bollinger_high', 'N/A'))}
            BB低: {format_value(indicators.get('bollinger_low', 'N/A'))}
            """
        else:
            return f"""
            10周期简单移动平均线 (SMA): {format_value(indicators.get('sma_10', 'N/A'))}
            20周期指数移动平均线 (EMA): {format_value(indicators.get('ema_20', 'N/A'))}
            相对强弱指标 (RSI): {format_value(indicators.get('rsi', 'N/A'))}
            MACD: {format_value(indicators.get('macd', 'N/A'))}
            MACD信号线: {format_value(indicators.get('macd_signal', 'N/A'))}
            平均真实范围 (ATR): {format_value(indicators.get('atr', 'N/A'))}
            布林带上轨: {format_value(indicators.get('bollinger_high', 'N/A'))}
            布林带中轨: {format_value(indicators.get('bollinger_mid', 'N/A'))}
            布林带下轨: {format_value(indicators.get('bollinger_low', 'N/A'))}
            """

    def _prepare_llm_input(self, symbol: str, bar: pd.Series, news: str) -> str:
        contract_state = self.contract_states[symbol]
        if contract_state.today_minute_bars.empty:
            return "Insufficient data for LLM input"
        
        today_data = self._calculate_indicators(contract_state.today_minute_bars)
        latest_indicators = today_data.iloc[-1]
        
        daily_summary = self._compress_history(contract_state.daily_history, 'D')
        hourly_summary = self._compress_history(contract_state.hourly_history, 'H')
        minute_summary = self._compress_history(contract_state.today_minute_bars, 'T')
        
        open_interest = bar.get('hold', 'N/A')
    
        position = contract_state.position_manager.get_current_position()
        position_description = "空仓"
        if position > 0:
            position_description = f"多头 {position} 手"
        elif position < 0:
            position_description = f"空头 {abs(position)} 手"
            
        profits = contract_state.position_manager.calculate_profits(bar['close'])

        profit_info = f"""
        实际盈亏: {profits['realized_profit']:.2f}
        浮动盈亏: {profits['unrealized_profit']:.2f}
        总盈亏: {profits['total_profit']:.2f}
        """

        position_details = contract_state.position_manager.get_position_details()

        news_section = ""
        if news and news.strip():
            news_section = f"""
            最新新闻:
            {news}

            新闻分析提示：
            1. 请考虑这条新闻可能对市场造成的短期（当日内）、中期（数日到数周）和长期（数月以上）影响。
            2. 注意市场可能已经提前消化了这个消息，价格可能已经反映了这个信息。
            3. 评估这个新闻是否与之前的市场预期一致，如果有出入，可能会造成更大的市场反应。
            4. 考虑这个新闻可能如何影响市场情绪和交易者的行为。
            5. 这条消息只会出现以此，如果有值得记录的信息，需要保留在 next_message 中
            """

        input_template = f"""
        你是一位经验老道的期货交易员，熟悉期货规律，掌握交易中获利的技巧。不放弃每个机会，也随时警惕风险。你认真思考，审视数据，做出交易决策。
        今天执行的日内交易策略。所有开仓都需要在当天收盘前平仓，不留过夜仓位。你看到数据的周期是：1分钟
        注意：历史信息不会保留，如果有留给后续使用的信息，需要记录在 next_message 中。
        
        {f"交易中注意遵循以下规则:{self.trade_rules}" if self.trade_rules else ""}

        当前合约: {symbol}
        上一次的消息: {contract_state.last_msg}
        当前 bar index: {len(contract_state.today_minute_bars) - 1}

        日线历史摘要 (最近 {self.max_daily_bars} 天):
        {daily_summary}

        小时线历史摘要 (最近 {self.max_hourly_bars} 小时):
        {hourly_summary}

        今日分钟线摘要 (最近 {self.max_minute_bars} 分钟):
        {minute_summary}

        当前 bar 数据:
        时间: {bar['datetime'].strftime('%Y-%m-%d %H:%M')}
        开盘: {bar['open']:.2f}
        最高: {bar['high']:.2f}
        最低: {bar['low']:.2f}
        收盘: {bar['close']:.2f}
        成交量: {bar['volume']}
        持仓量: {open_interest}

        技术指标:
        {self._format_indicators(latest_indicators)}

        {news_section}

        当前持仓状态: {position_description}
        最大持仓: {contract_state.max_position} 手

        盈亏情况:
        {profit_info}

        {position_details}

        请注意：
        1. 日内仓位需要在每天15:00之前平仓。
        2. 当前时间为 {bar['datetime'].strftime('%H:%M')}，请根据时间决定是否需要平仓。
        3. 开仓指令格式：
           - 买入：'buy 数量'（例如：'buy 2' 或 'buy all'）
           - 卖空：'short 数量'（例如：'short 2' 或 'short all'）
        4. 平仓指令格式：
           - 卖出平多：'sell 数量'（例如：'sell 2' 或 'sell all'）
           - 买入平空：'cover 数量'（例如：'cover 2' 或 'cover all'）
        5. 当前持仓已经达到最大值或最小值时，请勿继续开仓。
        6. 请提供交易理由和交易计划（包括止损区间和目标价格预测）。
        7. 即使选择持仓不变（hold），也可以根据最新行情修改交易计划。如果行情变化导致预期发生变化，请更新 trade_plan。

        请根据以上信息，给出交易指令或选择不交易（hold），并提供下一次需要的消息。
        请以JSON格式输出，包含以下字段：
        - trade_instruction: 交易指令（字符串，例如 "buy 2", "sell all", "short 1", "cover all" 或 "hold"）
        - next_message: 下一次需要的消息（字符串）
        - trade_reason: 此刻交易的理由（字符串）
        - trade_plan: 交易计划，包括止损区间和目标价格预测，可以根据最新行情进行修改（字符串）

        请确保输出的JSON格式正确，并用```json 和 ``` 包裹。
        """
        return input_template

    def _compress_history(self, df: pd.DataFrame, period: str) -> str:
        if df.empty:
            return "No data available"
        
        df = df.tail(self.max_daily_bars if period == 'D' else self.max_hourly_bars if period == 'H' else self.max_minute_bars)
        
        summary = []
        for _, row in df.iterrows():
            if self.compact_mode:
                summary.append(f"{row['datetime'].strftime('%Y-%m-%d %H:%M' if period != 'D' else '%Y-%m-%d')}: "
                               f"C:{row['close']:.2f} V:{row['volume']}")
            else:
                summary.append(f"{row['datetime'].strftime('%Y-%m-%d %H:%M' if period != 'D' else '%Y-%m-%d')}: "
                               f"O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']}")
        
        return "\n".join(summary)

    def _parse_llm_output(self, llm_response: str) -> Tuple[str, Union[int, str], str, str, str]:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in the response")
            
            json_str = json_match.group(1)
            data = json.loads(json_str)
            
            trade_instruction = data.get('trade_instruction', 'hold').lower()
            next_msg = data.get('next_message', '')
            trade_reason = data.get('trade_reason', '')
            trade_plan = data.get('trade_plan', '')
            
            instruction_parts = trade_instruction.split()
            action = instruction_parts[0]
            quantity = instruction_parts[1] if len(instruction_parts) > 1 else '1'
            
            if action not in ['buy', 'sell', 'short', 'cover', 'hold']:
                self.logger.warning(f"Invalid trade instruction: {action}. Defaulting to 'hold'.")
                return "hold", 1, next_msg, "", trade_plan
            
            if quantity.lower() == 'all':
                quantity = 'all'
            else:
                try:
                    quantity = int(quantity)
                except ValueError:
                    quantity = 1
            
            return action, quantity, next_msg, trade_reason, trade_plan
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parsing error: {e}")
            return "hold", 1, "", "JSON 解析错误", ""
        except Exception as e:
            self.logger.error(f"Error parsing LLM output: {e}")
            return "hold", 1, "", "解析错误", ""

    def _execute_trade(self, symbol: str, trade_instruction: str, quantity: Union[int, str], bar: pd.Series, trade_reason: str, trade_plan: str):
        contract_state = self.contract_states[symbol]
        current_datetime = bar['datetime']
        current_date = current_datetime.date()
        current_price = bar['close']

        self.logger.info(f"尝试执行交易: 合约={symbol}, 指令={trade_instruction}, 数量={quantity}, 价格={current_price}")
        self.logger.info(f"交易理由: {trade_reason}")
        self.logger.info(f"交易计划: {trade_plan}")

        if contract_state.last_trade_date != current_date:
            self._close_all_positions(symbol, current_price, current_datetime)
            contract_state.last_trade_date = current_date

        if trade_instruction.lower() == 'hold':
            self.logger.info(f"{symbol}: 保持当前仓位，不执行交易。")
            return

        action = trade_instruction.lower()
        qty = contract_state.max_position if quantity == 'all' else int(quantity)

        current_position = contract_state.position_manager.get_current_position()

        self.logger.info(f"{symbol}: 当前仓位: {current_position}, 最大仓位: {contract_state.max_position}")

        if action == "buy":
            max_buy = contract_state.max_position - current_position
            actual_quantity = min(qty, max_buy)
            self.logger.info(f"{symbol}: 尝试买入 {actual_quantity} 手")
            contract_state.position_manager.open_position(current_price, actual_quantity, True, current_datetime)
        elif action == "sell":
            actual_quantity = contract_state.position_manager.close_positions(current_price, qty, True, current_datetime)
            self.logger.info(f"{symbol}: 尝试卖出 {actual_quantity} 手")
        elif action == "short":
            max_short = contract_state.max_position + current_position
            actual_quantity = min(qty, max_short)
            self.logger.info(f"{symbol}: 尝试做空 {actual_quantity} 手")
            contract_state.position_manager.open_position(current_price, actual_quantity, False, current_datetime)
        elif action == "cover":
            actual_quantity = contract_state.position_manager.close_positions(current_price, qty, False, current_datetime)
            self.logger.info(f"{symbol}: 尝试买入平空 {actual_quantity} 手")
        else:
            self.logger.error(f"{symbol}: 未知的交易动作: {action}")
            return

        self._force_close_if_needed(symbol, current_datetime, current_price)

        profits = contract_state.position_manager.calculate_profits(current_price)
        contract_state.total_profit = profits['total_profit']

        self.logger.info(f"{symbol}: 执行交易后的仓位: {contract_state.position_manager.get_current_position()}")
        self.logger.info(f"{symbol}: 当前总盈亏: {contract_state.total_profit:.2f}")
        self.logger.info(contract_state.position_manager.get_position_details())

    def _close_all_positions(self, symbol: str, current_price: float, current_datetime: pd.Timestamp):
        contract_state = self.contract_states[symbol]
        contract_state.position_manager.close_positions(current_price, float('inf'), True, current_datetime)
        contract_state.position_manager.close_positions(current_price, float('inf'), False, current_datetime)

    def _force_close_if_needed(self, symbol: str, current_datetime: pd.Timestamp, current_price: float):
        contract_state = self.contract_states[symbol]
        day_closing_time = dt_time(14, 55)
        night_session_start = dt_time(21, 0)

        current_time = current_datetime.time()
        is_day_session = current_time < night_session_start and current_time >= dt_time(9, 0)
        is_night_session = current_time >= night_session_start or current_time < dt_time(9, 0)

        if is_day_session and current_time >= day_closing_time:
            self._close_all_positions(symbol, current_price, current_datetime)
            self.logger.info(f"{symbol}: 日盘强制平仓")
        elif is_night_session and contract_state.night_closing_time:
            # Check if it's within 5 minutes of the night closing time
            closing_window_start = (datetime.combine(datetime.min, contract_state.night_closing_time) - timedelta(minutes=5)).time()
            if closing_window_start <= current_time <= contract_state.night_closing_time:
                self._close_all_positions(symbol, current_price, current_datetime)
                self.logger.info(f"{symbol}: 夜盘强制平仓")
            else:
                self.logger.info(f"{symbol}: 夜盘交易，当前仓位：{contract_state.position_manager.get_current_position()}")
        elif is_night_session and not contract_state.night_closing_time:
            self.logger.info(f"{symbol}: 夜盘交易（无强制平仓时间），当前仓位：{contract_state.position_manager.get_current_position()}")

    def _get_today_bar_index(self, symbol: str, timestamp: pd.Timestamp) -> int:
        contract_state = self.contract_states[symbol]
        if contract_state.today_minute_bars.empty:
            return 0
        
        try:
            if not pd.api.types.is_datetime64_any_dtype(contract_state.today_minute_bars['datetime']):
                contract_state.today_minute_bars['datetime'] = pd.to_datetime(contract_state.today_minute_bars['datetime'], utc=True)
            
            if contract_state.today_minute_bars['datetime'].dt.tz is None:
                contract_state.today_minute_bars['datetime'] = contract_state.today_minute_bars['datetime'].dt.tz_localize('Asia/Shanghai')
            
            contract_state.today_minute_bars['datetime'] = contract_state.today_minute_bars['datetime'].dt.tz_convert('UTC')
            
            utc_timestamp = timestamp.tz_convert('UTC')
            
            today_bars = contract_state.today_minute_bars[contract_state.today_minute_bars['datetime'].dt.date == utc_timestamp.date()]
            return len(today_bars)
        except Exception as e:
            self.logger.error(f"Error in _get_today_bar_index for {symbol}: {str(e)}", exc_info=True)
            return 0

    def _log_bar_info(self, symbol: str, bar: Union[pd.Series, dict], news: str, trade_instruction: str, trade_reason: str, trade_plan: str):
        try:
            os.makedirs('./output', exist_ok=True)

            current_date = datetime.now().strftime('%Y%m%d')
            file_handler = next((h for h in self.logger.handlers if isinstance(h, logging.FileHandler) and h.baseFilename.endswith(f'{current_date}.log')), None)
            
            if not file_handler:
                file_path = f'./output/log_{symbol}_{current_date}.log'
                file_handler = logging.FileHandler(file_path)
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                self.logger.addHandler(file_handler)

                for handler in self.logger.handlers[:]:
                    if isinstance(handler, logging.FileHandler) and not handler.baseFilename.endswith(f'{current_date}.log'):
                        self.logger.removeHandler(handler)
                        handler.close()

            if isinstance(bar, dict):
                bar = pd.Series(bar)

            contract_state = self.contract_states[symbol]
            log_msg = f"""
            合约: {symbol}
            时间: {pd.to_datetime(bar['datetime'])}, Bar Index: {self._get_today_bar_index(symbol, pd.to_datetime(bar['datetime']))}
            价格: 开 {bar['open']:.2f}, 高 {bar['high']:.2f}, 低 {bar['low']:.2f}, 收 {bar['close']:.2f}
            成交量: {bar['volume']}, 持仓量: {bar.get('open_interest', bar.get('hold', 'N/A'))}
            新闻: {news[:200] + '...' if news else '无新闻数据'}
            交易指令: {trade_instruction}
            交易理由: {trade_reason}
            交易计划: {trade_plan}
            当前持仓: {contract_state.position_manager.get_current_position()}
            盈亏情况:
            {contract_state.position_manager.calculate_profits(bar['close'])}
            {contract_state.position_manager.get_position_details()}
            """

            self.logger.debug(log_msg)

            if trade_instruction.lower() != 'hold':
                console_msg = f"{symbol}: 时间: {pd.to_datetime(bar['datetime'])}, 价格: {bar['close']:.2f}, 交易指令: {trade_instruction}, 交易理由: {trade_reason[:50]}..., 当前持仓: {contract_state.position_manager.get_current_position()}"
                self.logger.info(console_msg)

        except Exception as e:
            self.logger.error(f"Error in _log_bar_info for {symbol}: {str(e)}", exc_info=True)

    def parse_timestamp(self, timestamp):
        self.logger.debug(f"Attempting to parse timestamp: {timestamp}")
        try:
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e12:
                    if timestamp > 9999999999999:
                        self.logger.warning(f"Abnormally large timestamp detected: {timestamp}")
                        try:
                            return pd.Timestamp(timestamp, unit='ns').tz_localize(beijing_tz)
                        except Exception:
                            self.logger.error(f"Failed to parse abnormally large timestamp: {timestamp}")
                            return datetime.now(beijing_tz)
                    return datetime.fromtimestamp(timestamp / 1000, tz=beijing_tz)
                else:
                    return datetime.fromtimestamp(timestamp, tz=beijing_tz)
            elif isinstance(timestamp, str):
                import dateutil.parser as parser
                return parser.parse(timestamp).astimezone(beijing_tz)
            elif isinstance(timestamp, pd.Timestamp):
                return timestamp.tz_localize(beijing_tz) if timestamp.tz is None else timestamp.tz_convert(beijing_tz)
            elif isinstance(timestamp, datetime):
                return timestamp.astimezone(beijing_tz) if timestamp.tzinfo else beijing_tz.localize(timestamp)
            else:
                raise ValueError(f"Unexpected timestamp type: {type(timestamp)}")
        except Exception as e:
            self.logger.error(f"Error parsing timestamp {timestamp}: {str(e)}")
            self.logger.warning("Using current time as fallback")
            return datetime.now(beijing_tz)

    def process_bar(self, symbol: str, bar: pd.Series, news: str = "") -> Tuple[str, Union[int, str], str]:
        try:
            contract_state = self.contract_states[symbol]
            time_key = 'time' if 'time' in bar else 'datetime'
            bar['datetime'] = self.parse_timestamp(bar[time_key])
            bar_date = bar['datetime'].date()

            if contract_state.current_date != bar_date:
                contract_state.current_date = bar_date
                contract_state.today_minute_bars = self._get_today_data(symbol, bar_date)
                contract_state.today_minute_bars['datetime'] = pd.to_datetime(contract_state.today_minute_bars['datetime'], utc=True)
                
                if contract_state.today_minute_bars['datetime'].dt.tz is None:
                    contract_state.today_minute_bars['datetime'] = contract_state.today_minute_bars['datetime'].dt.tz_localize('Asia/Shanghai')
                
                contract_state.today_minute_bars['datetime'] = contract_state.today_minute_bars['datetime'].dt.tz_convert('UTC')
                contract_state.position_manager = TradePositionManager()
                contract_state.last_trade_date = bar_date
                
                if not self.is_backtest:
                    self.last_news_time = None
                    self.news_summary = ""

            if not self._is_trading_time(bar['datetime']):
                return "hold", 0, ""

            contract_state.today_minute_bars = pd.concat([contract_state.today_minute_bars, bar.to_frame().T], ignore_index=True)

            news_updated = False
            if not self.is_backtest:
                news_updated = self._update_news(symbol, bar['datetime'])

            llm_input = self._prepare_llm_input(symbol, bar, self.news_summary if (not self.is_backtest and (news_updated or len(contract_state.today_minute_bars) == 1)) else "")
            
            llm_response = self.llm_client.one_chat(llm_input)
            trade_instruction, quantity, next_msg, trade_reason, trade_plan = self._parse_llm_output(llm_response)
            self._execute_trade(symbol, trade_instruction, quantity, bar, trade_reason, trade_plan)
            self._log_bar_info(symbol, bar, self.news_summary if news_updated else "", f"{trade_instruction} {quantity}", trade_reason, trade_plan)
            contract_state.last_msg = next_msg
            return trade_instruction, quantity, next_msg, trade_reason, trade_plan
        except Exception as e:
            self.logger.error(f"Error processing bar for {symbol}: {str(e)}", exc_info=True)
            self.logger.error(f"Problematic bar data: {bar}")
            return "hold", 0, "", "处理错误", "无交易计划"

    def process_bars(self, bars: Dict[str, pd.Series], news: Dict[str, str] = {}) -> Dict[str, Tuple[str, Union[int, str], str, str, str]]:
        results = {}
        for symbol, bar in bars.items():
            if symbol in self.contract_states:
                news_for_symbol = news.get(symbol, "")
                result = self.process_bar(symbol, bar, news_for_symbol)
                results[symbol] = result
            else:
                self.logger.warning(f"Received data for unsubscribed symbol: {symbol}")
        return results

    def get_position(self, symbol: str) -> int:
        if symbol in self.contract_states:
            return self.contract_states[symbol].position_manager.get_current_position()
        else:
            self.logger.warning(f"Attempted to get position for unsubscribed symbol: {symbol}")
            return 0

    def get_all_positions(self) -> Dict[str, int]:
        return {symbol: self.get_position(symbol) for symbol in self.contract_states}

    def get_total_profit(self, symbol: str) -> float:
        if symbol in self.contract_states:
            return self.contract_states[symbol].total_profit
        else:
            self.logger.warning(f"Attempted to get total profit for unsubscribed symbol: {symbol}")
            return 0.0

    def get_all_total_profits(self) -> Dict[str, float]:
        return {symbol: self.get_total_profit(symbol) for symbol in self.contract_states}

    def get_position_details(self, symbol: str) -> str:
        if symbol in self.contract_states:
            return self.contract_states[symbol].position_manager.get_position_details()
        else:
            self.logger.warning(f"Attempted to get position details for unsubscribed symbol: {symbol}")
            return "No position details available"

    def get_all_position_details(self) -> Dict[str, str]:
        return {symbol: self.get_position_details(symbol) for symbol in self.contract_states}