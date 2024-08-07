
from datetime import datetime, timedelta
import hashlib
import random
import re
import time
from typing import List, Literal, Optional
import akshare as ak
import pandas as pd
import requests
from core.utils.single_ton import Singleton
from dealer.lazy import lazy
rq = None
from core.config import get_key
rq_user = get_key('rq_user')
rq_pwd = get_key('rq_pwd')
if rq_user and rq_pwd:
    rq = lazy("rqdatac")
    rq.init(rq_user,rq_pwd)

from core.tushare_doc.ts_code_matcher import StringMatcher

class MainContractGetter(StringMatcher, metaclass=Singleton):
    def __init__(self):
        df_path =  './json/main_contract_cache.pickle'
        index_cache = './json/main_contract_index_cache.pickle'
        df = pd.read_pickle(df_path)
        super().__init__(df, index_cache=index_cache, index_column='content', result_column='symbol')
    def __getitem__(self, query):
        return self.rapidfuzz_match(query)


class MainContractProvider:
    def __init__(self) -> None:
        self.code_getter = MainContractGetter()
    
    def get_bar_data(self, name: str, period: Literal['1', '5', '15', '30', '60', 'D'] = '1', date: Optional[str] = None):
        """
        获取期货合约的bar数据
        
        :param name: 合约名称
        :param period: 时间周期，默认为'1'（1分钟）
        :param date: 回测日期，格式为'YYYY-MM-DD'，如果不提供则使用当前日期
        :return: DataFrame包含bar数据
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        end_date = datetime.strptime(date, '%Y-%m-%d')
        if period == 'D':
            start_date = end_date - timedelta(days=365)  # 获取一年的日线数据
        else:
            start_date = end_date - timedelta(days=5)  # 获取5天的分钟数据
        
        frequency_map = {'1': '1m', '5': '5m', '15': '15m', '30': '30m', '60': '60m', 'D': '1d'}
        frequency = frequency_map[period]
        
        code = self.code_getter[name]
        if code.endswith('0'):
            code = code[:-1]
        
        df = self.get_rqbar(code, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), frequency)
        
        if period != 'D':
            df = df.reset_index()
            df = df.rename(columns={'datetime': 'datetime', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume', 'open_interest': 'hold'})
        else:
            df = df.reset_index()
            #df['date'] = df['datetime'].dt.date
            df = df.rename(columns={'date': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume', 'open_interest': 'hold'})
            #df = df.drop(columns=['datetime'])
        
        return df

    def get_main_contract(self):
        df = ak.futures_display_main_sina()
        df["content"] = df['symbol'] +'.'+df['exchange']+','+ df['name']
        return df   

    def make_main_chache(self):
        df = self.get_main_contract()
        df.to_pickle('./json/main_contract_cache.pickle')
        from core.tushare_doc.ts_code_matcher import StringMatcher
        matcher = StringMatcher(df, index_cache='./json/main_contract_index_cache.pickle', index_column='content', result_column='symbol')
    
    def get_shment_news(self, symbol: str = '全部'):
        return ak.futures_news_shmet(symbol=symbol)

    def generate_acs_token(self):
        current_time = int(time.time() * 1000)
        random_num = random.randint(1000000000000000, 9999999999999999)  # 16位随机数
        
        part1 = str(current_time)
        part2 = str(random_num)
        part3 = "1"
        
        token = f"{part1}_{part2}_{part3}"
        
        md5 = hashlib.md5()
        md5.update(token.encode('utf-8'))
        hash_value = md5.hexdigest()
        
        # 添加额外的随机字符串来增加长度
        extra_chars = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=20))
        
        final_token = f"{token}_{hash_value}_{extra_chars}"
        
        return final_token   
    
    def get_futures_news(self, code: str = 'SC0', page_num: int = 0, page_size: int = 20) -> Optional[pd.DataFrame]:
        code = f"{code[:-1]}888" if code.endswith('0') else f"{code}888"
        url = 'https://finance.pae.baidu.com/vapi/getfuturesnews'
        
        headers = {
            'accept': 'application/vnd.finance-web.v1+json',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'acs-token': self.generate_acs_token(),
            'origin': 'https://gushitong.baidu.com',
            'referer': 'https://gushitong.baidu.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0',
            'sec-ch-ua': '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
        }
        
        cookies = {
            'BAIDUID': '564AD52829EF1290DDC1A20DCC14F220:FG=1',
            'BAIDUID_BFESS': '564AD52829EF1290DDC1A20DCC14F220:FG=1',
            'BIDUPSID': '564AD52829EF1290DDC1A20DCC14F220',
            'PSTM': '1714397940',
            'ZFY': '3ffAdSTQ3amiXQ393UWe0Uy1s70:BPIai4AGEBTM6yIQ:C',
            'H_PS_PSSID': '60275_60287_60297_60325',
            'BDUSS': 'X56Q3pvU1ZoNFBUaVZmWHh5QjFMQWRaVzNWcXRMc0NESTJwQ25wdm9RYlVJYnRtRVFBQUFBJCQAAAAAAAAAAAEAAACgejQAd3h5MmFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANSUk2bUlJNma',
            'BDUSS_BFESS': 'X56Q3pvU1ZoNFBUaVZmWHh5QjFMQWRaVzNWcXRMc0NESTJwQ25wdm9RYlVJYnRtRVFBQUFBJCQAAAAAAAAAAAEAAACgejQAd3h5MmFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANSUk2bUlJNma',
            'ab_sr': '1.0.1_MTFlOTZiMTRlYjEyYTliZGU4YWFkMWIzMzkxYjdlOTJjNWY1NDM1MzZkZDQ5NTlhOGQwZDE3NWJkZjJmY2NmY2RkYWVkZTcyYTVhNDRmNjg4OGEzYjMzZGUzYTczMzhhNWZhNjRiOWE2YTJjNWZmNzNhNTEwMWQwODYwZDZkNmUzMjg3Yjc0NGM5Y2M0MjViNDY5NzU4MWQzZDZjMzViMw=='
        }
        
        params = {
            'code': code,
            'pn': page_num,
            'rn': page_size,
            'finClientType': 'pc'
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, cookies=cookies)
            response.raise_for_status()  # Raises a HTTPError if the status is 4xx, 5xx
            
            data = response.json()
            
            if 'Result' in data and isinstance(data['Result'], list):
                df = pd.DataFrame(data['Result'])
                return df
            else:
                print("Unexpected data structure in the response")
                return None
        
        except requests.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    def get_rqbar(self, symbol: str, start_date: str, end_date: str, frequency: str = '1m', adjust_type: str = 'none'):
        if symbol.endswith('0'):
            symbol = symbol[:-1]
        
        return rq.futures.get_dominant_price(symbol, start_date, end_date, frequency, adjust_type=adjust_type)
    
    def get_trade_calendar(self, start,end) -> List[datetime.date]:
        return rq.get_trading_dates(start,end)
    
    def get_main_contract(self,code:str)->str:
        code = code[:-1] if code.endswith('0') else code
        codelist:pd.Series = rq.get_dominant(code)
        return codelist.iloc[0]

def curl_to_python_code(curl_command: str) -> str:
    # Extract URL
    url_match = re.search(r"curl '([^']+)'", curl_command)
    url = url_match.group(1) if url_match else ''

    # Extract headers
    headers = {}
    cookies = {}
    header_matches = re.findall(r"-H '([^:]+): ([^']+)'", curl_command)
    for key, value in header_matches:
        if key.lower() == 'cookie':
            cookies = {k.strip(): v.strip() for k, v in [cookie.split('=', 1) for cookie in value.split(';')]}
        else:
            headers[key] = value

    # Generate Python code
    code = f"""import requests
import pandas as pd
from typing import Optional

def get_futures_news(code: str = 'SC0', page_num: int = 0, page_size: int = 20) -> Optional[pd.DataFrame]:
    code = f"{{code[:-1]}}888" if code.endswith('0') else f"{{code}}888"
    url = 'https://finance.pae.baidu.com/vapi/getfuturesnews'
    
    headers = {headers}
    
    cookies = {cookies}
    
    params = {{
        'code': code,
        'pn': page_num,
        'rn': page_size,
        'finClientType': 'pc'
    }}
    
    try:
        response = requests.get(url, headers=headers, params=params, cookies=cookies)
        response.raise_for_status()
        
        data = response.json()
        
        if 'Result' in data and isinstance(data['Result'], list):
            df = pd.DataFrame(data['Result'])
            return df
        else:
            print("Unexpected data structure in the response")
            return None
    
    except requests.RequestException as e:
        print(f"An error occurred: {{e}}")
        return None

# Usage example:
# df = get_futures_news('SC0')
# if df is not None:
#     print(df.head())
"""
    return code
