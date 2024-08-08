from enum import Enum
import json
import os
import time
import numpy as np
import pandas as pd
import pytz
from ta import add_all_ta_features
from ta.trend import SMAIndicator, EMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
from ta.volatility import BollingerBands, AverageTrueRange
from typing import Dict, List, Tuple, Literal, Optional, Union
import logging
from logging import FileHandler
import re
from datetime import datetime, timedelta, time as dt_time
from dealer.trade_time import get_trading_end_time
import pytz
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

    def close_position(self, exit_price: float, exit_time: pd.Timestamp):
        self.exit_price = exit_price
        self.exit_time = exit_time

    def calculate_profit(self, current_price: float) -> float:
        price_diff = current_price - self.entry_price if self.position_type == PositionType.LONG else self.entry_price - current_price
        if self.exit_price is not None:
            price_diff = self.exit_price - self.entry_price if self.position_type == PositionType.LONG else self.entry_price - self.exit_price
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
        return {
            "realized_profit": realized_profit,
            "unrealized_profit": unrealized_profit,
            "total_profit": realized_profit + unrealized_profit
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
                details += f"  {i}. 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}\n"
        if short_positions:
            details += "空头:\n"
            for i, pos in enumerate(short_positions, 1):
                details += f"  {i}. 开仓价: {pos.entry_price:.2f}, 开仓时间: {pos.entry_time}\n"
        return details


class LLMDealer:
    def __init__(self, llm_client, symbol: str,data_provider: MainContractProvider,trade_rules:str="" ,
                 max_daily_bars: int = 60, max_hourly_bars: int = 30, max_minute_bars: int = 240,
                 backtest_date: Optional[str] = None, compact_mode: bool = False,
                 max_position: int = 1):
        self._setup_logging()
        self.trade_rules = trade_rules
        self.symbol = symbol
        self.night_closing_time = self._get_night_closing_time()
        self.backtest_date = backtest_date
        self.data_provider = data_provider
        self.llm_client = llm_client
        self.last_news_time = None
        self.news_summary = ""
        self.is_backtest = backtest_date is not None
        self.max_daily_bars = max_daily_bars
        self.max_hourly_bars = max_hourly_bars
        self.max_minute_bars = max_minute_bars
        self.max_position = max_position
        self.compact_mode = compact_mode
        self.backtest_date = backtest_date or datetime.now().strftime('%Y-%m-%d')
        
        self.today_minute_bars = pd.DataFrame()
        self.last_msg = ""
        self.position = 0  # 当前持仓量，正数表示多头，负数表示空头
        self.current_date = None
        self.last_trade_date = None  # 添加这个属性

        self.position_manager = TradePositionManager()
        self.total_profit = 0

        self.trading_hours = [
            (dt_time(9, 0), dt_time(11, 30)),
            (dt_time(13, 0), dt_time(15, 0)),
            (dt_time(21, 0), dt_time(23, 59)),
            (dt_time(0, 0), dt_time(2, 30))
        ]
        logging.basicConfig(level=logging.DEBUG)
        self.timezone = pytz.timezone('Asia/Shanghai') 
        

        self.daily_history = self._initialize_history('D')
        self.hourly_history = self._initialize_history('60')  
        self.minute_history = self._initialize_history('1')

    def _setup_logging(self):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        # Create a formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

        # Create a handler for console output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # Add the console handler to the logger
        self.logger.addHandler(console_handler)

        # Ensure the output directory exists
        os.makedirs('./output', exist_ok=True)

        # Create a file handler
        file_handler = logging.FileHandler(f'./output/log_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # Add the file handler to the logger
        self.logger.addHandler(file_handler)

    def _get_latest_news(self):
        if self.is_backtest:
            return pd.DataFrame()  # 回测模式下不读取新闻
        news_df = self.data_provider.get_futures_news(self.symbol, page_num=0, page_size=20)
        if news_df is not None and not news_df.empty:
            return news_df.sort_values('publish_time', ascending=False)
        return pd.DataFrame()

    def _summarize_news(self, news_df):
        if news_df.empty:
            return ""

        news_text = "\n".join(f"- {row['title']}" for _, row in news_df.iterrows())
        prompt = f"请将以下新闻整理成不超过200字的今日交易提示简报：\n\n{news_text}"
        
        summary = self.llm_client.one_chat(prompt)
        return summary[:200]  # Ensure the summary doesn't exceed 200 characters

    def _get_night_closing_time(self) -> Optional[dt_time]:
        night_end = get_trading_end_time(self.symbol, 'night')
        if isinstance(night_end, str) and ':' in night_end:
            hour, minute = map(int, night_end.split(':'))
            return dt_time(hour, minute)
        return None

    def _update_news(self, current_datetime):
        if self.is_backtest:
            return False  # 回测模式下不更新新闻

        try:
            news_df = self._get_latest_news()
            if news_df.empty:
                self.logger.info("No new news available")
                return False

            # 安全地解析新闻时间
            def safe_parse_time(time_str):
                try:
                    # 假设时间戳是毫秒级的
                    return pd.to_datetime(int(time_str) / 1000, unit='s', utc=True).tz_convert(beijing_tz)
                except ValueError:
                    # 如果失败，尝试直接解析字符串
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
                    self.logger.info(f"Updated news summary: {self.news_summary[:100]}...")
                    return True

            return False
        except Exception as e:
            self.logger.error(f"Error in _update_news: {str(e)}", exc_info=True)
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

    def _get_today_data(self, date: datetime.date) -> pd.DataFrame:
        self.logger.info(f"Fetching data for date: {date}")

        if self.is_backtest:
            today_data = self.data_provider.get_bar_data(self.symbol, '1', date.strftime('%Y-%m-%d'))
        else:
            today_data = self.data_provider.get_akbar(self.symbol, '1m')
            today_data = today_data[today_data.index.date == date]
            today_data = today_data.reset_index()

        self.logger.info(f"Raw data fetched: {len(today_data)} rows")

        if today_data.empty:
            self.logger.warning(f"No data returned from data provider for date {date}")
            return pd.DataFrame()

        # Ensure column names are consistent
        today_data = today_data.rename(columns={
            'open_interest': 'hold'
        })

        if self.is_backtest:
            filtered_data = today_data[today_data['trading_date'] == date]
        else:
            filtered_data = today_data[today_data['datetime'].dt.date == date]

        if filtered_data.empty:
            self.logger.warning(f"No data found for date {date} after filtering.")
        else:
            self.logger.info(f"Filtered data: {len(filtered_data)} rows")

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
        """预处理数据，处理空值和异常值"""
        # 将所有列转换为数值类型，非数值替换为 NaN
        numeric_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # 使用前向填充方法填充 NaN 值
        df = df.fillna(method='ffill')

        # 如果仍有 NaN 值（比如在数据开始处），则使用后向填充
        df = df.fillna(method='bfill')

        # 确保没有负值
        for col in numeric_columns:
            df[col] = df[col].clip(lower=0)

        return df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 5:  # 降低最小数据点要求
            return df
        
        try:
            df['sma_10'] = df['close'].rolling(window=min(10, len(df))).mean()
            df['ema_20'] = df['close'].ewm(span=min(20, len(df)), adjust=False).mean()
            df['rsi'] = RSIIndicator(close=df['close'], window=min(14, len(df))).rsi()
            
            macd = MACD(close=df['close'], window_slow=min(26, len(df)), window_fast=min(12, len(df)), window_sign=min(9, len(df)))
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            
            bollinger = BollingerBands(close=df['close'], window=min(20, len(df)), window_dev=2)
            df['bollinger_high'] = bollinger.bollinger_hband()
            df['bollinger_mid'] = bollinger.bollinger_mavg()
            df['bollinger_low'] = bollinger.bollinger_lband()
            
            df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=min(14, len(df))).average_true_range()
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
        
    def _initialize_history(self, period: Literal['1', '5', '15', '30', '60', 'D']) -> pd.DataFrame:
        try:
            frequency_map = {'1': '1m', '5': '5m', '15': '15m', '30': '30m', '60': '60m', 'D': 'D'}
            frequency = frequency_map[period]
            
            if self.is_backtest:
                df = self.data_provider.get_bar_data(self.symbol, period, self.backtest_date)
            else:
                df = self.data_provider.get_akbar(self.symbol, frequency)
            
            if df is None or df.empty:
                self.logger.warning(f"No data available for period {period}")
                return pd.DataFrame(columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest'])
            
            df = df.reset_index()
            
            # Ensure 'datetime' column is datetime type
            df['datetime'] = pd.to_datetime(df['datetime'])
            
            # Select and order the required columns
            columns_to_keep = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest']
            df = df[columns_to_keep]
            
            return self._limit_history(df, period)
        except Exception as e:
            self.logger.error(f"Error initializing history for period {period}: {str(e)}", exc_info=True)
            return pd.DataFrame(columns=['datetime', 'open', 'high', 'low', 'close', 'volume', 'open_interest'])

    def _limit_history(self, df: pd.DataFrame, period: str) -> pd.DataFrame:
        """根据时间周期限制历史数据的长度"""
        if df.empty:
            return df
        if period == 'D':
            return df.tail(self.max_daily_bars)
        elif period == '60':
            return df.tail(self.max_hourly_bars)
        else:
            return df.tail(self.max_minute_bars)

    def _update_histories(self, bar: pd.Series):
        """更新历史数据"""
        # 更新分钟数据
        self.minute_history = pd.concat([self.minute_history, bar.to_frame().T], ignore_index=True).tail(self.max_minute_bars)
        
        # 更新小时数据
        if bar['datetime'].minute == 0:
            self.hourly_history = pd.concat([self.hourly_history, bar.to_frame().T], ignore_index=True).tail(self.max_hourly_bars)
        
        # 更新日线数据
        if bar['datetime'].hour == 15 and bar['datetime'].minute == 0:
            daily_bar = bar.copy()
            daily_bar['datetime'] = daily_bar['datetime'].date()
            self.daily_history = pd.concat([self.daily_history, daily_bar.to_frame().T], ignore_index=True).tail(self.max_daily_bars)

    def _format_history(self) -> dict:
        """格式化历史数据，确保所有数据都被包含，并且格式一致"""
        
        def format_dataframe(df: pd.DataFrame, max_rows: int = None) -> str:
            if max_rows and len(df) > max_rows:
                df = df.tail(max_rows)  # 只保留最后 max_rows 行
            
            df_reset = df.reset_index(drop=True)
            formatted = df_reset.to_string(index=True, index_names=False, 
                                            formatters={
                                                'datetime': lambda x: x.strftime('%Y-%m-%d %H:%M') if isinstance(x, pd.Timestamp) else str(x),
                                                'open': '{:.2f}'.format,
                                                'high': '{:.2f}'.format,
                                                'low': '{:.2f}'.format,
                                                'close': '{:.2f}'.format
                                            })
            return formatted

        return {
            'daily': format_dataframe(self.daily_history, self.max_daily_bars),
            'hourly': format_dataframe(self.hourly_history, self.max_hourly_bars),
            'minute': format_dataframe(self.minute_history, self.max_minute_bars),
            'today_minute': format_dataframe(pd.DataFrame(self.today_minute_bars))
        }

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
    
    def _prepare_llm_input(self, bar: pd.Series, news: str) -> str:
        if self.today_minute_bars.empty:
            return "Insufficient data for LLM input"
        
        today_data = self._calculate_indicators(self.today_minute_bars)
        latest_indicators = today_data.iloc[-1]
        
        # Compress historical data
        daily_summary = self._compress_history(self.daily_history, 'D')
        hourly_summary = self._compress_history(self.hourly_history, 'H')
        minute_summary = self._compress_history(self.today_minute_bars, 'T')
        
        open_interest = bar.get('hold', 'N/A')
    
        position_description = "空仓"
        if self.position > 0:
            position_description = f"多头 {self.position} 手"
        elif self.position < 0:
            position_description = f"空头 {abs(self.position)} 手"
            
        profits = self.position_manager.calculate_profits(bar['close'])

        profit_info = f"""
        实际盈亏: {profits['realized_profit']:.2f}
        浮动盈亏: {profits['unrealized_profit']:.2f}
        总盈亏: {profits['total_profit']:.2f}
        """

        position_details = self.position_manager.get_position_details()

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

        上一次的消息: {self.last_msg}
        当前 bar index: {len(self.today_minute_bars) - 1}

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
        最大持仓: {self.max_position} 手

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

        请根据以上信息，给出交易指令或选择不交易（hold），并提供下一次需要的消息。
        请以JSON格式输出，包含以下字段：
        - trade_instruction: 交易指令（字符串，例如 "buy 2", "sell all", "short 1", "cover all" 或 "hold"）
        - next_message: 下一次需要的消息（字符串）
        - trade_reason: 此刻交易的理由（字符串）
        - trade_plan: 交易计划，包括止损区间和目标价格预测（字符串）

        请确保输出的JSON格式正确，并用```json 和 ``` 包裹。
        """
        return input_template

    def _format_history(self) -> dict:
        """格式化历史数据"""
        return {
            'daily': self.daily_history.to_string(index=False) if not self.daily_history.empty else "No daily data available",
            'hourly': self.hourly_history.to_string(index=False) if not self.hourly_history.empty else "No hourly data available",
        }

    def _parse_llm_output(self, llm_response: str) -> Tuple[str, Union[int, str], str, str, str]:
        """解析 LLM 的 JSON 输出"""
        try:
            # 提取 JSON 内容
            json_match = re.search(r'```json\s*(.*?)\s*```', llm_response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in the response")
            
            json_str = json_match.group(1)
            data = json.loads(json_str)
            
            # 使用 get 方法获取字段值，如果字段不存在则返回默认值
            trade_instruction = data.get('trade_instruction', 'hold').lower()
            next_msg = data.get('next_message', '')
            trade_reason = data.get('trade_reason', '')
            trade_plan = data.get('trade_plan', '')
            
            # 如果交易指令是 'hold'，我们不需要交易理由和计划
            if trade_instruction == 'hold':
                trade_reason = ''
                trade_plan = ''
            
            # 解析交易指令和数量
            instruction_parts = trade_instruction.split()
            action = instruction_parts[0]
            quantity = instruction_parts[1] if len(instruction_parts) > 1 else '1'
            
            if action not in ['buy', 'sell', 'short', 'cover', 'hold']:
                self.logger.warning(f"Invalid trade instruction: {action}. Defaulting to 'hold'.")
                return "hold", 1, next_msg, "", ""
            
            if quantity.lower() == 'all':
                quantity = 'all'
            else:
                try:
                    quantity = int(quantity)
                except ValueError:
                    quantity = 1  # 默认数量为1
            
            return action, quantity, next_msg, trade_reason, trade_plan
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parsing error: {e}")
            return "hold", 1, "", "JSON 解析错误", ""
        except Exception as e:
            self.logger.error(f"Error parsing LLM output: {e}")
            return "hold", 1, "", "解析错误", ""

    def _execute_trade(self, trade_instruction: str, quantity: Union[int, str], bar: pd.Series, trade_reason: str, trade_plan: str):
        current_datetime = bar['datetime']
        current_date = current_datetime.date()
        current_price = bar['close']

        self.logger.info(f"尝试执行交易: 指令={trade_instruction}, 数量={quantity}, 价格={current_price}")
        self.logger.info(f"交易理由: {trade_reason}")
        self.logger.info(f"交易计划: {trade_plan}")

        if self.last_trade_date != current_date:
            self._close_all_positions(current_price, current_datetime)
            self.last_trade_date = current_date

        if trade_instruction.lower() == 'hold':
            self.logger.info("保持当前仓位，不执行交易。")
            return

        action = trade_instruction.lower()
        qty = self.max_position if quantity == 'all' else int(quantity)

        current_position = self.position_manager.get_current_position()

        self.logger.info(f"当前仓位: {current_position}, 最大仓位: {self.max_position}")

        if action == "buy":
            max_buy = self.max_position - current_position
            actual_quantity = min(qty, max_buy)
            self.logger.info(f"尝试买入 {actual_quantity} 手")
            self.position_manager.open_position(current_price, actual_quantity, True, current_datetime, trade_plan)
        elif action == "sell":
            actual_quantity = self.position_manager.close_positions(current_price, qty, True, current_datetime)
            self.logger.info(f"尝试卖出 {actual_quantity} 手")
        elif action == "short":
            max_short = self.max_position + current_position
            actual_quantity = min(qty, max_short)
            self.logger.info(f"尝试做空 {actual_quantity} 手")
            self.position_manager.open_position(current_price, actual_quantity, False, current_datetime, trade_plan)
        elif action == "cover":
            actual_quantity = self.position_manager.close_positions(current_price, qty, False, current_datetime)
            self.logger.info(f"尝试买入平空 {actual_quantity} 手")
        else:
            self.logger.error(f"未知的交易动作: {action}")
            return

        self._force_close_if_needed(current_datetime, current_price)

        profits = self.position_manager.calculate_profits(current_price)
        self.total_profit = profits['total_profit']

        self.logger.info(f"执行交易后的仓位: {self.position_manager.get_current_position()}")
        self.logger.info(f"当前总盈亏: {self.total_profit:.2f}")
        self.logger.info(self.position_manager.get_position_details())

    def _close_all_positions(self, current_price: float, current_datetime: pd.Timestamp):
        self.position_manager.close_positions(current_price, float('inf'), True, current_datetime)
        self.position_manager.close_positions(current_price, float('inf'), False, current_datetime)

    def _force_close_if_needed(self, current_datetime: pd.Timestamp, current_price: float):
        day_closing_time = dt_time(14, 55)
        night_session_start = dt_time(21, 0)

        current_time = current_datetime.time()
        is_day_session = current_time < night_session_start and current_time >= dt_time(9, 0)
        is_night_session = current_time >= night_session_start or current_time < dt_time(9, 0)

        if is_day_session and current_time >= day_closing_time:
            self._close_all_positions(current_price, current_datetime)
            self.logger.info("日盘强制平仓")
        elif is_night_session and self.night_closing_time:
            # Check if it's within 5 minutes of the night closing time
            closing_window_start = (datetime.combine(datetime.min, self.night_closing_time) - timedelta(minutes=5)).time()
            if closing_window_start <= current_time <= self.night_closing_time:
                self._close_all_positions(current_price, current_datetime)
                self.logger.info("夜盘强制平仓")
            else:
                self.logger.info(f"夜盘交易，当前仓位：{self.position_manager.get_current_position()}")
        elif is_night_session and not self.night_closing_time:
            self.logger.info(f"夜盘交易（无强制平仓时间），当前仓位：{self.position_manager.get_current_position()}")

    def _get_today_bar_index(self, timestamp: pd.Timestamp) -> int:
        """
        Calculate the current bar index based on today's minute bars
        """
        if self.today_minute_bars.empty:
            return 0
        
        try:
            # Convert 'datetime' column to datetime type if it's not already
            if not pd.api.types.is_datetime64_any_dtype(self.today_minute_bars['datetime']):
                self.today_minute_bars['datetime'] = pd.to_datetime(self.today_minute_bars['datetime'], utc=True)
            
            # Now check if datetimes are timezone-aware
            if self.today_minute_bars['datetime'].dt.tz is None:
                # If not timezone-aware, assume they're in local time and make them timezone-aware
                self.today_minute_bars['datetime'] = self.today_minute_bars['datetime'].dt.tz_localize('Asia/Shanghai')
            
            # Convert to UTC
            self.today_minute_bars['datetime'] = self.today_minute_bars['datetime'].dt.tz_convert('UTC')
            
            # Ensure the input timestamp is in UTC
            utc_timestamp = timestamp.tz_convert('UTC')
            
            today_bars = self.today_minute_bars[self.today_minute_bars['datetime'].dt.date == utc_timestamp.date()]
            return len(today_bars)
        except Exception as e:
            self.logger.error(f"Error in _get_today_bar_index: {str(e)}", exc_info=True)
            return 0

    def _is_trading_time(self, timestamp: pd.Timestamp) -> bool:
        """
        判断给定时间是否在交易时间内
        """
        # 定义交易时间段（根据实际情况调整）
        trading_sessions = [
            ((9, 0), (11, 30)),   # 上午交易时段
            ((13, 0), (15, 0)),   # 下午交易时段
            ((21, 0), (23, 59)),  # 夜盘交易时段开始
            ((0, 0), (2, 30))     # 夜盘交易时段结束（跨天）
        ]
        
        time = timestamp.time()
        for start, end in trading_sessions:
            if start <= (time.hour, time.minute) <= end:
                return True
        return False

    def _log_bar_info(self, bar: Union[pd.Series, dict], news: str, trade_instruction: str):
        try:
            # Ensure the output directory exists
            os.makedirs('./output', exist_ok=True)

            # Create or get the file handler for the current date
            current_date = datetime.now().strftime('%Y%m%d')
            file_handler = next((h for h in self.logger.handlers if isinstance(h, FileHandler) and h.baseFilename.endswith(f'{current_date}.log')), None)
            
            if not file_handler:
                # If the file handler for the current date doesn't exist, create a new one
                file_path = f'./output/log{current_date}.log'
                file_handler = FileHandler(file_path)
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
                self.logger.addHandler(file_handler)

                # Remove old file handlers
                for handler in self.logger.handlers[:]:
                    if isinstance(handler, FileHandler) and not handler.baseFilename.endswith(f'{current_date}.log'):
                        self.logger.removeHandler(handler)
                        handler.close()

            # Convert bar to pd.Series if it's a dict
            if isinstance(bar, dict):
                bar = pd.Series(bar)

            # Format the log message
            log_msg = f"""
            时间: {pd.to_datetime(bar['datetime'])}, Bar Index: {self._get_today_bar_index(pd.to_datetime(bar['datetime']))}
            价格: 开 {bar['open']:.2f}, 高 {bar['high']:.2f}, 低 {bar['low']:.2f}, 收 {bar['close']:.2f}
            成交量: {bar['volume']}, 持仓量: {bar.get('open_interest', bar.get('hold', 'N/A'))}
            新闻: {news[:200] + '...' if news else '无新闻数据'}
            交易指令: {trade_instruction}
            交易理由: {trade_reason}
            交易计划: {trade_plan}
            当前持仓: {self.position_manager.get_current_position()}
            盈亏情况:
            {self.position_manager.calculate_profits(bar['close'])}
            {self.position_manager.get_position_details()}
            """

            # Log to file (DEBUG level includes all information)
            self.logger.debug(log_msg)

            # Log to console only if there's a trade instruction (excluding 'hold')
            if trade_instruction.lower() != 'hold':
                console_msg = f"时间: {pd.to_datetime(bar['datetime'])}, 价格: {bar['close']:.2f}, 交易指令: {trade_instruction}, 交易理由: {trade_reason[:50]}..., 当前持仓: {self.position_manager.get_current_position()}"
                self.logger.info(console_msg)

        except Exception as e:
            self.logger.error(f"Error in _log_bar_info: {str(e)}", exc_info=True)

    def parse_timestamp(self, timestamp):
        """解析时间戳"""
        self.logger.debug(f"Attempting to parse timestamp: {timestamp}")
        try:
            # 尝试多种可能的时间戳格式
            if isinstance(timestamp, (int, float)):
                # 如果时间戳是以毫秒为单位
                if timestamp > 1e12:
                    # 检查时间戳是否超出合理范围（2262年之后）
                    if timestamp > 9999999999999:
                        self.logger.warning(f"Abnormally large timestamp detected: {timestamp}")
                        # 尝试将其解释为纳秒级时间戳
                        try:
                            return pd.Timestamp(timestamp, unit='ns').tz_localize(beijing_tz)
                        except Exception:
                            self.logger.error(f"Failed to parse abnormally large timestamp: {timestamp}")
                            return datetime.now(beijing_tz)
                    return datetime.fromtimestamp(timestamp / 1000, tz=beijing_tz)
                # 如果时间戳是以秒为单位
                else:
                    return datetime.fromtimestamp(timestamp, tz=beijing_tz)
            elif isinstance(timestamp, str):
                # 尝试使用dateutil解析字符串格式的时间戳
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
            # 如果所有方法都失败，返回当前时间作为后备选项
            self.logger.warning("Using current time as fallback")
            return datetime.now(beijing_tz)

    def process_bar(self, bar: pd.Series, news: str = "") -> Tuple[str, Union[int, str], str]:
        try:
            # 确保使用正确的时间戳键
            time_key = 'time' if 'time' in bar else 'datetime'
            bar['datetime'] = self.parse_timestamp(bar[time_key])
            bar_date = bar['datetime'].date()

            if self.current_date != bar_date:
                self.current_date = bar_date
                self.today_minute_bars = self._get_today_data(bar_date)
                # Ensure the datetime column is in datetime format and timezone-aware
                self.today_minute_bars['datetime'] = pd.to_datetime(self.today_minute_bars['datetime'], utc=True)
                
                # If the datetimes are not timezone-aware, assume they're in local time and make them timezone-aware
                if self.today_minute_bars['datetime'].dt.tz is None:
                    self.today_minute_bars['datetime'] = self.today_minute_bars['datetime'].dt.tz_localize('Asia/Shanghai')
                
                # Convert to UTC
                self.today_minute_bars['datetime'] = self.today_minute_bars['datetime'].dt.tz_convert('UTC')
                self.position = 0
                self.last_trade_date = bar_date
                
                if not self.is_backtest:
                    self.last_news_time = None
                    self.news_summary = ""

            if not self._is_trading_time(bar['datetime']):
                return "hold", 0, ""

            self.today_minute_bars = pd.concat([self.today_minute_bars, bar.to_frame().T], ignore_index=True)

            news_updated = False
            if not self.is_backtest:
                news_updated = self._update_news(bar['datetime'])

            llm_input = self._prepare_llm_input(bar, self.news_summary if (not self.is_backtest and (news_updated or len(self.today_minute_bars) == 1)) else "")
            
            llm_response = self.llm_client.one_chat(llm_input)
            trade_instruction, quantity, next_msg, trade_reason, trade_plan = self._parse_llm_output(llm_response)
            self._execute_trade(trade_instruction, quantity, bar, trade_reason, trade_plan)
            self._log_bar_info(bar, self.news_summary if news_updated else "", f"{trade_instruction} {quantity}", trade_reason, trade_plan)
            self.last_msg = next_msg
            return trade_instruction, quantity, next_msg, trade_reason, trade_plan
        except Exception as e:
            self.logger.error(f"Error processing bar: {str(e)}", exc_info=True)
            self.logger.error(f"Problematic bar data: {bar}")
            return "hold", 0, "", "处理错误", "无交易计划"
