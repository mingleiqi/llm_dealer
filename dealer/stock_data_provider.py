import logging
from typing import List, Dict, Tuple, Optional, Union ,Literal
import pandas as pd
from datetime import datetime, timedelta
import pytz
import os
import json
import akshare as ak
from core.llms._llm_api_client import LLMClient
import ta



class StockDataProvider:
    def __init__(self,llm_client:LLMClient ):
        self.llm_client = llm_client
        self.code_name_list = {}
        self.previous_trading_date_cache = None
        self.previous_trading_date_cache_time = None
        self.latest_trading_date_cache = None
        self.latest_trading_date_cache_time = None
        self.cash_flow_cache = {}
        self.profit_cache = {}
        self.balance_sheet_cache = {}
        self.forecast_cache = {}
        self.report_cache = {}
        self.comment_cache = {}
        self.historical_data_cache = {}

    def _fetch_trading_dates(self):
        # 获取当前时间
        now = datetime.now()

        # 定义今天的日期
        today_str = now.strftime("%Y%m%d")
        start_date_str = (now - timedelta(days=10)).strftime("%Y%m%d")

        # 获取最近10天的交易数据，假设使用上证指数（000001.SH）
        stock_data = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date=start_date_str, end_date=today_str, adjust="")

        # 提取交易日期
        trading_dates = stock_data['日期'].apply(lambda x: datetime.strptime(x, "%Y-%m-%d")).tolist()
        trading_dates.sort()
        return trading_dates

    def get_previous_trading_date(self) -> str:
        """
        获取最近一个交易日，不包含今天的日期
        返回格式：YYYYMMDD
        """
        now = datetime.now()
        
        # 检查缓存是否有效
        if self.previous_trading_date_cache and self.previous_trading_date_cache_time.date() == now.date():
            return self.previous_trading_date_cache

        trading_dates = self._fetch_trading_dates()

        # 如果最近交易日期是今天，则返回上一个交易日期
        if trading_dates[-1].strftime("%Y%m%d") == now.strftime("%Y%m%d"):
            previous_trading_date = trading_dates[-2]
        else:
            previous_trading_date = trading_dates[-1]

        self.previous_trading_date_cache = previous_trading_date.strftime("%Y%m%d")
        self.previous_trading_date_cache_time = now
        return self.previous_trading_date_cache
    
    def get_latest_trading_date(self) -> str:
        """
        获取最近一个交易日
        如果当前时间是9:30之后，则，最近包含今天，否则不包含
        返回格式：YYYYMMDD
        """
        now = datetime.now()
        cache_valid = False

        # 检查缓存是否有效
        if self.latest_trading_date_cache and self.latest_trading_date_cache_time.date() == now.date():
            if now.time() < datetime.strptime('09:30', '%H:%M').time():
                if self.latest_trading_date_cache_time.time() < datetime.strptime('09:30', '%H:%M').time():
                    cache_valid = True
            else:
                cache_valid = True

        if cache_valid:
            return self.latest_trading_date_cache

        trading_dates = self._fetch_trading_dates()
        include_today = now.time() >= datetime.strptime('09:30', '%H:%M').time()

        if include_today and trading_dates[-1].strftime("%Y%m%d") == now.strftime("%Y%m%d"):
            latest_trading_date = trading_dates[-1]
        else:
            latest_trading_date = trading_dates[-2] if trading_dates[-1].strftime("%Y%m%d") == now.strftime("%Y%m%d") else trading_dates[-1]

        self.latest_trading_date_cache = latest_trading_date.strftime("%Y%m%d")
        self.latest_trading_date_cache_time = now
        return self.latest_trading_date_cache

    def stock_zt_pool_zbgc_em(self,date:str=None):
        """
        炸板股池
            date	str 交易日  yyyymmdd
        返回值:
            名称	类型	描述
            序号	int32	-
            代码	object	-
            名称	object	-
            涨跌幅	float64	注意单位: %
            最新价	float64	-
            涨停价	float64	-
            成交额	int64	-
            流通市值	float64	-
            总市值	float64	-
            换手率	float64	注意单位: %
            涨速	int64	-
            首次封板时间	object	注意格式: 09:25:00
            炸板次数	int64	-
            涨停统计	int64	-
            振幅	object	-
            所属行业	object	-
        """
        if not date:
            date = self.get_previous_trading_date()
        return ak.stock_zt_pool_zbgc_em(date=date)

    def stock_zt_pool_sub_new_em(self,date:str=None):
        """
        次新股池
             date	str 交易日  yyyymmdd
        返回值:
            名称	类型	描述
            序号	int32	-
            代码	object	-
            名称	object	-
            涨跌幅	float64	注意单位: %
            最新价	float64	-
            涨停价	float64	-
            成交额	int64	-
            流通市值	float64	-
            总市值	float64	-
            转手率	float64	注意单位: %
            开板几日	int64	-
            开板日期	int64	-
            上市日期	int64	-
            是否新高	int64	-
            涨停统计	object	-
            所属行业	object	-
        """
        if not date:
            date = self.get_previous_trading_date()
        return ak.stock_zt_pool_sub_new_em(date=date)

    def stock_zt_pool_strong_em(self,date:str=None):
        """
        强势股池
            date	str 交易日  yyyymmdd
        返回值:
            名称	类型	描述
            序号	int32	-
            代码	object	-
            名称	object	-
            涨跌幅	float64	注意单位: %
            最新价	float64	-
            涨停价	float64	-
            成交额	int64	-
            流通市值	float64	-
            总市值	float64	-
            换手率	float64	注意单位: %
            涨速	float64	注意单位: %
            是否新高	int64	-
            量比	float64	-
            涨停统计	object	-
            入选理由	object	{'1': '60日新高', '2': '近期多次涨停', '3': '60日新高且近期多次涨停'}
            所属行业	object	-
        """
        if not date:
            date = self.get_previous_trading_date()
        return ak.stock_zt_pool_strong_em(date=date)

    def stock_zt_pool_previous_em(self,date:str=None):
        """
        昨日涨停股池
            date	str 交易日 yyyymmdd
        返回值:
            名称	类型	描述
            序号	int32	-
            代码	object	-
            名称	object	-
            涨跌幅	float64	注意单位: %
            最新价	int64	-
            涨停价	int64	-
            成交额	int64	-
            流通市值	float64	-
            总市值	float64	-
            换手率	float64	注意单位: %
            涨速	float64	注意单位: %
            振幅	float64	注意单位: %
            昨日封板时间	int64	注意格式: 09:25:00
            昨日连板数	int64	注意格式: 1 为首板
            涨停统计	object	-
            所属行业	object	-
        """
        if not date:
            date = self.get_previous_trading_date()
        return ak.stock_zt_pool_previous_em(date)

    def stock_changes_em(self,symbol:Literal['火箭发射', '快速反弹', '大笔买入', '封涨停板', '打开跌停板', '有大买盘', '竞价上涨', '高开5日线', '向上缺口', '60日新高', '60日大幅上涨', '加速下跌', '高台跳水', '大笔卖出', '封跌停板', '打开涨停板', '有大卖盘', '竞价下跌', '低开5日线', '向下缺口', '60日新低', '60日大幅下跌']='大笔买入'):
        """
        返回值：
            名称	类型	描述
            时间	object	-
            代码	object	-
            名称	object	-
            板块	object	-
            相关信息	object	注意: 不同的 symbol 的单位不同
        """

    def stock_dzjy_hygtj(self,symbol:Literal['近一月', '近三月', '近六月', '近一年']="近一月"):
        """
        活跃 A 股统计
        返回值:
            名称	类型	描述
            序号	int64	-
            证券代码	object	-
            证券简称	object	-
            最新价	float64	-
            涨跌幅	float64	注意单位: %
            最近上榜日	object	-
            上榜次数-总计	int64	-
            上榜次数-溢价	int64	-
            上榜次数-折价	int64	
            总成交额	float64	注意单位: 万元
            折溢率	float64	注意单位: 万元
            成交总额/流通市值	float64	-
            上榜日后平均涨跌幅-1日	float64	注意符号: %
            上榜日后平均涨跌幅-5日	float64	注意符号: %
            上榜日后平均涨跌幅-10日	float64	注意符号: %
            上榜日后平均涨跌幅-20日	float64	注意符号: %
        """
        return ak.stock_dzjy_hygtj()

    def stock_lhb_detail_daily_sina(self):
        """
        龙虎榜-每日详情
        返回：
            名称	类型	描述
            序号	int64	-
            股票代码	object	-
            股票名称	object	-
            收盘价	float64	注意单位: 元
            对应值	float64	注意单位: %
            成交量	float64	注意单位: 万股
            成交额	float64	注意单位: 万元
            指标	object	注意单位: 万元
        """
        date=self.get_previous_trading_date()
        return stock_lhb_detail_daily_sina(date)

    def get_latest_financial_report_date(self):
        # 当前日期
        today = datetime.today()
        year = today.year
        month = today.month

        # 定义财报发行日期
        report_dates = [
            datetime(year, 3, 31),
            datetime(year, 6, 30),
            datetime(year, 9, 30),
            datetime(year, 12, 31)
        ]

        # 查找最近的财报发行日期
        for report_date in reversed(report_dates):
            if today >= report_date:
                return report_date.strftime("%Y%m%d")

        # 如果当前日期在1月1日至3月30日之间，返回上一年的12月31日
        return datetime(year - 1, 12, 31).strftime("%Y%m%d")

    def stock_report_fund_hold(self,symbol:str):
        """
        输入参数:
            symbol	str	symbol="基金持仓"; choice of {"基金持仓", "QFII持仓", "社保持仓", "券商持仓", "保险持仓", "信托持仓"}
            date	str	date="20200630"; date="20200630"; 财报发布日期, xxxx-03-31, xxxx-06-30, xxxx-09-30, xxxx-12-31
        返回值:
            名称	类型	描述
            变动日期	object	-
            股东名称	object	
        """
        date = self.get_latest_financial_report_date()
        return ak.stock_report_fund_hold(symbol=symbol, date=date)

    def stock_market_desc(self):
        """
        获取市场总体描述信息，每个市场的市盈率，指数等信息
        """
        market_descriptions = []

        for market in markets:
            try:
                df = ak.stock_market_pe_lg(symbol=market)
                if not df.empty:
                    latest_data = df.iloc[-1]
                    if market == "科创版":
                        description = f"{market}最新市值: {latest_data['总市值']:.2f}亿元，市盈率: {latest_data['市盈率']:.2f}"
                    else:
                        description = f"{market}最新指数: {latest_data['指数']:.2f}，平均市盈率: {latest_data['平均市盈率']:.2f}"
                    market_descriptions.append(description)
                else:
                    market_descriptions.append(f"{market}无数据")
            except Exception as e:
                market_descriptions.append(f"{market}数据获取失败: {e}")

        return "当前市场整体概况: " + "; ".join(market_descriptions)

    def stock_a_all_pb(self):
        """
        返回值:
            名称	类型	描述
            date	object	日期
            middlePB	float64	全部A股市净率中位数
            equalWeightAveragePB	float64	全部A股市净率等权平均
            close	float64	上证指数
            quantileInAllHistoryMiddlePB	float64	当前市净率中位数在历史数据上的分位数
            quantileInRecent10YearsMiddlePB	float64	当前市净率中位数在最近10年数据上的分位数
            quantileInAllHistoryEqualWeightAveragePB	float64	当前市净率等权平均在历史数据上的分位数
            quantileInRecent10YearsEqualWeightAveragePB	float64	当前市净率等权平均在最近10年数据上的分位数
        """
        return ak.stock_a_all_pb()

    def stock_a_ttm_lyr(self):
        """
        返回值:
            名称	类型	描述
            date	object	日期
            middlePETTM	float64	全A股滚动市盈率(TTM)中位数
            averagePETTM	float64	全A股滚动市盈率(TTM)等权平均
            middlePELYR	float64	全A股静态市盈率(LYR)中位数
            averagePELYR	float64	全A股静态市盈率(LYR)等权平均
            quantileInAllHistoryMiddlePeTtm	float64	当前"TTM(滚动市盈率)中位数"在历史数据上的分位数
            quantileInRecent10YearsMiddlePeTtm	float64	当前"TTM(滚动市盈率)中位数"在最近10年数据上的分位数
            quantileInAllHistoryAveragePeTtm	float64	当前"TTM(滚动市盈率)等权平均"在历史数据上的分位数
            quantileInRecent10YearsAveragePeTtm	float64	当前"TTM(滚动市盈率)等权平均"在在最近10年数据上的分位数
            quantileInAllHistoryMiddlePeLyr	float64	当前"LYR(静态市盈率)中位数"在历史数据上的分位数
            quantileInRecent10YearsMiddlePeLyr	float64	当前"LYR(静态市盈率)中位数"在最近10年数据上的分位数
            quantileInAllHistoryAveragePeLyr	float64	当前"LYR(静态市盈率)等权平均"在历史数据上的分位数
            quantileInRecent10YearsAveragePeLyr	float64	当前"LYR(静态市盈率)等权平均"在最近10年数据上的分位数
            close	float64	沪深300指数
        """
        return ak.stock_a_ttm_lyr()

    def get_current_buffett_index(self):
        """
        获取当前巴菲特指数的最新数据
        
        返回值:
            一个字符串，包含以下信息：
            - 收盘价
            - 总市值
            - GDP
            - 近十年分位数
            - 总历史分位数
        """
        # 获取数据
        data = ak.stock_buffett_index_lg()
        
        # 获取最后一行数据
        latest_data = data.iloc[-1]
        
        # 将最后一行数据转换为字符串
        buffett_index_info = (
            f"当前巴菲特指数: "
            f"收盘价: {latest_data['收盘价']}, "
            f"总市值: {latest_data['总市值']}, "
            f"GDP: {latest_data['GDP']}, "
            f"近十年分位数: {latest_data['近十年分位数']}, "
            f"总历史分位数: {latest_data['总历史分位数']}"
        )
        
        return buffett_index_info

    def get_stock_a_indicators(self, symbol: str) -> str:
        """
        获取指定股票的A股个股指标的最新数据
        
        输入参数:
            symbol (str): 股票代码
            
        返回值:
            一个字符串，包含以下信息的描述：
            - 市盈率
            - 市盈率TTM
            - 市净率
            - 市销率
            - 市销率TTM
            - 股息率
            - 股息率TTM
            - 总市值
        """
        # 获取数据
        data = ak.stock_a_indicator_lg(symbol=symbol)
        
        # 获取最后一行数据
        latest_data = data.iloc[-1]
        
        # 将最后一行数据转换为字符串
        stock_indicators_info = (
            f"A股个股指标"
            f"股票代码: {symbol} 的最新A股个股指标: "
            f"市盈率: {latest_data['pe']}, "
            f"市盈率TTM: {latest_data['pe_ttm']}, "
            f"市净率: {latest_data['pb']}, "
            f"市销率: {latest_data['ps']}, "
            f"市销率TTM: {latest_data['ps_ttm']}, "
            f"股息率: {latest_data['dv_ratio']}, "
            f"股息率TTM: {latest_data['dv_ttm']}, "
            f"总市值: {latest_data['total_mv']}"
        )
        
        return stock_indicators_info

    def get_industry_pe_ratio(self, symbol: str, date: str = None) -> str:
        """
        获取指定日期和行业分类的行业市盈率数据
        
        输入参数:
            symbol (str): 行业分类，选择 {"证监会行业分类", "国证行业分类"}
            date (str): 交易日，格式为 "YYYYMMDD"。如果未提供，则使用最近的一个交易日。
            
        返回值:
            一个字符串，包含以下信息的描述：
            - 行业分类
            - 行业层级
            - 行业编码
            - 行业名称
            - 公司数量
            - 纳入计算公司数量
            - 总市值-静态
            - 净利润-静态
            - 静态市盈率-加权平均
            - 静态市盈率-中位数
            - 静态市盈率-算术平均
        """
        if not date:
            date = self.get_previous_trading_date()
        
        # 获取数据
        data = ak.stock_industry_pe_ratio_cninfo(symbol=symbol, date=date)
        
        # 获取最后一行数据
        latest_data = data.iloc[-1]
        
        # 将最后一行数据转换为字符串
        industry_pe_ratio_info = (
            f"行业分类: {latest_data['行业分类']}, "
            f"行业层级: {latest_data['行业层级']}, "
            f"行业编码: {latest_data['行业编码']}, "
            f"行业名称: {latest_data['行业名称']}, "
            f"公司数量: {latest_data['公司数量']}, "
            f"纳入计算公司数量: {latest_data['纳入计算公司数量']}, "
            f"总市值-静态: {latest_data['总市值-静态']}亿元, "
            f"净利润-静态: {latest_data['净利润-静态']}亿元, "
            f"静态市盈率-加权平均: {latest_data['静态市盈率-加权平均']}, "
            f"静态市盈率-中位数: {latest_data['静态市盈率-中位数']}, "
            f"静态市盈率-算术平均: {latest_data['静态市盈率-算术平均']}"
        )
        
        return industry_pe_ratio_info

    def stock_institute_recommend(self,indicator :Literal['最新投资评级', '上调评级股票', '下调评级股票', '股票综合评级', '首次评级股票', '目标涨幅排名', '机构关注度', '行业关注度', '投资评级选股']="投资评级选股"):
        """
        机构推荐池
        """
        return ak.stock_institute_recommend(symbol=indicator)

    def get_recent_recommendations_summary(self, symbol: str) -> str:
        """
        获取指定股票的最近半年的评级记录统计
        
        输入参数:
            symbol (str): 股票代码
            
        返回值:
            一个描述性的字符串，包含以下信息的统计：
            - 股票名称
            - 最近半年内的评级次数
            - 各种评级的次数统计（例如：买入、增持等）
            - 涉及的分析师数量
            - 涉及的评级机构数量
            - 目标价的最高值、最低值、平均值
            - 目标价的分布情况（最多的目标价区间）
        """
        # 获取数据
        data = ak.stock_institute_recommend_detail(symbol=symbol)
        
        # 计算最近半年的日期
        six_months_ago = datetime.now() - timedelta(days=180)
        
        # 过滤最近半年的数据
        recent_data = data[data['评级日期'] >= six_months_ago.strftime('%Y-%m-%d')]
        
        # 统计股票名称
        stock_name = recent_data['股票名称'].iloc[0] if not recent_data.empty else "未知"
        
        # 统计评级次数
        total_recommendations = recent_data.shape[0]
        
        # 统计各种评级的次数
        rating_counts = recent_data['最新评级'].value_counts().to_dict()
        
        # 统计涉及的分析师数量
        analysts = recent_data['分析师'].str.split(',').explode().unique()
        num_analysts = len(analysts)
        
        # 统计涉及的评级机构数量
        institutions = recent_data['评级机构'].unique()
        num_institutions = len(institutions)
        
        # 统计目标价
        target_prices = recent_data['目标价'].replace('NaN', np.nan).dropna().astype(float)
        if not target_prices.empty:
            max_target_price = target_prices.max()
            min_target_price = target_prices.min()
            avg_target_price = target_prices.mean()
            
            # 计算目标价的分布情况
            bins = [0, 10, 20, 30, 40, 50, 100, 200, 300, 400, 500]
            target_price_distribution = np.histogram(target_prices, bins=bins)
            most_common_range_index = np.argmax(target_price_distribution[0])
            most_common_range = f"{bins[most_common_range_index]}-{bins[most_common_range_index + 1]}"
        else:
            max_target_price = min_target_price = avg_target_price = most_common_range = "无数据"
        
        # 生成描述性的字符串
        recommendation_summary = (
            f"股票代码: {symbol}, 股票名称: {stock_name}\n"
            f"最近半年内的评级次数: {total_recommendations}\n"
            f"评级统计:\n"
        )
        
        for rating, count in rating_counts.items():
            recommendation_summary += f" - {rating}: {count}次\n"
        
        recommendation_summary += (
            f"涉及的分析师数量: {num_analysts}\n"
            f"涉及的评级机构数量: {num_institutions}\n"
            f"目标价统计:\n"
            f" - 最高目标价: {max_target_price}\n"
            f" - 最低目标价: {min_target_price}\n"
            f" - 平均目标价: {avg_target_price:.2f}\n"
            f" - 最多的目标价区间: {most_common_range}\n"
        )
        
        return recommendation_summary

    def stock_rank_forecast_cninfo(self,date:str=None):
        """
        投资评级
            date	str	date="20210910"; 交易日
        返回：
            名称	类型	描述
            证券代码	object	-
            证券简称	object	-
            发布日期	object	-
            研究机构简称	object	-
            研究员名称	object	-
            投资评级	object	-
            是否首次评级	object	-
            评级变化	object	-
            前一次投资评级	object	-
            目标价格-下限	float64	-
            目标价格-上限	float64	-
        """
        if not date:
            date = self.get_previous_trading_date()
        return ak.stock_rank_forecast_cninfo(date=date)
    
    def stock_financial_analysis_indicator(self,symbol:str,start_year:str):
        """
        财务指标
        输入参数:
            start_year	str	start_year="2020"; 开始查询的时间
        返回值:
            名称	类型	描述
            日期	object	-
            摊薄每股收益(元)	float64	-
            加权每股收益(元)	float64	-
            每股收益_调整后(元)	float64	-
            扣除非经常性损益后的每股收益(元)	float64	-
            每股净资产_调整前(元)	float64	-
            每股净资产_调整后(元)	float64	-
            每股经营性现金流(元)	float64	-
            每股资本公积金(元)	float64	-
            每股未分配利润(元)	float64	-
            调整后的每股净资产(元)	float64	-
            总资产利润率(%)	float64	-
            主营业务利润率(%)	float64	-
            总资产净利润率(%)	float64	-
            成本费用利润率(%)	float64	-
            营业利润率(%)	float64	-
            主营业务成本率(%)	float64	-
            销售净利率(%)	float64	-
            股本报酬率(%)	float64	-
            净资产报酬率(%)	float64	-
            资产报酬率(%)	float64	-
            销售毛利率(%)	float64	-
            三项费用比重	float64	-
            非主营比重	float64	-
            主营利润比重	float64	-
            股息发放率(%)	float64	-
            投资收益率(%)	float64	-
            主营业务利润(元)	float64	-
            净资产收益率(%)	float64	-
            加权净资产收益率(%)	float64	-
            扣除非经常性损益后的净利润(元)	float64	-
            主营业务收入增长率(%)	float64	-
            净利润增长率(%)	float64	-
            净资产增长率(%)	float64	-
            总资产增长率(%)	float64	-
            应收账款周转率(次)	float64	-
            应收账款周转天数(天)	float64	-
            存货周转天数(天)	float64	-
            存货周转率(次)	float64	-
            固定资产周转率(次)	float64	-
            总资产周转率(次)	float64	-
            总资产周转天数(天)	float64	-
            流动资产周转率(次)	float64	-
            流动资产周转天数(天)	float64	-
            股东权益周转率(次)	float64	-
            流动比率	float64	-
            速动比率	float64	-
            现金比率(%)	float64	-
            利息支付倍数	float64	-
            长期债务与营运资金比率(%)	float64	-
            股东权益比率(%)	float64	-
            长期负债比率(%)	float64	-
            股东权益与固定资产比率(%)	float64	-
            负债与所有者权益比率(%)	float64	-
            长期资产与长期资金比率(%)	float64	-
            资本化比率(%)	float64	-
            固定资产净值率(%)	float64	-
            资本固定化比率(%)	float64	-
            产权比率(%)	float64	-
            清算价值比率(%)	float64	-
            固定资产比重(%)	float64	-
            资产负债率(%)	float64	-
            总资产(元)	float64	-
            经营现金净流量对销售收入比率(%)	float64	-
            资产的经营现金流量回报率(%)	float64	-
            经营现金净流量与净利润的比率(%)	float64	-
            经营现金净流量对负债比率(%)	float64	-
            现金流量比率(%)	float64	-
            短期股票投资(元)	float64	-
            短期债券投资(元)	float64	-
            短期其它经营性投资(元)	float64	-
            长期股票投资(元)	float64	-
            长期债券投资(元)	float64	-
            长期其它经营性投资(元)	float64	-
            1年以内应收帐款(元)	float64	-
            1-2年以内应收帐款(元)	float64	-
            2-3年以内应收帐款(元)	float64	-
            3年以内应收帐款(元)	float64	-
            1年以内预付货款(元)	float64	-
            1-2年以内预付货款(元)	float64	-
            2-3年以内预付货款(元)	float64	-
            3年以内预付货款(元)	float64	-
            1年以内其它应收款(元)	float64	-
            1-2年以内其它应收款(元)	float64	-
            2-3年以内其它应收款(元)	float64	-
            3年以内其它应收款(元)	float64	-
        """
        return ak.stock_financial_analysis_indicator(symbol,indicator)
 
    def stock_financial_abstract_ths(self,symbol:str,indicator:Literal["按报告期", "按年度", "按单季度"]="按报告期"):
        """
        输入参数:
            symbol	str	股票代码
            indicator	str	indicator="按报告期"; choice of {"按报告期", "按年度", "按单季度"}
        """
        return ak.stock_financial_abstract_ths(symbol,indicator)

    def get_stock_balance_sheet_by_report_em(self,symbol:str):
        """
        输入参数:symbol	str	 股票代码
        返回值:
            名称	类型	描述
            -	-	319 项，不逐一列出
        """
        return ak.stock_balance_sheet_by_report_em(symbol)

    def get_stock_financial_report_sina(self,stock:str,symbol:Literal["资产负债表", "利润表", "现金流量表"]="现金流量表"):
        """
        输入参数:
                stock	str	stock="sh600600"; 带市场标识的股票代码
                symbol	str	symbol="现金流量表"; choice of {"资产负债表", "利润表", "现金流量表"}
        返回值:
            名称	类型	描述
            报告日	object	报告日期
            流动资产	object	-
            ...	object	-
            类型	object	-
            更新日期	object	-
        """

    def get_stock_individual_fund_flow_rank(self,indicator:str="今日"):
        """
        输入参数:indicator	str	indicator="今日"; choice {"今日", "3日", "5日", "10日"}
        返回值:
            名称	类型	描述
            序号	int64	-
            代码	object	-
            名称	object	-
            最新价	float64	-
            今日涨跌幅	float64	注意单位: %
            今日主力净流入-净额	float64	-
            今日主力净流入-净占比	float64	注意单位: %
            今日超大单净流入-净额	float64	-
            今日超大单净流入-净占比	float64	注意单位: %
            今日大单净流入-净额	float64	-
            今日大单净流入-净占比	float64	注意单位: %
            今日中单净流入-净额	float64	-
            今日中单净流入-净占比	float64	注意单位: %
            今日小单净流入-净额	float64	-
            今日小单净流入-净占比	float64	注意单位: %
        """
        return ak.stock_individual_fund_flow_rank(indicator=indicator)

    def get_stock_stock_fund_flow_individual(self,symbol:str,market:str="sh" ):
        """
        输入参数:stock	str	stock="000425"; 股票代码
                market	str	market="sh"; 上海证券交易所: sh, 深证证券交易所: sz, 北京证券交易所: bj
        返回值:
            名称	类型	描述
            序号	int32	-
            股票代码	int64	-
            股票简称	object	-
            最新价	float64	-
            涨跌幅	object	注意单位: %
            换手率	object	-
            流入资金	object	注意单位: 元
            流出资金	object	注意单位: 元
            净额	object	注意单位: 元
            成交额	object	注意单位: 元
            大单流入	object	注意单位: 元
        """
        return ak.stock_individual_fund_flow(indicator)

    def get_cash_flow_statement_summary(self) -> dict:
        """
        获取最近一个财报发行日期的现金流量表数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 股票简称
            - 净现金流
            - 净现金流同比增长
            - 经营性现金流净额
            - 经营性现金流净额占比
            - 投资性现金流净额
            - 投资性现金流净额占比
            - 融资性现金流净额
            - 融资性现金流净额占比
            - 公告日期
        """
        # 获取最近的财报发行日期
        date = self.get_latest_financial_report_date()

        # 检查缓存是否存在
        if date in self.cash_flow_cache:
            return self.cash_flow_cache[date]
        
        # 获取数据
        data = ak.stock_xjll_em(date=date)
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"股票简称: {row['股票简称']}, "
                f"净现金流: {row['净现金流-净现金流']}元, "
                f"净现金流同比增长: {row['净现金流-同比增长']}%, "
                f"经营性现金流净额: {row['经营性现金流-现金流量净额']}元, "
                f"经营性现金流净额占比: {row['经营性现金流-净现金流占比']}%, "
                f"投资性现金流净额: {row['投资性现金流-现金流量净额']}元, "
                f"投资性现金流净额占比: {row['投资性现金流-净现金流占比']}%, "
                f"融资性现金流净额: {row['融资性现金流-现金流量净额']}元, "
                f"融资性现金流净额占比: {row['融资性现金流-净现金流占比']}%, "
            )
            summary_dict[row['股票代码']] = description
        
        # 缓存结果
        self.cash_flow_cache[date] = summary_dict
        
        return summary_dict

    def get_profit_statement_summary(self) -> dict:
        """
        获取最近一个财报发行日期的利润表数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 股票简称
            - 净利润
            - 净利润同比
            - 营业总收入
            - 营业总收入同比
            - 营业总支出-营业支出
            - 营业总支出-销售费用
            - 营业总支出-管理费用
            - 营业总支出-财务费用
            - 营业总支出-营业总支出
            - 营业利润
            - 利润总额
            - 公告日期
        """
        date = self.get_latest_financial_report_date()

        # 检查缓存是否存在
        if date in self.profit_cache:
            return self.profit_cache[date]
        
        # 获取数据
        data = ak.stock_lrb_em(date=date)
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"股票简称: {row['股票简称']}, "
                f"净利润: {row['净利润']}元, "
                f"净利润同比: {row['净利润同比']}%, "
                f"营业总收入: {row['营业总收入']}元, "
                f"营业总收入同比: {row['营业总收入同比']}%, "
                f"营业总支出-营业支出: {row['营业总支出-营业支出']}元, "
                f"营业总支出-销售费用: {row['营业总支出-销售费用']}元, "
                f"营业总支出-管理费用: {row['营业总支出-管理费用']}元, "
                f"营业总支出-财务费用: {row['营业总支出-财务费用']}元, "
                f"营业总支出-营业总支出: {row['营业总支出-营业总支出']}元, "
                f"营业利润: {row['营业利润']}元, "
                f"利润总额: {row['利润总额']}元, "
            )
            summary_dict[row['股票代码']] = description
        
        # 缓存结果
        self.profit_cache[date] = summary_dict
        
        return summary_dict

    def get_balance_sheet_summary(self) -> dict:
        """
        获取最近一个财报发行日期的资产负债表数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 股票简称
            - 资产-货币资金
            - 资产-应收账款
            - 资产-存货
            - 资产-总资产
            - 资产-总资产同比
            - 负债-应付账款
            - 负债-总负债
            - 负债-预收账款
            - 负债-总负债同比
            - 资产负债率
            - 股东权益合计
            - 公告日期
        """
        date = self.get_latest_financial_report_date()

        # 检查缓存是否存在
        if date in self.balance_sheet_cache:
            return self.balance_sheet_cache[date]
        
        # 获取数据
        data = ak.stock_zcfz_em(date=date)
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"股票简称: {row['股票简称']}, "
                f"资产-货币资金: {row['资产-货币资金']}元, "
                f"资产-应收账款: {row['资产-应收账款']}元, "
                f"资产-存货: {row['资产-存货']}元, "
                f"资产-总资产: {row['资产-总资产']}元, "
                f"资产-总资产同比: {row['资产-总资产同比']}%, "
                f"负债-应付账款: {row['负债-应付账款']}元, "
                f"负债-总负债: {row['负债-总负债']}元, "
                f"负债-预收账款: {row['负债-预收账款']}元, "
                f"负债-总负债同比: {row['负债-总负债同比']}%, "
                f"资产负债率: {row['资产负债率']}%, "
                f"股东权益合计: {row['股东权益合计']}元, "
                f"公告日期: {row['公告日期']}"
            )
            summary_dict[row['股票代码']] = description
        
        # 缓存结果
        self.balance_sheet_cache[date] = summary_dict
        
        return summary_dict

    def get_stock_info(self,symbol:str)->pd.DataFrame:
        """
        输入参数:symbol	str	股票代码
        返回值:
            名称	类型	描述
            公司名称	object	-
            英文名称	object	-
            曾用简称	object	-
            A股代码	object	-
            A股简称	object	-
            B股代码	object	-
            B股简称	object	-
            H股代码	object	-
            H股简称	object	-
            入选指数	object	-
            所属市场	object	-
            所属行业	object	-
            法人代表	object	-
            注册资金	object	-
            成立日期	object	-
            上市日期	object	-
            官方网站	object	-
            电子邮箱	object	-
            联系电话	object	-
            传真	object	-
            注册地址	object	-
            办公地址	object	-
            邮政编码	object	-
            主营业务	object	-
            经营范围	object	-
            机构简介	object	-
        """
        return ak.stock_profile_cninfo(symbol=symbol)

    def get_stock_report(self,symbol:str):
        """
        输入参数:symbol	str	股票代码
        返回值:
            名称	类型	描述
            序号	int64	-
            股票代码	object	-
            股票简称	object	-
            报告名称	object	-
            东财评级	object	-
            机构	object	-
            近一月个股研报数	int64	-
            2023-盈利预测-收益	float64	-
            2023-盈利预测-市盈率	float64	-
            2024-盈利预测-收益	float64	-
            2024-盈利预测-市盈率	float64	-
            行业	object	-
            日期	object	-
        """
        return ak.stock_research_report_em(symbol)

    def get_financial_forecast_summary(self) -> dict:
        """
        获取最近一个财报发行日期的业绩预告数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 股票简称
            - 预测指标
            - 业绩变动
            - 预测数值
            - 业绩变动幅度
            - 业绩变动原因
            - 预告类型
            - 上年同期值
            - 公告日期
        """
        date = self.get_latest_financial_report_date()

        # 检查缓存是否存在
        if date in self.forecast_cache:
            return self.forecast_cache[date]
        
        # 获取数据
        data = ak.stock_yjyg_em(date=date)
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"股票简称: {row['股票简称']}, "
                f"预测指标: {row['预测指标']}, "
                f"业绩变动: {row['业绩变动']}, "
                f"预测数值: {row['预测数值']}元, "
                f"业绩变动幅度: {row['业绩变动幅度']}%, "
                f"业绩变动原因: {row['业绩变动原因']}, "
                f"预告类型: {row['预告类型']}, "
                f"上年同期值: {row['上年同期值']}元, "
                f"公告日期: {row['公告日期']}"
            )
            summary_dict[row['股票代码']] = description
        
        # 缓存结果
        self.forecast_cache[date] = summary_dict
        
        return summary_dict

    def get_financial_report_summary(self) -> dict:
        """
        获取最近一个财报发行日期的业绩报表数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 股票简称
            - 每股收益
            - 营业收入
            - 营业收入同比增长
            - 营业收入季度环比增长
            - 净利润
            - 净利润同比增长
            - 净利润季度环比增长
            - 每股净资产
            - 净资产收益率
            - 每股经营现金流量
            - 销售毛利率
            - 所处行业
            - 最新公告日期
        """
        date = self.get_latest_financial_report_date()

        # 检查缓存是否存在
        if date in self.report_cache:
            return self.report_cache[date]
        
        # 获取数据
        data = ak.stock_yjbb_em(date=date)
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"股票简称: {row['股票简称']}, "
                f"每股收益: {row['每股收益']}元, "
                f"营业收入: {row['营业收入-营业收入']}元, "
                f"营业收入同比增长: {row['营业收入-同比增长']}%, "
                f"营业收入季度环比增长: {row['营业收入-季度环比增长']}%, "
                f"净利润: {row['净利润-净利润']}元, "
                f"净利润同比增长: {row['净利润-同比增长']}%, "
                f"净利润季度环比增长: {row['净利润-季度环比增长']}%, "
                f"每股净资产: {row['每股净资产']}元, "
                f"净资产收益率: {row['净资产收益率']}%, "
                f"每股经营现金流量: {row['每股经营现金流量']}元, "
                f"销售毛利率: {row['销售毛利率']}%, "
                f"所处行业: {row['所处行业']}, "
                f"最新公告日期: {row['最新公告日期']}"
            )
            summary_dict[row['股票代码']] = description
        
        # 缓存结果
        self.report_cache[date] = summary_dict
        
        return summary_dict

    def stock_amount_of_increase(self,market:Literal["北向", "沪股通", "深股通"] ="北向" , indicator:Literal["今日排行", "3日排行", "5日排行", "10日排行", "月排行", "季排行", "年排行"] ="月排行"):
        """
        do not use this function
        """
        return ak.stock_hsgt_hold_stock_em(indicator=indicator, market=market)

    def get_stock_comments_summary(self) -> dict:
        """
        获取东方财富网-数据中心-特色数据-千股千评数据摘要
        
        返回值:
            一个字典，键是股票代码，值是描述性的字符串，包含以下信息的统计：
            - 名称
            - 最新价
            - 涨跌幅
            - 换手率
            - 市盈率
            - 主力成本
            - 机构参与度
            - 综合得分
            - 上升
            - 目前排名
            - 关注指数
            - 交易日
        """
        # 检查缓存是否存在
        if "stock_comments" in self.comment_cache:
            return self.comment_cache["stock_comments"]
        
        # 获取数据
        data = ak.stock_comment_em()
        
        # 生成描述性字符串的字典
        summary_dict = {}
        for index, row in data.iterrows():
            description = (
                f"名称: {row['名称']}, "
                f"最新价: {row['最新价']}, "
                f"涨跌幅: {row['涨跌幅']}%, "
                f"换手率: {row['换手率']}%, "
                f"市盈率: {row['市盈率']}, "
                f"主力成本: {row['主力成本']}, "
                f"机构参与度: {row['机构参与度']}%, "
                f"综合得分: {row['综合得分']}, "
                f"上升: {row['上升']}, "
                f"目前排名: {row['目前排名']}, "
                f"关注指数: {row['关注指数']}, "
                f"交易日: {row['交易日']}"
            )
            summary_dict[row['代码']] = description
        
        # 缓存结果
        self.comment_cache["stock_comments"] = summary_dict
        
        return summary_dict

    def get_main_business_description(self, symbol: str) -> str:
        """
        获取同花顺-主营介绍的数据，并返回描述性的字符串
        
        输入参数:
            symbol (str): 股票代码
            
        返回值:
            一个描述性的字符串，包含以下信息的统计：
            - 股票代码
            - 主营业务
            - 产品类型
            - 产品名称
            - 经营范围
        """
        # 获取数据
        data = ak.stock_zyjs_ths(symbol=symbol)
        
        if data.empty:
            return f"未找到股票代码 {symbol} 的主营介绍数据。"
        
        row = data.iloc[0]
        description = (
            f"股票代码: {row['股票代码']}\n"
            f"主营业务: {row['主营业务']}\n"
            f"产品类型: {row['产品类型']}\n"
            f"产品名称: {row['产品名称']}\n"
            f"经营范围: {row['经营范围']}"
        )
        
        return description

    def get_mainbussiness_more(self,symbol)->pd.DataFrame:
        """
        输入参数:
            symbol:str  股票代码
        返回值:
            名称	类型	描述
            股票代码	object	-
            报告日期	object	-
            分类类型	object	-
            主营构成	int64	-
            主营收入	float64	注意单位: 元
            收入比例	float64	-
            主营成本	float64	注意单位: 元
            成本比例	float64	-
            主营利润	float64	注意单位: 元
            利润比例	float64	-
            毛利率	float64	-
        """
        return ak.stock_zygc_em(symbol=symbol)

    def get_mainbussiness_mid(self,symbol:str)->pd.DataFrame:
        """
        输入参数:
            symbol:str  股票代码
        返回值:
            名称	类型	描述
            报告期	object	-
            内容	object	-
        """
        return ak.stock_zygc_ym(symbol=symbol)

    def get_manager_talk(self,symbol:str):
        """
        输入参数:
            symbol:str  股票代码
        返回值:
            名称	类型	描述
            报告期	object	-
            内容	object	-
        """
        return ak.stock_mda_ym(symbol)

    def get_historical_daily_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        返回值：Dict[symbol,list]
        list=名称	类型	描述
            日期	object	交易日
            股票代码	object	不带市场标识的股票代码
            开盘	float64	开盘价
            收盘	float64	收盘价
            最高	float64	最高价
            最低	float64	最低价
            成交量	int64	注意单位: 手
            成交额	float64	注意单位: 元
            振幅	float64	注意单位: %
            涨跌幅	float64	注意单位: %
            涨跌额	float64	注意单位: 元
            换手率	float64	注意单位: %
        """
        return ak.stock_zh_a_hist(symbol=symbol,period="daily", start_date=start_date, end_date=end_date)

    def get_code_name(self) -> Dict[str, str]:
        """
        返回值: Dict[代码,名称]
        """
        if self.code_name_list:
            return self.code_name_list  

        spot = ak.stock_info_a_code_name()
        for index, row in spot.iterrows():
            self.code_name_list[row["code"]] = row["name"]

    def get_news_updates(self, symbols: List[str],since_time: datetime) -> Dict[str, List[Dict]]:
        """
        返回值: Dict[symbol,list]
        list=名称	类型	描述
            关键词	object	-
            新闻标题	object	-
            新闻内容	object	-
            发布时间	object	-
            文章来源	object	-
            新闻链接	object	-
        """
        result = {}
        for symbol in symbols:
            news = ak.stock_news_em(symbol=symbol)
            news = news[news["发布时间"] > since_time]
            result[symbol] = news.to_dict(orient="list")

    def get_market_news(self) -> List[Dict]:
        """
        返回值:
            名称	类型	描述
            标题	object	-
            内容	object	-
            发布日期	object	-
            发布时间	object	-
        """
        return ak.stock_info_global_cls().to_dict(orient="list")

    def get_stock_minute(self,symbol:str, period='1'):
        """
        输入参数：
            symbol:str 股票代码
            period:str 周期，默认为1，可选值：1,5,15,30,60
        返回值:
            名称	类型	描述
            day	object	-
            open	float64	-
            high	float64	-
            low	float64	-
            close	float64	-
            volume	float64	-
        """
        return ak.stock_zh_a_minute(symbol=symbol, period=period)

    def get_index_data(self, index_symbols: List[str]) -> Dict[str, pd.DataFrame]:
        result = {}
        for index in index_symbols:
            data = ak.stock_zh_index_daily(symbol=index)
            result[index] = data
        return result
    
    def get_stock_news(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """
        输入参数:
            symbols: List[str]  股票代码列表
        返回值:
            名称	类型	描述
            关键词	object	-
            新闻标题	object	-
            新闻内容	object	-
            发布时间	object	-
            文章来源	object	-
            新闻链接	object	-
        """
        result = {}
        for symbol in symbols:
            news = ak.stock_news_em(symbol=symbol)
            
            result[symbol] = news.to_dict(orient="list")
    
    def get_main_cx_news(self)->pd.DataFrame:
        """
        输入参数
        无

        输出参数

        名称	类型	描述
        tag	object	-
        summary	object	-
        interval_time	object	-
        pub_time	object	-
        url	object	-
        """
        return ak.stock_news_main_cx()

    def stock_info_global(self):
        return ak.stock_info_global_ths()
    
    def summarize_historical_data(self, symbols: List[str]) -> dict:
        """
        汇总多个股票的历史数据，并生成描述性的字符串。
        
        输入参数:
            symbols: List[str] 股票代码列表
            
        返回值:
            一个字典，键是股票代码，值是描述性的字符串。
        """
        summary_dict = {}
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")

        for symbol in symbols:
            # 检查缓存
            if symbol in self.historical_data_cache:
                df = self.historical_data_cache[symbol]
            else:
                df = self.get_historical_daily_data(symbol, start_date, end_date)
                self.historical_data_cache[symbol] = df
            
            if df.empty:
                summary_dict[symbol] = "未找到数据"
                continue

            # 计算常用技术指标
            df['MA20'] = ta.trend.sma_indicator(df['收盘'], window=20)
            df['MA50'] = ta.trend.sma_indicator(df['收盘'], window=50)
            df['RSI'] = ta.momentum.rsi(df['收盘'], window=14)
            macd = ta.trend.MACD(df['收盘'])
            df['MACD'] = macd.macd()
            df['MACD_signal'] = macd.macd_signal()
            bb = ta.volatility.BollingerBands(df['收盘'], window=20, window_dev=2)
            df['BB_upper'] = bb.bollinger_hband()
            df['BB_lower'] = bb.bollinger_lband()

            # 获取数据统计
            latest_close = df['收盘'].iloc[-1]
            highest_close = df['收盘'].max()
            lowest_close = df['收盘'].min()
            avg_volume = df['成交量'].mean()
            latest_rsi = df['RSI'].iloc[-1]
            latest_macd = df['MACD'].iloc[-1]
            latest_macd_signal = df['MACD_signal'].iloc[-1]
            bb_upper = df['BB_upper'].iloc[-1]
            bb_lower = df['BB_lower'].iloc[-1]

            # 生成描述性的字符串
            description = (
                f"股票代码: {symbol}\n"
                f"最新收盘价: {latest_close}\n"
                f"最近半年内最高收盘价: {highest_close}\n"
                f"最近半年内最低收盘价: {lowest_close}\n"
                f"最近半年平均成交量: {avg_volume}\n"
                f"最新RSI(14): {latest_rsi}\n"
                f"最新MACD: {latest_macd}\n"
                f"最新MACD信号线: {latest_macd_signal}\n"
                f"布林带上轨: {bb_upper}\n"
                f"布林带下轨: {bb_lower}\n"
                f"MA20: {df['MA20'].iloc[-1]}\n"
                f"MA50: {df['MA50'].iloc[-1]}"
            )
            
            summary_dict[symbol] = description
        
        return summary_dict