



import akshare as ak



def get_index_dict()->dict:
    result = {}
    index_stock_info_df = ak.index_stock_info()
    for row in index_stock_info_df.iterrows():
        result["index_code"] = result["display_name"]


index_code=get_index_dict()