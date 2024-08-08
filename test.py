

from dealer.xt_provider import XTDataProvider   
from ta import add_all_ta_features
import akshare as ak
from dealer.baidu_news import BaiduNewsAPI

def test():
    api = BaiduNewsAPI()
    d = api.fetch_news(200)
    print(len(d))  


if __name__ == "__main__":
    test()