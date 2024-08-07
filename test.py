

from dealer.xt_provider import XTDataProvider   


def test():
    provider = XTDataProvider()
    print(provider.get_all_code())
    
if __name__ == "__main__":
    test()