import requests
import random
import time
import hashlib
from datetime import datetime

class BaiduFinanceAPI:
    def __init__(self):
        self.base_urls = {
            'news': 'https://finance.pae.baidu.com/selfselect/news',
            'analysis': 'https://finance.pae.baidu.com/vapi/v1/analysis',
            'express_news': 'https://finance.pae.baidu.com/selfselect/expressnews'
        }
        self.headers = {
            'accept': 'application/vnd.finance-web.v1+json',
            'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
            'origin': 'https://gushitong.baidu.com',
            'priority': 'u=1, i',
            'referer': 'https://gushitong.baidu.com/',
            'sec-ch-ua': '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0',
            'cookie': '__bid_n=18e6eb2425d2304866020a; BAIDUID=564AD52829EF1290DDC1A20DCC14F220:FG=1; BAIDUID_BFESS=564AD52829EF1290DDC1A20DCC14F220:FG=1; BIDUPSID=564AD52829EF1290DDC1A20DCC14F220; PSTM=1714397940; ZFY=3ffAdSTQ3amiXQ393UWe0Uy1s70:BPIai4AGEBTM6yIQ:C; H_PS_PSSID=60275_60287_60297_60325; MCITY=-131%3A; BDUSS=X56Q3pvU1ZoNFBUaVZmWHh5QjFMQWRaVzNWcXRMc0NESTJwQ25wdm9RYlVJYnRtRVFBQUFBJCQAAAAAAAAAAAEAAACgejQAd3h5MmFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANSUk2bUlJNma; BDUSS_BFESS=X56Q3pvU1ZoNFBUaVZmWHh5QjFMQWRaVzNWcXRMc0NESTJwQ25wdm9RYlVJYnRtRVFBQUFBJCQAAAAAAAAAAAEAAACgejQAd3h5MmFiAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANSUk2bUlJNma; newlogin=1; RT="z=1&dm=baidu.com&si=ec229f0d-1099-40a1-a3eb-7e95c88c7a95&ss=lzlj98wo&sl=1&tt=93&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=10z"; ab_sr=1.0.1_YmQ1NjZiMzJjOWMzZTFiOGM2MTQxYWE5MDcxNWM0MWZiODg3YjkxNTBjYTQ5ZmQ3NzYwOTAwOWQ1MTgwYTE5MDZmZTAwNWY0N2U4YWM1OWNlMzRhODA3ZTdhMGQ0MDI3YzI3MmQ0MTA2NmY4MTU4ODBjMDJjNWQzMTJiMDU0YzNiODc0MTQzNjFhOGI2YzZlODAzODBmMjcxZTY0OTI1Nw=='
        }

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

    def fetch_news(self, rn=6, pn=0):
        params = {
            'rn': rn,
            'pn': pn,
            'finClientType': 'pc'
        }
        self.headers['acs-token'] = self.generate_acs_token()

        response = requests.get(self.base_urls['news'], headers=self.headers, params=params)
        if response.status_code == 200:
            return self.parse_news(response.json())
        else:
            response.raise_for_status()

    def parse_news(self, data):
        news_list = []
        if "Result" in data and "tabs" in data["Result"]:
            for tab in data["Result"]["tabs"]:
                if "contents" in tab and "list" in tab["contents"]:
                    for item in tab["contents"]["list"]:
                        content_data = " ".join([c['data'] for c in item.get("content", {}).get("items", []) if c.get('data')])
                        publish_time = datetime.fromtimestamp(int(item.get("publish_time", 0)))
                        news_item = {
                            "title": item.get("title", ""),
                            "content": content_data,
                            "ptime": publish_time,
                            "tag": item.get("tag", ""),
                            "provider": item.get("provider", "")
                        }
                        news_list.append(news_item)
        return news_list

    def fetch_analysis(self, code='000725', market='ab'):
        params = {
            'code': code,
            'market': market,
            'finClientType': 'pc'
        }
        self.headers['acs-token'] = self.generate_acs_token()

        response = requests.get(self.base_urls['analysis'], headers=self.headers, params=params)
        if response.status_code == 200:
            return self.parse_analysis(response.json())
        else:
            response.raise_for_status()

    def parse_analysis(self, data):
        result = data.get("Result", {})
        output = []

        synthesis_score = result.get("synthesisScore", {})
        technology_score = result.get("technologyScore", {})
        capital_score = result.get("capitalScore", {})
        market_score = result.get("marketScore", {})
        finance_score = result.get("financeScore", {})

        output.append(f"综合得分: {synthesis_score.get('rating', 'N/A')} ({synthesis_score.get('desc', 'N/A')})")
        output.append(f"行业排名: {synthesis_score.get('industryRanking', 'N/A')} / {synthesis_score.get('firstIndustryName', 'N/A')}")
        output.append(f"更新时间: {synthesis_score.get('updateTime', 'N/A')}")
        output.append("")

        output.append(f"技术面: {technology_score.get('score', 'N/A')} ({technology_score.get('desc', 'N/A')})")
        output.append(f"近5日累计涨跌幅: {', '.join([item.get('increase', 'N/A') for item in technology_score.get('increase', {}).get('items', [])])}")
        output.append("")

        output.append(f"资金面: {capital_score.get('score', 'N/A')} ({capital_score.get('desc', 'N/A')})")
        fundflow = capital_score.get('fundflow', {}).get('body', [])
        for flow in fundflow:
            output.append(f"{flow.get('name', 'N/A')}: 净流入 {flow.get('in', 'N/A')}, 净占比 {flow.get('out', 'N/A')}")
        output.append("")

        output.append(f"市场面: {market_score.get('score', 'N/A')} ({market_score.get('desc', 'N/A')})")
        output.append("")

        output.append(f"财务面: {finance_score.get('score', 'N/A')} ({finance_score.get('desc', 'N/A')})")
        rating_content = finance_score.get('ratingContent', {}).get('list', [])
        for section in rating_content:
            output.append(f"{section.get('title', 'N/A')}:")
            for body in section.get('body', []):
                output.append(f"  {body.get('name', 'N/A')}: 本期 {body.get('thisIssue', 'N/A')}, 上期 {body.get('previousPeriod', 'N/A')}, 行业排名 {body.get('industryRanking', 'N/A')}")
            output.append("")

        return "\n".join(output)

    def fetch_express_news(self, rn=10, pn=0, finance_type='stock', code='000725'):
        params = {
            'rn': rn,
            'pn': pn,
            'financeType': finance_type,
            'code': code,
            'finClientType': 'pc'
        }
        self.headers['acs-token'] = self.generate_acs_token()

        response = requests.get(self.base_urls['express_news'], headers=self.headers, params=params)
        if response.status_code == 200:
            return self.parse_express_news(response.json())
        else:
            response.raise_for_status()

    def parse_express_news(self, data):
        news_list = []
        if "Result" in data and "content" in data["Result"] and "list" in data["Result"]["content"]:
            for item in data["Result"]["content"]["list"]:
                news_item = {
                    "title": item.get("title", ""),
                    "content": " ".join([c['data'] for c in item.get("content", {}).get("items", []) if c.get('data')]),
                    "ptime": datetime.fromtimestamp(int(item.get("publish_time", 0))),
                    "tag": item.get("tag", ""),
                    "provider": item.get("provider", "")
                }
                news_list.append(news_item)
        return news_list