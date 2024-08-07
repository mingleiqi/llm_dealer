from xtquant import xtdata



class XTDataProvider:
    market_codes = ["SF","DF","ZF","IF","INE","GF"]
    def __init__(self):
        pass

    def get_all_code(self)->list:
        all = []
        for sector_name in XTDataProvider.market_codes:
            codes = xtdata.get_stock_list_in_sector(sector_name)
            all.extend(codes)
        return all
    def get_instrument_detail(self,code)->dict:
         return xtdata.get_instrument_detail(stock_code)
    def get_main_contract(self,code)->str:
        return xtdata.get_main_contract(code)