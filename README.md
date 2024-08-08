# llm_dealer
llm  交易员    
目前基于xuntou模拟的期货单合约策略已经可以运行   

## 支持的操作系统
因为模拟环境的关系，目前只能支持windows

## 模拟环境
讯投研

## 安装
- 下载代码    
- 下载讯投研
- 注册miniMax
- 配置setting.ini
    - 配置xt_key  从讯投用户中心获取
    - 配置account_id 从讯投App获取，目前只支持期货，后续支持股票
    - symbol 填一个**有效** 的期货合约代码，具体格式看讯投的文档
    - 填写 minimax_api_key 从minimax官网获取
- 运行install.bat
- 运行run.bat

## plan
- 支持vnpy
- 支持多合约期货策略
- 支持选股
- 支持股票交易