

from dealer.stock_data_provider import StockDataProvider
from core.llms.simple_deep_seek_client import SimpleDeepSeekClient
from dealer.stock_query import StockQuery

def runner():
    llm = SimpleDeepSeekClient()
    data = StockDataProvider(llm)
    query = StockQuery(llm,data)

    result = query.query("从百度热榜挑选5支值得短线关注的股票")
    print(result)