

from dealer.stock_data_provider import StockDataProvider
from core.llms.simple_deep_seek_client import SimpleDeepSeekClient
from dealer.stock_query import StockQuery

def test():
    llm = SimpleDeepSeekClient()
    data = StockDataProvider(llm)
    query = StockQuery(llm,data)
    q = "科技股"
    selected_stocks = data.select_stocks_by_concept_board_query(q)
    print(selected_stocks)
    #result = query.query("查询过去一个月涨幅超过2%的科技股")
    #print(result)


if __name__ == "__main__":
    test()