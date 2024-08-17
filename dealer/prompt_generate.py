import re
from typing import Optional

class PromptTemplateGenerator:
    def __init__(self, stock_data_provider, llm_client):
        self.stock_data_provider = stock_data_provider
        self.llm_client = llm_client

    def generate_prompt(self, query: str) -> str:
        provider_description = self.stock_data_provider.get_self_description()

        initial_prompt = f"""
        请根据以下查询生成一个详细的提示词模板：

        查询: {query}

        可用的数据提供方法:
        {provider_description}

        请生成一个包含以下内容的提示词模板：
        1. 查询目的的明确描述
        2. 需要使用的数据提供方法及其参数
        3. 数据分析和处理步骤
        4. 预期输出的格式和内容
        5. 任何特殊考虑或注意事项

        请确保模板清晰、结构化，并充分利用可用的数据提供方法。
        使用 markdown 格式来组织模板结构。
        结果以```markdown ```包裹，不用添加额外解释

        以下是一个示例模板：

        ```markdown
        ### 个股行情解读模板

        1. 股票代码获取

        - 使用 `search_stock_code(stock_name)` 获取股票代码

        2. 数据收集

        对于获取的股票代码 `stock_code`，收集以下数据：

        - 使用 `get_stock_info(stock_code)` 获取股票基本信息
        - 使用 `get_latest_stock_data(stock_code)` 获取最新行情数据
        - 使用 `get_historical_daily_data(stock_code, start_date, end_date)` 获取最近30个交易日的历史数据
        - 使用 `get_stock_a_indicators(stock_code)` 获取A股个股指标
        - 使用 `get_one_stock_news(stock_code, num=5)` 获取最新的5条相关新闻
        - 使用 `get_baidu_analysis_summary(stock_code)` 获取百度分析摘要
        - 使用 `get_stock_comments_summary()` 获取该股票的千股千评数据
        - 使用 `get_industry_pe_ratio("证监会行业分类", date)` 获取行业市盈率数据

        3. 数据分析

        使用 LLM 分析收集到的数据，生成个股行情解读。提示词如下：
        为一位专业的股票分析师，请根据以下信息对 [股票代码] [股票名称] 的近期行情进行全面解读：

        股票基本信息：
        [插入 get_stock_info() 的结果]
        最新行情数据：
        [插入 get_latest_stock_data() 的结果]
        近30个交易日历史数据摘要：
        [插入 get_historical_daily_data() 的摘要统计，包括价格范围、平均成交量等]
        A股个股指标：
        [插入 get_stock_a_indicators() 的结果]
        最新相关新闻：
        [插入 get_one_stock_news() 的结果]
        百度分析摘要：
        [插入 get_baidu_analysis_summary() 的结果]
        千股千评数据：
        [插入 get_stock_comments_summary() 中该股票的数据]
        行业市盈率数据：
        [插入 get_industry_pe_ratio() 的结果]

        请提供以下分析：

        股价走势分析（200字以内）：分析近期股价走势，包括关键支撑位和压力位，以及可能的突破点。
        成交量分析（150字以内）：解读成交量变化，评估买卖双方力量对比。
        基本面评估（200字以内）：基于公司基本面信息和行业数据，评估公司当前估值水平和增长潜力。
        技术指标解读（200字以内）：解读主要技术指标（如 MACD、KDJ、RSI 等）的信号，预判可能的走势。
        消息面影响（150字以内）：分析近期新闻对股价的潜在影响。
        行业对比（150字以内）：将该股票与行业平均水平对比，评估其相对优势或劣势。
        风险提示（100字以内）：指出投资该股票可能面临的主要风险。
        投资建议（150字以内）：基于以上分析，给出短期（1-2周）和中期（1-3个月）的投资建议。

        请确保您的分析客观、全面，并提供有见地的洞察。您的解读将帮助投资者理解该股票的近期表现并为投资决策提供参考。
        请以JSON格式返回您的分析结果，包含上述8个字段。

        4. 生成报告

        基于LLM的分析结果，再次调用LLM生成最终的个股行情解读报告。报告结构如下：

        1. 股票概况
        - 基本信息
        - 最新行情数据

        2. 走势分析
        - 近期股价走势
        - 成交量分析
        - 技术指标解读

        3. 基本面评估
        - 公司基本面
        - 行业对比分析
        - 估值水平评估

        4. 消息面分析
        - 近期相关新闻
        - 消息对股价的影响

        5. 风险与机会
        - 主要风险因素
        - 潜在投资机会

        6. 投资建议
        - 短期操作建议
        - 中期投资策略

        5. 注意事项

        - 确保使用最新的股票数据进行分析
        - 保持分析的客观性，避免过度乐观或悲观的偏见
        - 关注个股的特定因素，如公司基本面、行业地位等
        - 将技术分析与基本面分析相结合
        - 考虑市场整体环境对个股的影响
        - 提供具体、可操作的投资建议，但同时提醒投资者注意风险
        - 使用清晰、易懂的语言，避免过于专业的术语
        ```

        请基于上述指南和示例，为给定的查询生成一个适当的提示词模板。
        """

        initial_template = self.llm_client.one_chat(initial_prompt)
        markdown_content = self._extract_markdown(initial_template)
        optimized_template = self._optimize_template(markdown_content, query)

        return optimized_template

    def _extract_markdown(self, content: str) -> str:
        markdown_pattern = r'```markdown\s*([\s\S]*?)\s*```'
        match = re.search(markdown_pattern, content)
        return match.group(1) if match else content

    def _optimize_template(self, template: str, query: str) -> str:
        # Step 1: Chain of Thought (COT)
        cot_prompt = f"""
        请对以下提示词模板进行分析和改进，使用思维链（Chain of Thought）技术：

        原始查询: {query}

        原始模板:
        {template}

        请执行以下步骤，并详细解释您的思考过程：

        1. 分析模板的每个部分，说明它如何满足查询需求。
        2. 识别可能的改进点，如遗漏的重要信息、步骤的逻辑顺序等。
        3. 考虑如何使模板更加清晰、全面和有效。
        4. 提出具体的改进建议。

        请提供详细的分析和建议。
        """

        cot_analysis = self.llm_client.one_chat(cot_prompt)

        # Step 2: Self-Reflection
        reflection_prompt = f"""
        请对以下思维链分析进行自我反思，并提出进一步的改进建议：

        原始查询: {query}

        原始模板:
        {template}

        思维链分析:
        {cot_analysis}

        请执行以下步骤：

        1. 评估思维链分析的质量和完整性。
        2. 识别分析中可能存在的偏见或逻辑缺陷。
        3. 考虑是否有任何重要的角度或方法被忽视。
        4. 基于这些反思，提出额外的改进建议。

        请提供您的自我反思结果和最终的改进建议。
        """

        reflection_result = self.llm_client.one_chat(reflection_prompt)

        # Step 3: Apply improvements
        final_optimization_prompt = f"""
        请基于原始模板、思维链分析和自我反思的结果，生成一个优化后的提示词模板：

        原始查询: {query}

        原始模板:
        {template}

        思维链分析:
        {cot_analysis}

        自我反思和改进建议:
        {reflection_result}

        请生成一个优化后的提示词模板，确保：
        1. 充分吸收思维链分析和自我反思中的有效建议
        2. 模板结构清晰，易于理解和执行
        3. 充分利用可用的数据提供方法
        4. 全面覆盖查询需求
        5. 包含必要的分析步骤和注意事项

        请使用 markdown 格式提供优化后的模板。
        结果以```markdown  ```包裹，不要添加如何解释
        """

        optimized_template = self.llm_client.one_chat(final_optimization_prompt)
        return self._extract_markdown(optimized_template)