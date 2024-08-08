

from dealer.xt_provider import XTDataProvider   
from ta import add_all_ta_features
import akshare as ak

def test():
    table = ak.stock_buffett_index_lg()
    print(table)

if __name__ == "__main__":
    test()