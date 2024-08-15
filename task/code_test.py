

import json


def _format_result(llm_client, result: str) ->str:
    markdown_prompt = f"""
    请将以下查询结果转换为清晰、结构化的Markdown格式：
    结果:
    {result}
    请确保:
    1. 使用适当的Markdown标记（如标题、列表、表格等）来组织信息。
    2. 保留所有重要信息，但以更易读的方式呈现。
    3. 如果结果中包含数字数据，考虑使用表格形式展示。
    4. 为主要部分添加简短的解释或总结。
    5. 如果有多个部分，使用适当的分隔和标题。
    请直接返回Markdown格式的文本，无需其他解释。
    """
    
    
    markdown_result = ""
    markdown_result = llm_client.one_chat(markdown_prompt)
    return markdown_result

def runner():
    from core.utils.code_tools import code_tools
    from core.llms.simple_deep_seek_client import SimpleDeepSeekClient
    from core.llms.simple_claude import SimpleClaudeAwsClient
    from core.llms.mini_max_client import MiniMaxClient
    llm = SimpleDeepSeekClient()
    #llm.debug=True
    from dealer.stock_data_provider import StockDataProvider
    data = StockDataProvider(llm)
    code_tools.add_var("llm_client",llm)
    code_tools.add_var("stock_data_provider",data)
    stock_data_provider = code_tools["stock_data_provider"]
    llm_client = llm

    # Step 1: 获取热门股票和市场信息
    hot_stocks = stock_data_provider.get_baidu_hotrank(num=300) #这个数据是百度热门股票
    market_overview = stock_data_provider.stock_market_desc()   #市场描述包含每个市场的平均市盈率
    market_news = stock_data_provider.get_market_news_300()     #这是大概最近10个小时的新闻
    market_news_summary = stock_data_provider.summarizer_news(market_news,"总结行业热点，市场机会，市场风险点，以及可能影响短期走势的关键因素") #这是对新闻进行摘要和总结，修改文字内容可以修改摘要内容
    index_trend = stock_data_provider.summarize_historical_index_data(['000001', '399001', '399006'])  #这个是上证指数的走势，还可以添加和读取其他指数的走势，只需要在方括号里面添加指数代码

    # Step 2: 分析所有选出股票
    stock_analysis = {}
    for stock in hot_stocks:
        info = stock_data_provider.get_stock_info(stock)
        indicators = stock_data_provider.get_stock_a_indicators(stock)
        history = stock_data_provider.summarize_historical_data([stock])[stock]
        baidu_analysis = stock_data_provider.get_baidu_analysis_summary(stock)
        stock_news = stock_data_provider.get_one_stock_news(stock, num=3)  # 获取个股最新新闻
        stock_analysis[stock] = {
            'name': stock_data_provider.get_code_name()[stock],
            'info': info,
            'indicators': indicators,
            'history': history,
            'baidu_analysis': baidu_analysis,
            'news': stock_news
        }

    # Step 3: 短线潜力评估
    stock_evaluations = {}
    for stock_code, stock_data in stock_analysis.items():
        prompt = f"""
        请对股票{stock_data['name']}({stock_code})进行短线潜力分析，考虑以下因素：

        1. 基本面分析：
        - 股票信息：{stock_data['info']}
        - 股票指标：{stock_data['indicators']}
        - 百度分析摘要：{stock_data['baidu_analysis']}

        2. 技术面分析：
        - 历史数据摘要：{stock_data['history']}

        3. 市场环境：
        - 市场整体情况：{market_overview}
        - 市场新闻摘要：{market_news_summary}
        - 上证指数近期走势：{index_trend['000001']}
        - 深证成指近期走势：{index_trend['399001']}
        - 创业板指近期走势：{index_trend['399006']}

        4. 个股新闻：
        {stock_data['news']}

        请针对短线投资进行综合评估：
        1. 股票对市场情绪的敏感度（高/中/低）
        2. 股票与当前热点事件的相关性（强/中/弱）
        3. 股票的短期技术面走势（上升/震荡/下降）
        4. 股票的流动性（高/中/低，参考换手率）
        5. 短期催化剂或利好因素
        6. 潜在风险因素

        返回JSON格式，包含：
        - 'code': 股票代码
        - 'name': 股票名称
        - 'score': 短线潜力评分（0-100的整数）
        - 'attention': 市场关注度（0-100的整数）
        - 'sentiment': 市场情绪（看多/看空/中性）
        - 'liquidity': 流动性（高/中/低）
        - 'trend': 短期趋势（上升/震荡/下降）
        - 'catalyst': 主要催化剂或利好因素（简短描述）
        - 'risk': 主要风险因素（简短描述）
        - 'reason': 评分理由（不超过100字）
        """
        llm_response = llm_client.one_chat(prompt)
        evaluation = stock_data_provider.extract_json_from_text(llm_response)
        stock_evaluations[stock_code] = evaluation

    # Step 4: 筛选和排序
    sorted_stocks = sorted(stock_evaluations.values(), key=lambda x: (x['score'], x['attention']), reverse=True)
    recommended_stocks = sorted_stocks[:10]
    for stock in recommended_stocks:
        stock['composite_score'] = stock['score'] * 0.6 + stock['attention'] * 0.4

    # Step 5: 生成推荐列表和输出结果
    final_result = f"""
    # 短线股票推荐报告

    ## 市场整体情况概述
    {market_overview}

    ## 市场新闻摘要
    {market_news_summary}

    ## 主要指数走势
    1. 上证指数：{index_trend['000001']}
    2. 深证成指：{index_trend['399001']}
    3. 创业板指：{index_trend['399006']}

    ## 推荐的短线股票列表
    {json.dumps(recommended_stocks, indent=2, ensure_ascii=False)}

    ## 短线操作建议
    1. 密切关注个股新闻和行业动态，及时调整持仓。
    2. 设置合理的止盈止损位，控制风险。
    3. 关注大盘走势，不要逆势操作。
    4. 注意仓位控制，不要过度集中。

    ## 风险提示
    短线投资具有高风险性，以上推荐仅供参考。投资者应根据自身风险承受能力和投资目标，进行充分的研究和谨慎决策。市场瞬息万变，任何投资决策都需要投资者自行承担风险。
    """

    code_tools.add('output_result', final_result)
    markdown_result = _format_result(llm_client, final_result)
    print(markdown_result)
