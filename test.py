

from dealer.xt_provider import XTDataProvider   
from ta import add_all_ta_features

def test():
    provider = XTDataProvider()
    print(provider.get_all_code())

if __name__ == "__main__":
    test()