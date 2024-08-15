

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
    from core.llms.mini_max_client import MiniMaxClient
    llm = MiniMaxClient()
    llm.debug=True
    from dealer.stock_data_provider import StockDataProvider
    data = StockDataProvider(llm)
    code_tools.add_var("llm_client",llm)
    code_tools.add_var("stock_data_provider",data)
    stock_data_provider = code_tools["stock_data_provider"]
    llm_client = llm

    # Step 1: 获取热门股票和市场信息
    hot_stocks = stock_data_provider.get_baidu_hotrank(num=200)
    market_overview = stock_data_provider.stock_market_desc()
    market_news = stock_data_provider.get_market_news_300()
    market_news_summary = stock_data_provider.summarizer_news(market_news)
    index_trend = stock_data_provider.summarize_historical_index_data(['000001'])['000001']

    # Step 2: 分析所有选出股票
    stock_analysis = {}
    for stock in hot_stocks:
        info = stock_data_provider.get_stock_info(stock)
        indicators = stock_data_provider.get_stock_a_indicators(stock)
        history = stock_data_provider.summarize_historical_data([stock])[stock]
        baidu_analysis = stock_data_provider.get_baidu_analysis_summary(stock)
        stock_analysis[stock] = {
            'name': stock_data_provider.get_code_name()[stock],
            'info': info,
            'indicators': indicators,
            'history': history,
            'baidu_analysis': baidu_analysis
        }

    # Step 3: 短线潜力评估
    stock_evaluations = {}
    for stock_code, stock_data in stock_analysis.items():
        prompt = f"""评估股票{stock_data['name']}({stock_code})的短线潜力，考虑以下因素：
        - 股票信息：{stock_data['info']}
        - 股票指标：{stock_data['indicators']}
        - 历史数据摘要：{stock_data['history']}
        - 百度分析摘要：{stock_data['baidu_analysis']}
        - 市场信息：{market_overview}
        - 市场新闻摘要：{market_news_summary}
        - 上证指数近期走势：{index_trend}
        短线投资特定要求：
        - 评估股票对市场情绪的敏感度（高/中/低）
        - 股票与当前热点事件的相关性（强/中/弱）
        - 股票的短期技术面走势（上升/震荡/下降）
        - 股票的流动性（以换手率为参考）
        返回JSON格式，包含：
        - 'code': 股票代码
        - 'name': 股票名称
        - 'score': 短线潜力评分（0-100的整数）
        - 'attention': 从评论摘要中提取的关注指数（数值）
        - 'reason': 评分理由(不超过50字)   """
        llm_response = llm_client.one_chat(prompt)
        evaluation = stock_data_provider.extract_json_from_text(llm_response)
        stock_evaluations[stock_code] = evaluation

    # Step 4: 筛选和排序
    sorted_stocks = sorted(stock_evaluations.values(), key=lambda x: (x['score'], x['attention']), reverse=True)
    recommended_stocks = sorted_stocks[:5]
    for stock in recommended_stocks:
        stock['composite_score'] = stock['score'] * 0.7 + stock['attention'] * 0.3

    # Step 5: 生成推荐列表和输出结果
    final_result = f"""市场整体情况概述：{market_overview}
    市场新闻摘要：{market_news_summary}
    上证指数近期走势：{index_trend}
    推荐的股票列表：
    {recommended_stocks}
    整体风险提示：短线投资具有高风险性，建议用户进行进一步的研究和谨慎决策"""

    code_tools.add('output_result', final_result)
    markdown_result = _format_result(llm_client,final_result)
    print(markdown_result)
