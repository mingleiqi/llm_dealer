from dealer.prompt_generate import PromptTemplateGenerator
from core.llms.simple_claude import SimpleClaudeAwsClient
from dealer.stock_data_provider import StockDataProvider

if __name__ == '__main__':
    llm = SimpleClaudeAwsClient()
    data = StockDataProvider(llm)
    generator = PromptTemplateGenerator(data,llm)
    result = generator.generate_prompt("新闻解读")
    print(result)