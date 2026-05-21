import requests
import json
import time
from functools import lru_cache, wraps
from bs4 import BeautifulSoup
from config import DATA_SOURCES
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

def retry_on_failure(max_retries=3, delay=1, backoff=2, exceptions=(requests.RequestException, requests.Timeout, ConnectionError, json.JSONDecodeError)):
    """
    重试装饰器，用于处理API请求失败的情况
    :param max_retries: 最大重试次数
    :param delay: 初始延迟时间（秒）
    :param backoff: 延迟时间倍数
    :param exceptions: 需要重试的异常类型
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if result is None:
                        raise ValueError("API返回None值")
                    return result
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"API请求失败，第{attempt + 1}次重试，等待{current_delay:.2f}秒... 错误: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"API请求失败，已达到最大重试次数{max_retries}次，放弃重试。错误: {e}")
                except ValueError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"API返回None值，第{attempt + 1}次重试，等待{current_delay:.2f}秒... 错误: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        print(f"API返回None值，已达到最大重试次数{max_retries}次，放弃重试。错误: {e}")
                except Exception as e:
                    print(f"API请求遇到非重试异常: {e}")
                    raise e

            return None
        return wrapper
    return decorator

class DataFetcher:
    """数据获取类"""

    # 线程池执行器，用于并发请求
    _executor = ThreadPoolExecutor(max_workers=5)  # 减少线程池大小，避免资源占用过多
    _lock = threading.Lock()

    @staticmethod
    def _get_fund_valuation_no_retry(fund_code, timestamp=None):
        # 尝试主数据源 (1234567.com.cn)
        url = f"{DATA_SOURCES['fund_valuation']}{fund_code}.js"
        try:
            response = requests.get(url, timeout=5)
            response.encoding = 'utf-8'
            start = response.text.find('(')
            end = response.text.rfind(')')
            if start != -1 and end != -1:
                data_str = response.text[start+1:end]
                data_str = data_str.rstrip(';')
                data = json.loads(data_str)
                result = {
                    'fund_code': data.get('fundcode'),
                    'fund_name': data.get('name'),
                    'net_value': data.get('jzrq'),
                    'unit_net_value': data.get('dwjz'),
                    'estimate_net_value': data.get('gsz'),
                    'estimate_change_rate': data.get('gszzl'),
                    'estimate_time': data.get('gztime')
                }
                # 验证数据有效性
                if result.get('estimate_net_value') or result.get('unit_net_value'):
                    return result
        except Exception as e:
            print(f"主数据源获取基金 {fund_code} 估值失败: {e}")

        # 尝试备用数据源 (东方财富)
        try:
            url = f"{DATA_SOURCES['fund_valuation_backup']}?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
            headers = {
                'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'
            }
            response = requests.get(url, headers=headers, timeout=5)
            response.encoding = 'utf-8'
            data = response.json()
            if data and data.get('Datas'):
                datas = data['Datas']
                result = {
                    'fund_code': fund_code,
                    'fund_name': datas.get('NAME', ''),
                    'net_value': datas.get('JZRQ', ''),
                    'unit_net_value': datas.get('DWJZ', ''),
                    'estimate_net_value': datas.get('GSZ', ''),
                    'estimate_change_rate': datas.get('GSZZL', ''),
                    'estimate_time': datas.get('GZTIME', '')
                }
                if result.get('estimate_net_value') or result.get('unit_net_value'):
                    return result
        except Exception as e:
            print(f"备用数据源获取基金 {fund_code} 估值失败: {e}")

        return None

    @staticmethod
    @lru_cache(maxsize=512)
    @retry_on_failure(max_retries=3, delay=1, backoff=2)
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
            response = requests.get(url, timeout=10)
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
            response = requests.get(url, timeout=10)
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
            response = requests.get(url, timeout=10)
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
    def _get_fund_rates_no_retry(fund_code, timestamp=None):
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'
        }

        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        fsrq = ''
        unit_net_value = 0

        try:
            response = requests.get(url, headers=headers, timeout=8)
            data = response.json()

            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                field_mappings = {
                    'one_month': ['SYL_Y', 'SYL_1M', 'syl_y', 'syly'],
                    'three_month': ['SYL_3Y', 'SYL_3M', 'syl_3y', 'syl3y'],
                    'one_year': ['SYL_1N', 'syl_1n', 'syl1n'],
                    'daily': ['RZDF', 'JZZZL', 'rzdf', 'jzzzl'],
                    'unit_net_value': ['DWJZ', 'dwjz']
                }

                for field in field_mappings['unit_net_value']:
                    if field in data['Datas']:
                        try:
                            unit_net_value = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['one_month']:
                    if field in data['Datas']:
                        try:
                            one_month_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['three_month']:
                    if field in data['Datas']:
                        try:
                            three_month_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['one_year']:
                    if field in data['Datas']:
                        try:
                            one_year_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['daily']:
                    if field in data['Datas']:
                        try:
                            daily_change_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

            return {
                'fund_code': fund_code,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }
        except Exception as e:
            print(f"批量获取基金 {fund_code} 涨跌幅数据失败: {e}")
            return {
                'fund_code': fund_code,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }

    @staticmethod
    @lru_cache(maxsize=512)
    @retry_on_failure(max_retries=5, delay=2, backoff=2)
    def get_fund_rates(fund_code, timestamp=None):
        """
        只获取基金涨跌幅数据（不获取历史净值数组）
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 涨跌幅数据
        """
        print(f"开始获取基金 {fund_code} 的涨跌幅数据")
        # 首先尝试使用东方财富的FundBaseTypeInformation API
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="

        # 增加请求头，模拟浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'
        }

        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        fsrq = ''
        unit_net_value = 0

        try:
            # 增加超时时间到10秒
            response = requests.get(url, headers=headers, timeout=10)
            print(f"东方财富API响应状态码: {response.status_code}")
            data = response.json()
            print(f"东方财富API返回数据: {data}")

            # 解析涨跌幅数据
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                print(f"基金 {fund_code} 的FSRQ: {fsrq}")
                # 尝试使用不同的字段名称组合
                # 常见的字段名称组合
                field_mappings = {
                    'one_month': ['SYL_1M', 'syl_1m', 'SYL_Y', 'syl_y', '近1月', 'OneMonth', 'syly', 'SYLY', '1m', '1M'],
                    'three_month': ['SYL_3M', 'syl_3m', 'SYL_3Y', 'syl_3y', '近3月', 'ThreeMonth', 'syl3y', 'SYL3Y', '3m', '3M'],
                    'one_year': ['SYL_1N', 'syl_1n', '近1年', 'OneYear', 'syl1n', 'SYL1N', '1y', '1Y'],
                    'daily': ['JZZZL', 'jzzzl', 'RZDF', 'rzdf', '日涨跌幅', 'DailyChange', 'rdf', 'RDF', 'daily_change', 'DAILY_CHANGE', 'zdf', 'ZDF'],
                    'unit_net_value': ['DWJZ', 'dwjz', '单位净值', 'UnitNetValue']
                }

                # 尝试获取单位净值
                for field in field_mappings['unit_net_value']:
                    if field in data['Datas']:
                        try:
                            unit_net_value = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的单位净值: {unit_net_value}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取近1月收益率
                for field in field_mappings['one_month']:
                    if field in data['Datas']:
                        try:
                            one_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取近3月收益率
                for field in field_mappings['three_month']:
                    if field in data['Datas']:
                        try:
                            three_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取近1年收益率
                for field in field_mappings['one_year']:
                    if field in data['Datas']:
                        try:
                            one_year_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取日涨跌幅
                for field in field_mappings['daily']:
                    if field in data['Datas']:
                        try:
                            daily_change_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的日涨跌幅: {daily_change_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

            # 如果使用东方财富API没有获取到数据，尝试使用天天基金API
            if one_month_rate == 0 and three_month_rate == 0 and one_year_rate == 0 and daily_change_rate == 0:
                print(f"东方财富API未获取到基金 {fund_code} 的数据，尝试使用天天基金API")
                # 天天基金API
                url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    print(f"天天基金API响应状态码: {response.status_code}")
                    response.encoding = 'utf-8'
                    content = response.text
                    print(f"天天基金API返回数据长度: {len(content)}")

                    # 提取涨跌幅数据
                    import re
                    # 提取日涨跌幅
                    daily_match = re.search(r'var\s+rzdf\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if daily_match:
                        try:
                            daily_change_rate = float(daily_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的日涨跌幅: {daily_change_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"日涨跌幅转换失败: {e}")
                            pass

                    # 提取近1月收益率
                    one_month_match = re.search(r'var\s+syly\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if one_month_match:
                        try:
                            one_month_rate = float(one_month_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近1月收益率转换失败: {e}")
                            pass

                    # 提取近3月收益率
                    three_month_match = re.search(r'var\s+syl3y\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if three_month_match:
                        try:
                            three_month_rate = float(three_month_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近3月收益率转换失败: {e}")
                            pass

                    # 提取近1年收益率
                    one_year_match = re.search(r'var\s+syl1n\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if one_year_match:
                        try:
                            one_year_rate = float(one_year_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近1年收益率转换失败: {e}")
                            pass

                    # 提取净值日期
                    fsrq_match = re.search(r'var\s+fsrq\s*=\s*"([\d-]+)"', content)
                    if fsrq_match:
                        fsrq = fsrq_match.group(1)
                        print(f"使用正则提取基金 {fund_code} 的FSRQ: {fsrq}")

                    # 提取单位净值
                    unit_net_value_match = re.search(r'var\s+dwjz\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if unit_net_value_match:
                        try:
                            unit_net_value = float(unit_net_value_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的单位净值: {unit_net_value}")
                        except (ValueError, TypeError):
                            pass

                except Exception as e:
                    print(f"使用天天基金API获取基金涨跌幅数据失败: {e}")

            print(f"基金 {fund_code} 的最终涨跌幅数据: one_month_rate={one_month_rate}, three_month_rate={three_month_rate}, one_year_rate={one_year_rate}, daily_change_rate={daily_change_rate}, fsrq={fsrq}, unit_net_value={unit_net_value}")
            return {
                'fund_code': fund_code,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }
        except Exception as e:
            print(f"获取基金涨跌幅数据失败: {e}")
            # 即使失败，也尝试返回部分数据
            return {
                'fund_code': fund_code,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }

    @staticmethod
    def _get_fund_history_simple_no_retry(fund_code, timestamp=None):
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'
        }

        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        unit_net_value = 0
        fsrq = ''

        try:
            response = requests.get(url, headers=headers, timeout=8)
            data = response.json()

            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                field_mappings = {
                    'one_month': ['SYL_1M', 'syl_1m', 'SYL_Y', 'syl_y', 'syly', 'SYLY'],
                    'three_month': ['SYL_3M', 'syl_3m', 'SYL_3Y', 'syl_3y', 'syl3y', 'SYL3Y'],
                    'one_year': ['SYL_1N', 'syl_1n', 'syl1n', 'SYL1N'],
                    'daily': ['JZZZL', 'jzzzl', 'RZDF', 'rzdf'],
                    'unit_net_value': ['DWJZ', 'dwjz']
                }

                for field in field_mappings['unit_net_value']:
                    if field in data['Datas']:
                        try:
                            unit_net_value = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['one_month']:
                    if field in data['Datas']:
                        try:
                            one_month_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['three_month']:
                    if field in data['Datas']:
                        try:
                            three_month_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['one_year']:
                    if field in data['Datas']:
                        try:
                            one_year_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

                for field in field_mappings['daily']:
                    if field in data['Datas']:
                        try:
                            daily_change_rate = float(data['Datas'][field])
                            break
                        except (ValueError, TypeError):
                            continue

            return {
                'fund_code': fund_code,
                'net_values': [],
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }
        except Exception as e:
            print(f"获取基金 {fund_code} 涨跌幅数据失败(无重试): {e}")
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
    @lru_cache(maxsize=256)
    @retry_on_failure(max_retries=5, delay=2, backoff=2)
    def get_fund_history_simple(fund_code, timestamp=None):
        """
        获取基金基本涨跌幅数据，不获取完整的历史净值
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 涨跌幅数据
        """
        print(f"开始获取基金 {fund_code} 的基本涨跌幅数据")
        # 使用东方财富的FundBaseTypeInformation API获取涨跌幅数据
        url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="

        # 增加请求头，模拟浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': f'https://fundf10.eastmoney.com/jjjz_{fund_code}.html'
        }

        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        unit_net_value = 0
        fsrq = ''

        try:
            # 增加超时时间到10秒
            response = requests.get(url, headers=headers, timeout=10)
            print(f"东方财富API响应状态码: {response.status_code}")
            data = response.json()
            print(f"东方财富API返回数据: {data}")

            # 解析涨跌幅数据
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                print(f"基金 {fund_code} 的FSRQ: {fsrq}")
                # 尝试使用不同的字段名称组合
                # 常见的字段名称组合
                field_mappings = {
                    'one_month': ['SYL_1M', 'syl_1m', 'SYL_Y', 'syl_y', '近1月', 'OneMonth', 'syly', 'SYLY', '1m', '1M'],
                    'three_month': ['SYL_3M', 'syl_3m', 'SYL_3Y', 'syl_3y', '近3月', 'ThreeMonth', 'syl3y', 'SYL3Y', '3m', '3M'],
                    'one_year': ['SYL_1N', 'syl_1n', '近1年', 'OneYear', 'syl1n', 'SYL1N', '1y', '1Y'],
                    'daily': ['JZZZL', 'jzzzl', 'RZDF', 'rzdf', '日涨跌幅', 'DailyChange', 'rdf', 'RDF', 'daily_change', 'DAILY_CHANGE', 'zdf', 'ZDF'],
                    'unit_net_value': ['DWJZ', 'dwjz', '单位净值', 'UnitNetValue']
                }

                # 尝试获取近1月收益率
                for field in field_mappings['one_month']:
                    if field in data['Datas']:
                        try:
                            one_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取近3月收益率
                for field in field_mappings['three_month']:
                    if field in data['Datas']:
                        try:
                            three_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取近1年收益率
                for field in field_mappings['one_year']:
                    if field in data['Datas']:
                        try:
                            one_year_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取日涨跌幅
                for field in field_mappings['daily']:
                    if field in data['Datas']:
                        try:
                            daily_change_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的日涨跌幅: {daily_change_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

                # 尝试获取单位净值
                for field in field_mappings['unit_net_value']:
                    if field in data['Datas']:
                        try:
                            unit_net_value = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的单位净值: {unit_net_value}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")
                            continue

            # 如果使用东方财富API没有获取到数据，尝试使用天天基金API
            if one_month_rate == 0 and three_month_rate == 0 and one_year_rate == 0 and daily_change_rate == 0:
                print(f"东方财富API未获取到基金 {fund_code} 的数据，尝试使用天天基金API")
                # 天天基金API
                url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    print(f"天天基金API响应状态码: {response.status_code}")
                    response.encoding = 'utf-8'
                    content = response.text
                    print(f"天天基金API返回数据长度: {len(content)}")

                    # 提取涨跌幅数据
                    import re
                    # 提取日涨跌幅
                    daily_match = re.search(r'var\s+rzdf\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if daily_match:
                        try:
                            daily_change_rate = float(daily_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的日涨跌幅: {daily_change_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"日涨跌幅转换失败: {e}")
                            pass

                    # 提取近1月收益率
                    one_month_match = re.search(r'var\s+syly\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if one_month_match:
                        try:
                            one_month_rate = float(one_month_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近1月收益率转换失败: {e}")
                            pass

                    # 提取近3月收益率
                    three_month_match = re.search(r'var\s+syl3y\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if three_month_match:
                        try:
                            three_month_rate = float(three_month_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近3月收益率转换失败: {e}")
                            pass

                    # 提取近1年收益率
                    one_year_match = re.search(r'var\s+syl1n\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if one_year_match:
                        try:
                            one_year_rate = float(one_year_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                        except (ValueError, TypeError) as e:
                            print(f"近1年收益率转换失败: {e}")
                            pass

                    # 提取净值日期
                    fsrq_match = re.search(r'var\s+fsrq\s*=\s*"([\d-]+)"', content)
                    if fsrq_match:
                        fsrq = fsrq_match.group(1)
                        print(f"使用正则提取基金 {fund_code} 的FSRQ: {fsrq}")

                    # 提取单位净值
                    unit_net_value_match = re.search(r'var\s+dwjz\s*=\s*"([-+]?\d+\.\d+)"', content)
                    if unit_net_value_match:
                        try:
                            unit_net_value = float(unit_net_value_match.group(1))
                            print(f"使用正则提取基金 {fund_code} 的单位净值: {unit_net_value}")
                        except (ValueError, TypeError) as e:
                            print(f"单位净值转换失败: {e}")
                            pass

                except Exception as e:
                    print(f"使用天天基金API获取基金涨跌幅数据失败: {e}")

            print(f"基金 {fund_code} 的最终涨跌幅数据: one_month_rate={one_month_rate}, three_month_rate={three_month_rate}, one_year_rate={one_year_rate}, daily_change_rate={daily_change_rate}, unit_net_value={unit_net_value}, fsrq={fsrq}")
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
            # 即使失败，也尝试返回部分数据
            return {
                'fund_code': fund_code,
                'net_values': [],
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': '',
                'unit_net_value': 0
            }

    @staticmethod
    def get_fund_history(fund_code, timestamp=None):
        """
        获取基金历史净值数据
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期，传入秒级时间戳可强制刷新）
        :return: 历史净值数据和涨跌幅数据
        """
        if timestamp is None:
            # 按小时缓存，避免同一天内缓存空数据
            timestamp = int(time.time() / 3600)

        @lru_cache(maxsize=128)
        def _get_fund_history(fund_code, timestamp):
            rates_data = DataFetcher.get_fund_rates(fund_code, timestamp)
            one_month_rate = rates_data.get('one_month_rate', 0)
            three_month_rate = rates_data.get('three_month_rate', 0)
            one_year_rate = rates_data.get('one_year_rate', 0)
            daily_change_rate = rates_data.get('daily_change_rate', 0)
            fsrq = rates_data.get('fsrq', '')
            unit_net_value = rates_data.get('unit_net_value', 0)

            net_values = []
            try:
                page_index = 1
                page_size = 100

                while True:
                    net_values_url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex={page_index}&pageSize={page_size}"
                    headers = {
                        "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                    }
                    net_values_response = requests.get(net_values_url, headers=headers, timeout=10)
                    net_values_data = net_values_response.json()

                    if net_values_data.get('Data') and net_values_data['Data'].get('LSJZList'):
                        for item in net_values_data['Data']['LSJZList']:
                            if item.get('DWJZ'):
                                net_values.append({
                                    'date': item.get('FSRQ'),
                                    'unit_net_value': item.get('DWJZ'),
                                    'cumulative_net_value': item.get('LJJZ'),
                                    'change_rate': item.get('JZZZL')
                                })

                        total_count = net_values_data.get('TotalCount', 0)
                        if len(net_values) >= total_count or len(net_values) >= 500:
                            break
                        page_index += 1
                    else:
                        break
            except Exception as e:
                print(f"获取基金历史净值失败，但涨跌幅数据仍可用: {e}")

            if net_values:
                latest_lsjz = net_values[0]
                latest_lsjz_date = latest_lsjz.get('date', '')
                try:
                    latest_lsjz_nav = float(latest_lsjz.get('unit_net_value', 0))
                except (ValueError, TypeError):
                    latest_lsjz_nav = 0

                if unit_net_value == 0 and latest_lsjz_nav > 0:
                    unit_net_value = latest_lsjz_nav
                    fsrq = latest_lsjz_date
                    print(f"基金 {fund_code} get_fund_rates未返回净值，使用LSJZList数据: unit_net_value={unit_net_value}, fsrq={fsrq}")
                elif fsrq == latest_lsjz_date and latest_lsjz_nav > 0 and unit_net_value != latest_lsjz_nav:
                    print(f"基金 {fund_code} 净值数据不一致(API: {unit_net_value}, LSJZList: {latest_lsjz_nav}, 日期: {fsrq})，使用LSJZList数据")
                    unit_net_value = latest_lsjz_nav

            return {
                'fund_code': fund_code,
                'net_values': net_values,
                'one_month_rate': one_month_rate,
                'three_month_rate': three_month_rate,
                'one_year_rate': one_year_rate,
                'daily_change_rate': daily_change_rate,
                'fsrq': fsrq,
                'unit_net_value': unit_net_value
            }

        # 调用内部函数
        return _get_fund_history(fund_code, timestamp)

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
        批量并发获取多个基金的涨跌幅数据（使用 real-time-fund 风格的批量接口）
        :param fund_codes: 基金代码列表
        :param timestamp: 时间戳（用于缓存过期）
        :return: 基金数据字典 {fund_code: data}
        """
        if not fund_codes:
            return {}

        # 使用 real-time-fund 风格的批量接口
        return DataFetcher._get_fund_rates_batch_realtime_style(fund_codes)

    @staticmethod
    def _get_fund_rates_batch_realtime_style(fund_codes):
        """
        使用 real-time-fund 风格的批量接口获取基金数据
        主要使用东方财富批量接口 + 腾讯基金备用接口
        """
        results = {}

        # 1. 首先尝试东方财富批量接口
        batch_result = DataFetcher._fetch_eastmoney_batch(fund_codes)
        results.update(batch_result)

        # 2. 对于未获取到数据的基金，使用腾讯基金接口补充
        missing_codes = [code for code in fund_codes if code not in results or results[code] is None]
        if missing_codes:
            tencent_result = DataFetcher._fetch_tencent_batch(missing_codes)
            results.update(tencent_result)

        # 3. 最后使用单只基金接口补充剩余的
        remaining_codes = [code for code in fund_codes if code not in results or results[code] is None]
        if remaining_codes:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._get_fund_rates_no_retry, fund_code, None): fund_code
                    for fund_code in remaining_codes
                }
                for future in as_completed(future_to_fund, timeout=15):
                    fund_code = future_to_fund[future]
                    try:
                        data = future.result(timeout=8)
                        if data:
                            results[fund_code] = data
                    except Exception as e:
                        print(f"单只基金接口获取 {fund_code} 数据失败: {e}")

        return results

    @staticmethod
    def _fetch_eastmoney_batch(fund_codes):
        """
        使用东方财富批量接口获取基金数据
        real-time-fund 使用的接口
        """
        results = {}
        if not fund_codes:
            return results

        try:
            # 东方财富批量接口，一次最多支持约100个基金代码
            max_per_request = 50
            for i in range(0, len(fund_codes), max_per_request):
                batch = fund_codes[i:i+max_per_request]
                fcodes = ",".join(batch)

                url = f"https://fundmobapi.eastmoney.com/FundMApi/FundInfoCombineNew.ashx?Fcodes={fcodes}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://m.fund.eastmoney.com/'
                }

                response = requests.get(url, headers=headers, timeout=10)
                data = response.json()

                if data.get('Datas'):
                    for item in data['Datas']:
                        fund_code = item.get('FCODE', '')
                        if fund_code:
                            results[fund_code] = {
                                'fund_code': fund_code,
                                'one_month_rate': float(item.get('SYL_Y', 0) or 0),
                                'three_month_rate': float(item.get('SYL_3Y', 0) or 0),
                                'one_year_rate': float(item.get('SYL_1N', 0) or 0),
                                'daily_change_rate': float(item.get('RZDF', 0) or 0),
                                'fsrq': item.get('FSRQ', ''),
                                'unit_net_value': float(item.get('DWJZ', 0) or 0)
                            }
        except Exception as e:
            print(f"东方财富批量接口请求失败: {e}")

        return results

    @staticmethod
    def _fetch_tencent_batch(fund_codes):
        """
        使用腾讯基金接口获取基金数据（作为备用）
        real-time-fund 使用的接口
        """
        results = {}
        if not fund_codes:
            return results

        try:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._fetch_tencent_single, fund_code): fund_code
                    for fund_code in fund_codes
                }

                for future in as_completed(future_to_fund, timeout=10):
                    fund_code = future_to_fund[future]
                    try:
                        data = future.result(timeout=5)
                        if data:
                            results[fund_code] = data
                    except Exception as e:
                        print(f"腾讯基金接口获取 {fund_code} 数据失败: {e}")
        except Exception as e:
            print(f"腾讯基金批量请求失败: {e}")

        return results

    @staticmethod
    def _fetch_tencent_single(fund_code):
        """
        使用腾讯基金单只接口获取数据
        """
        try:
            url = f"https://qt.gtimg.cn/q=ofund_{fund_code}"
            response = requests.get(url, timeout=5)
            data = response.text

            if data:
                parts = data.split('~')
                if len(parts) >= 45:
                    return {
                        'fund_code': fund_code,
                        'one_month_rate': float(parts[8] or 0),
                        'three_month_rate': float(parts[9] or 0),
                        'one_year_rate': float(parts[10] or 0),
                        'daily_change_rate': float(parts[3] or 0),
                        'fsrq': parts[46] if len(parts) > 46 else '',
                        'unit_net_value': float(parts[4] or 0)
                    }
        except Exception as e:
            print(f"腾讯基金接口获取 {fund_code} 数据失败: {e}")

        return None

    @staticmethod
    def get_fund_valuation_batch(fund_codes, timestamp=None):
        """
        批量并发获取多个基金的估值数据（使用 real-time-fund 风格的批量接口）
        :param fund_codes: 基金代码列表
        :param timestamp: 时间戳（用于缓存过期）
        :return: 基金数据字典 {fund_code: data}
        """
        if not fund_codes:
            return {}

        # 使用 real-time-fund 风格的批量估值接口
        return DataFetcher._get_fund_valuation_batch_realtime_style(fund_codes)

    @staticmethod
    def _get_fund_valuation_batch_realtime_style(fund_codes):
        """
        使用 real-time-fund 风格的批量估值接口
        """
        results = {}

        # 1. 首先尝试东方财富批量估值接口
        batch_result = DataFetcher._fetch_eastmoney_valuation_batch(fund_codes)
        results.update(batch_result)

        # 2. 对于未获取到数据的基金，使用原有方法补充
        missing_codes = [code for code in fund_codes if code not in results or results[code] is None]
        if missing_codes:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._get_fund_valuation_no_retry, fund_code, None): fund_code
                    for fund_code in missing_codes
                }
                for future in as_completed(future_to_fund, timeout=15):
                    fund_code = future_to_fund[future]
                    try:
                        data = future.result(timeout=5)
                        if data:
                            results[fund_code] = data
                    except Exception as e:
                        print(f"估值接口获取 {fund_code} 数据失败: {e}")

        return results

    @staticmethod
    def _fetch_eastmoney_valuation_batch(fund_codes):
        """
        使用东方财富批量估值接口
        real-time-fund 使用的接口
        """
        results = {}
        if not fund_codes:
            return results

        try:
            # 东方财富估值批量接口
            max_per_request = 50
            for i in range(0, len(fund_codes), max_per_request):
                batch = fund_codes[i:i+max_per_request]
                fcodes = ",".join(batch)

                url = f"https://fundmobapi.eastmoney.com/FundMApi/FundEstimate.ashx?Fcodes={fcodes}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://m.fund.eastmoney.com/'
                }

                response = requests.get(url, headers=headers, timeout=10)
                data = response.json()

                if data.get('Datas'):
                    for item in data['Datas']:
                        fund_code = item.get('FCODE', '')
                        if fund_code:
                            results[fund_code] = {
                                'fund_code': fund_code,
                                'estimate_net_value': float(item.get('GSZ', 0) or 0),
                                'estimate_change_rate': float(item.get('GSZZL', 0) or 0),
                                'estimate_time': item.get('GZTIME', ''),
                                'net_value': item.get('DWJZ', ''),
                                'unit_net_value': float(item.get('DWJZ', 0) or 0)
                            }
        except Exception as e:
            print(f"东方财富估值批量接口请求失败: {e}")

        return results
