import requests
import json
import time
from functools import lru_cache
from bs4 import BeautifulSoup
from config import DATA_SOURCES
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

class DataFetcher:
    """数据获取类"""
    
    # 线程池执行器，用于并发请求
    _executor = ThreadPoolExecutor(max_workers=10)
    _lock = threading.Lock()
    
    @staticmethod
    @lru_cache(maxsize=512)
    def get_fund_valuation(fund_code, timestamp=None):
        """
        获取基金估值数据
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 基金估值数据字典
        """
        url = f"{DATA_SOURCES['fund_valuation']}{fund_code}.js"
        try:
            response = requests.get(url, timeout=5)  # 5秒超时
            response.encoding = 'utf-8'
            # 解析JSONP格式数据
            # 找到第一个左括号和最后一个右括号
            start = response.text.find('(')
            end = response.text.rfind(')')
            if start != -1 and end != -1:
                data_str = response.text[start+1:end]
                # 移除可能的分号
                data_str = data_str.rstrip(';')
                data = json.loads(data_str)
                return {
                    'fund_code': data.get('fundcode'),
                    'fund_name': data.get('name'),
                    'net_value': data.get('jzrq'),  # 净值日期
                    'unit_net_value': data.get('dwjz'),  # 单位净值
                    'estimate_net_value': data.get('gsz'),  # 估算净值
                    'estimate_change_rate': data.get('gszzl'),  # 估算涨跌幅
                    'estimate_time': data.get('gztime')  # 估值时间
                }
            else:
                return None
        except Exception as e:
            print(f"获取基金估值失败: {e}")
            return None
    
    @staticmethod
    def get_fund_holding(fund_code):
        """
        获取基金重仓股数据
        :param fund_code: 基金代码
        :return: 重仓股列表
        """
        url = f"{DATA_SOURCES['eastmoney']}ccmx_{fund_code}.html"
        try:
            response = requests.get(url)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找重仓股表格
            table = soup.find('table', class_='w782 comm tzxq')
            if not table:
                return []
            
            holdings = []
            rows = table.find_all('tr')[1:]  # 跳过表头
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 7:
                    stock_name = cols[1].text.strip()
                    stock_code = cols[2].text.strip()
                    holding_ratio = cols[6].text.strip()
                    holdings.append({
                        'stock_name': stock_name,
                        'stock_code': stock_code,
                        'holding_ratio': holding_ratio
                    })
            return holdings
        except Exception as e:
            print(f"获取基金重仓股失败: {e}")
            return []
    
    @staticmethod
    def get_stock_quote(stock_code):
        """
        获取股票行情数据
        :param stock_code: 股票代码
        :return: 股票行情数据字典
        """
        # 腾讯财经股票代码格式：sh600000 或 sz000001
        prefix = 'sh' if stock_code.startswith('6') else 'sz'
        tencent_code = f"{prefix}{stock_code}"
        url = f"{DATA_SOURCES['tencent_stock']}{tencent_code}"
        
        try:
            response = requests.get(url)
            response.encoding = 'utf-8'
            data_str = response.text.split('=')[1].rstrip(';')
            data_list = data_str.split('~')
            
            if len(data_list) >= 32:
                return {
                    'stock_code': stock_code,
                    'stock_name': data_list[1],
                    'current_price': data_list[3],  # 当前价格
                    'change_rate': data_list[32],  # 涨跌幅
                    'change_amount': data_list[31],  # 涨跌额
                    'open_price': data_list[5],  # 开盘价
                    'high_price': data_list[33],  # 最高价
                    'low_price': data_list[34],  # 最低价
                    'volume': data_list[36],  # 成交量
                    'amount': data_list[37]  # 成交额
                }
            return None
        except Exception as e:
            print(f"获取股票行情失败: {e}")
            return None
    
    @staticmethod
    def search_fund(fund_keyword):
        """
        根据关键词搜索基金
        :param fund_keyword: 基金代码或名称
        :return: 基金列表
        """
        # 使用东方财富搜索API
        url = f"http://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx?m=1&key={fund_keyword}"
        try:
            response = requests.get(url)
            data = response.json()
            funds = []
            for item in data.get('Datas', []):
                funds.append({
                    'fund_code': item.get('CODE'),
                    'fund_name': item.get('NAME'),
                    'fund_type': item.get('CATEGORYDESC', '未知')
                })
            return funds
        except Exception as e:
            print(f"搜索基金失败: {e}")
            return []
    
    @staticmethod
    @lru_cache(maxsize=512)
    def get_fund_rates(fund_code, timestamp=None):
        """
        只获取基金涨跌幅数据（不获取历史净值数组）
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 涨跌幅数据
        """
        # 使用东方财富的FundBaseTypeInformation API获取涨跌幅数据
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
        try:
            response = requests.get(url, timeout=5)  # 5秒超时
            data = response.json()
            
            # 解析涨跌幅数据
            one_month_rate = 0
            three_month_rate = 0
            one_year_rate = 0
            daily_change_rate = 0
            
            # 提取FSRQ（净值日期）
            fsrq = ''
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                # 使用实际API返回的字段名称
                # 根据用户提供的信息：
                # SYL_Y: 近1月收益率
                # SYL_1N: 近1年收益率
                # SYL_3Y: 近3年收益率
                # RZDF: 昨天涨跌幅
                try:
                    one_month_rate = float(data['Datas'].get('SYL_Y', 0))
                except (ValueError, TypeError):
                    one_month_rate = 0
                try:
                    three_month_rate = float(data['Datas'].get('SYL_3Y', 0))
                except (ValueError, TypeError):
                    three_month_rate = 0
                try:
                    one_year_rate = float(data['Datas'].get('SYL_1N', 0))
                except (ValueError, TypeError):
                    one_year_rate = 0
                try:
                    daily_change_rate = float(data['Datas'].get('RZDF', 0))
                except (ValueError, TypeError):
                    daily_change_rate = 0
            
            return {
                'fund_code': fund_code,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq
            }
        except Exception as e:
            print(f"获取基金涨跌幅数据失败: {e}")
            return {
                'fund_code': fund_code,
                'one_month_rate': 0,
                'three_month_rate': 0,
                'one_year_rate': 0,
                'daily_change_rate': 0,
                'fsrq': ''
            }
    
    @staticmethod
    @lru_cache(maxsize=256)
    def get_fund_history_simple(fund_code, timestamp=None):
        """
        获取基金基本涨跌幅数据，不获取完整的历史净值
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 涨跌幅数据
        """
        # 使用东方财富的FundBaseTypeInformation API获取涨跌幅数据
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
        try:
            response = requests.get(url, timeout=3)  # 3秒超时
            data = response.json()
            
            # 解析涨跌幅数据
            one_month_rate = 0
            three_month_rate = 0
            one_year_rate = 0
            daily_change_rate = 0
            unit_net_value = 0
            
            # 提取FSRQ（净值日期）
            fsrq = ''
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                # 使用实际API返回的字段名称
                try:
                    one_month_rate = float(data['Datas'].get('SYL_Y', 0))
                except (ValueError, TypeError):
                    one_month_rate = 0
                try:
                    three_month_rate = float(data['Datas'].get('SYL_3Y', 0))
                except (ValueError, TypeError):
                    three_month_rate = 0
                try:
                    one_year_rate = float(data['Datas'].get('SYL_1N', 0))
                except (ValueError, TypeError):
                    one_year_rate = 0
                try:
                    daily_change_rate = float(data['Datas'].get('RZDF', 0))
                except (ValueError, TypeError):
                    daily_change_rate = 0
                try:
                    unit_net_value = float(data['Datas'].get('DWJZ', 0))
                except (ValueError, TypeError):
                    unit_net_value = 0
            
            return {
                'fund_code': fund_code,
                'net_values': [],  # 空数组，不返回历史数据
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }
        except Exception as e:
            print(f"获取基金涨跌幅数据失败: {e}")
            return {
                'fund_code': fund_code,
                'net_values': [],
                'one_month_rate': 0,
                'three_month_rate': 0,
                'one_year_rate': 0,
                'daily_change_rate': 0,
                'fsrq': '',
                'unit_net_value': 0
            }

    @staticmethod
    @lru_cache(maxsize=128)
    def get_fund_history(fund_code, timestamp=None):
        """
        获取基金历史净值数据
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 历史净值数据和涨跌幅数据
        """
        # 使用东方财富的FundBaseTypeInformation API获取涨跌幅数据
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
        try:
            response = requests.get(url)
            data = response.json()
            
            # 解析涨跌幅数据
            one_month_rate = 0
            three_month_rate = 0
            one_year_rate = 0
            daily_change_rate = 0
            
            # 提取FSRQ（净值日期）
            fsrq = ''
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                # 使用实际API返回的字段名称
                # 根据用户提供的信息：
                # SYL_Y: 近1月收益率
                # SYL_1N: 近1年收益率
                # SYL_3Y: 近3年收益率
                # RZDF: 昨天涨跌幅
                try:
                    one_month_rate = float(data['Datas'].get('SYL_Y', 0))
                except (ValueError, TypeError):
                    one_month_rate = 0
                try:
                    three_month_rate = float(data['Datas'].get('SYL_3Y', 0))
                except (ValueError, TypeError):
                    three_month_rate = 0
                try:
                    one_year_rate = float(data['Datas'].get('SYL_1N', 0))
                except (ValueError, TypeError):
                    one_year_rate = 0
                try:
                    daily_change_rate = float(data['Datas'].get('RZDF', 0))
                except (ValueError, TypeError):
                    daily_change_rate = 0
            
            # 同时获取历史净值数据
            net_values = []
            page_index = 1
            page_size = 100
            
            while True:
                net_values_url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex={page_index}&pageSize={page_size}"
                headers = {
                    "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                }
                net_values_response = requests.get(net_values_url, headers=headers)
                net_values_data = net_values_response.json()
                
                # 解析历史净值数据
                if net_values_data.get('Data') and net_values_data['Data'].get('LSJZList'):
                    for item in net_values_data['Data']['LSJZList']:
                        # 跳过DWJZ为空的记录（如节假日）
                        if item.get('DWJZ'):
                            net_values.append({
                                'date': item.get('FSRQ'),
                                'unit_net_value': item.get('DWJZ'),
                                'cumulative_net_value': item.get('LJJZ'),
                                'change_rate': item.get('JZZZL')
                            })
                    
                    # 检查是否还有更多数据
                    total_count = net_values_data.get('TotalCount', 0)
                    if len(net_values) >= total_count or len(net_values) >= 500:
                        break
                    page_index += 1
                else:
                    break
            
            return {
                'fund_code': fund_code,
                'net_values': net_values,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq  # 添加FSRQ字段
            }
        except Exception as e:
            print(f"获取基金历史净值失败: {e}")
            return {
                'fund_code': fund_code,
                'net_values': [],
                'one_month_rate': 0,
                'three_month_rate': 0,
                'one_year_rate': 0,
                'daily_change_rate': 0,
                'fsrq': ''  # 添加FSRQ字段
            }
    
    @staticmethod
    @lru_cache(maxsize=512)
    def get_fund_history_by_date(fund_code, target_date):
        """
        根据基金代码和日期获取历史净值
        :param fund_code: 基金代码
        :param target_date: 目标日期，格式为 'YYYY-MM-DD'
        :return: 对应日期的净值数据，或 None
        """
        try:
            # 获取基金历史净值数据
            history_data = DataFetcher.get_fund_history(fund_code)
            net_values = history_data.get('net_values', [])
            
            # 遍历历史净值数据，找到目标日期的净值
            for item in net_values:
                if item.get('date') == target_date:
                    return {
                        'fund_code': fund_code,
                        'date': item.get('date'),
                        'unit_net_value': item.get('unit_net_value'),
                        'cumulative_net_value': item.get('cumulative_net_value'),
                        'change_rate': item.get('change_rate')
                    }
            
            # 如果没有找到目标日期的净值，返回 None
            return None
        except Exception as e:
            print(f"获取基金历史净值失败: {e}")
            return None
    
    @staticmethod
    def get_fund_rates_batch(fund_codes, timestamp=None):
        """
        批量并发获取多个基金的涨跌幅数据
        :param fund_codes: 基金代码列表
        :param timestamp: 时间戳（用于缓存过期）
        :return: 基金数据字典 {fund_code: data}
        """
        if not fund_codes:
            return {}
        
        results = {}
        
        # 使用线程池并发获取数据
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 提交所有任务
            future_to_fund = {
                executor.submit(DataFetcher.get_fund_rates, fund_code, timestamp): fund_code 
                for fund_code in fund_codes
            }
            
            # 等待所有任务完成
            for future in as_completed(future_to_fund):
                fund_code = future_to_fund[future]
                try:
                    data = future.result(timeout=5)  # 5秒超时
                    results[fund_code] = data
                except Exception as e:
                    print(f"获取基金 {fund_code} 数据失败: {e}")
                    # 返回默认数据，避免阻塞其他基金
                    results[fund_code] = {
                        'fund_code': fund_code,
                        'one_month_rate': 0,
                        'three_month_rate': 0,
                        'one_year_rate': 0,
                        'daily_change_rate': 0,
                        'fsrq': ''
                    }
        
        return results
    
    @staticmethod
    def get_fund_valuation_batch(fund_codes, timestamp=None):
        """
        批量并发获取多个基金的估值数据
        :param fund_codes: 基金代码列表
        :param timestamp: 时间戳（用于缓存过期）
        :return: 基金数据字典 {fund_code: data}
        """
        if not fund_codes:
            return {}
        
        results = {}
        
        # 使用线程池并发获取数据
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 提交所有任务
            future_to_fund = {
                executor.submit(DataFetcher.get_fund_valuation, fund_code, timestamp): fund_code 
                for fund_code in fund_codes
            }
            
            # 等待所有任务完成
            for future in as_completed(future_to_fund):
                fund_code = future_to_fund[future]
                try:
                    data = future.result(timeout=5)  # 5秒超时
                    results[fund_code] = data
                except Exception as e:
                    print(f"获取基金 {fund_code} 估值数据失败: {e}")
                    results[fund_code] = None
        
        return results
