

from dealer.stock_data_provider import StockDataProvider
from core.llms.simple_deep_seek_client import SimpleDeepSeekClient
from core.llms.mini_max_client import MiniMaxClient
from dealer.stock_query_stream import StockQueryStream

def test():
    llm = MiniMaxClient()
    llm.debug=True
    data = StockDataProvider(llm)
    query = StockQueryStream(llm,data)

    result = query.query("从百度热榜挑选5支值得短线关注的股票")
    for chunk in result:
        print(chunk["content"],end="" ,flush=True)


if __name__ == "__main__":
    test()