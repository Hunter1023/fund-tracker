import requests
import json
import time
from functools import lru_cache, wraps
from bs4 import BeautifulSoup
from config import DATA_SOURCES
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
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

# 全局缓存字典，用于存储成功获取的数据
_fund_data_cache = {}
_fund_data_cache_time = {}
_cache_lock = threading.Lock()
CACHE_EXPIRY_SECONDS = 300  # 缓存5分钟

def get_cached_fund_data(fund_code):
    """获取缓存的基金数据，检查是否过期"""
    with _cache_lock:
        cache_time = _fund_data_cache_time.get(fund_code)
        if cache_time:
            elapsed = time.time() - cache_time
            if elapsed > CACHE_EXPIRY_SECONDS:
                # 缓存已过期，删除
                _fund_data_cache.pop(fund_code, None)
                _fund_data_cache_time.pop(fund_code, None)
                return None
        return _fund_data_cache.get(fund_code)

def set_cached_fund_data(fund_code, data):
    """设置缓存的基金数据（仅存储有效数据，带过期时间）"""
    with _cache_lock:
        if data and (data.get('one_month_rate') != 0 or
                     data.get('three_month_rate') != 0 or
                     data.get('one_year_rate') != 0 or
                     data.get('daily_change_rate') != 0 or
                     data.get('unit_net_value') != 0):
            _fund_data_cache[fund_code] = data
            _fund_data_cache_time[fund_code] = time.time()

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
        """获取单只基金涨跌幅数据，优先级: 估值接口 > pingzhongdata"""
        one_month_rate = 0
        three_month_rate = 0
        one_year_rate = 0
        daily_change_rate = 0
        fsrq = ''
        unit_net_value = 0

        # 尝试1: 估值接口（天天基金网，最稳定可靠）
        try:
            gz_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
            gz_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}
            gz_response = requests.get(gz_url, headers=gz_headers, timeout=5)
            if gz_response.status_code == 200:
                import re as _re0
                gz_match = _re0.search(r'jsonpgz\((.+)\);?', gz_response.text)
                if gz_match:
                    gz_data = json.loads(gz_match.group(1))
                    fsrq = gz_data.get('jzrq', '')
                    gz_dwjz = gz_data.get('dwjz', '')
                    gz_gszzl = gz_data.get('gszzl', '')

                    if gz_dwjz:
                        try:
                            unit_net_value = float(gz_dwjz)
                        except (ValueError, TypeError):
                            pass

                    if gz_gszzl:
                        try:
                            daily_change_rate = float(gz_gszzl)
                        except (ValueError, TypeError):
                            pass

                    print(f"估值接口获取基金 {fund_code}: fsrq={fsrq}, nav={unit_net_value}, daily={daily_change_rate}")
        except Exception as e:
            print(f"估值接口获取基金 {fund_code} 数据失败: {e}")

        # 尝试2: pingzhongdata 接口（补充月/年涨跌幅）
        try:
            import re as _re
            url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js?v={int(time.time())}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': f'http://fundf10.eastmoney.com/jjjz_{fund_code}.html'
            }
            response = requests.get(url, headers=headers, timeout=8)
            content = response.text

            m = _re.search(r'var\s+syl_1y\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    one_month_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            m = _re.search(r'var\s+syl_3y\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    three_month_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            m = _re.search(r'var\s+syl_1n\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    one_year_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            # 估值接口失败时，从 Data_netWorthTrend 兜底获取 fsrq/nav/daily
            if not fsrq:
                m = _re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);', content, _re.DOTALL)
                if m:
                    try:
                        net_worth_data = json.loads(m.group(1))
                        if net_worth_data:
                            last = net_worth_data[-1]
                            from datetime import datetime as _dt
                            fsrq = _dt.fromtimestamp(last['x'] / 1000).strftime('%Y-%m-%d')
                            unit_net_value = last.get('y', 0)
                            pz_daily = float(last.get('equityReturn', 0) or 0)
                            if daily_change_rate == 0 and pz_daily != 0:
                                daily_change_rate = pz_daily
                    except Exception as e:
                        print(f"解析基金 {fund_code} 净值趋势数据失败: {e}")

            print(f"pingzhongdata获取基金 {fund_code}: 1m={one_month_rate}, 3m={three_month_rate}, 1y={one_year_rate}")
        except Exception as e:
            print(f"pingzhongdata获取基金 {fund_code} 涨跌幅数据失败: {e}")

        # 两个接口都失败，返回缓存数据
        if one_month_rate == 0 and three_month_rate == 0 and one_year_rate == 0 and daily_change_rate == 0 and unit_net_value == 0:
            cached_data = get_cached_fund_data(fund_code)
            if cached_data:
                print(f"使用缓存数据返回基金 {fund_code} 的涨跌幅数据")
                return cached_data
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
    def get_fund_rates(fund_code, timestamp=None):
        # 使用 timestamp 作为缓存键的一部分，实现按时间过期
        cache_key = f"{fund_code}_{timestamp or int(time.time() // 3600)}"
        result = DataFetcher._get_fund_rates_cached(cache_key, fund_code, timestamp)
        # 如果缓存的结果是全0/空（API失败），不使用缓存，直接重新获取
        if result and result.get('one_month_rate') == 0 and result.get('three_month_rate') == 0 and result.get('one_year_rate') == 0 and result.get('daily_change_rate') == 0 and not result.get('fsrq'):
            # 清除缓存中这个无效结果
            DataFetcher._get_fund_rates_cached.cache_clear()
            result = DataFetcher._get_fund_rates_no_retry(fund_code, timestamp)
        return result

    @staticmethod
    @lru_cache(maxsize=512)
    def _get_fund_rates_cached(cache_key, fund_code, timestamp):
        # 实际的数据获取逻辑，带重试
        return DataFetcher._get_fund_rates_with_retry(fund_code, timestamp)

    @staticmethod
    @retry_on_failure(max_retries=2, delay=1, backoff=2)
    def _get_fund_rates_with_retry(fund_code, timestamp):
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

            # 如果使用东方财富API没有获取到数据，尝试使用天天基金pingzhongdata接口
            if one_month_rate == 0 and three_month_rate == 0 and one_year_rate == 0 and daily_change_rate == 0:
                print(f"东方财富API未获取到基金 {fund_code} 的数据，尝试使用pingzhongdata接口")
                url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js?v={int(time.time())}"
                try:
                    response = requests.get(url, headers=headers, timeout=8)
                    response.encoding = 'utf-8'
                    content = response.text

                    import re
                    # 提取涨跌幅: syl_1n=近1年, syl_3y=近3月, syl_1y=近1月
                    m = re.search(r'var\s+syl_1y\s*=\s*"([-+]?\d+\.?\d*)"', content)
                    if m:
                        try:
                            one_month_rate = float(m.group(1))
                            print(f"pingzhongdata提取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                        except (ValueError, TypeError):
                            pass

                    m = re.search(r'var\s+syl_3y\s*=\s*"([-+]?\d+\.?\d*)"', content)
                    if m:
                        try:
                            three_month_rate = float(m.group(1))
                            print(f"pingzhongdata提取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                        except (ValueError, TypeError):
                            pass

                    m = re.search(r'var\s+syl_1n\s*=\s*"([-+]?\d+\.?\d*)"', content)
                    if m:
                        try:
                            one_year_rate = float(m.group(1))
                            print(f"pingzhongdata提取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                        except (ValueError, TypeError):
                            pass

                    # 提取最新净值和日期从 Data_netWorthTrend
                    m = re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);', content, re.DOTALL)
                    if m:
                        try:
                            net_worth_data = json.loads(m.group(1))
                            if net_worth_data:
                                last = net_worth_data[-1]
                                from datetime import datetime as _dt
                                fsrq = _dt.fromtimestamp(last['x'] / 1000).strftime('%Y-%m-%d')
                                unit_net_value = last.get('y', 0)
                                daily_change_rate = float(last.get('equityReturn', 0) or 0)
                                print(f"pingzhongdata提取基金 {fund_code} 净值: {unit_net_value}, 日增长率: {daily_change_rate}, 日期: {fsrq}")
                        except Exception as e:
                            print(f"解析基金 {fund_code} 净值趋势数据失败: {e}")

                except Exception as e:
                    print(f"使用pingzhongdata接口获取基金涨跌幅数据失败: {e}")

            # 如果fundmobapi和pingzhongdata都未获取到fsrq，尝试LSJZ接口
            if not fsrq:
                try:
                    lsjz_url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex=1&pageSize=1"
                    lsjz_headers = {
                        "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                    lsjz_response = requests.get(lsjz_url, headers=lsjz_headers, timeout=8)
                    lsjz_data = lsjz_response.json()
                    if lsjz_data.get('Data') and lsjz_data['Data'].get('LSJZList'):
                        latest = lsjz_data['Data']['LSJZList'][0]
                        if latest.get('DWJZ'):
                            fsrq = latest.get('FSRQ', '')
                            if unit_net_value == 0:
                                try:
                                    unit_net_value = float(latest.get('DWJZ', 0))
                                except (ValueError, TypeError):
                                    pass
                            if daily_change_rate == 0 and latest.get('JZZZL'):
                                try:
                                    daily_change_rate = float(latest.get('JZZZL', 0))
                                except (ValueError, TypeError):
                                    pass
                            print(f"LSJZ接口获取基金 {fund_code} 最新数据: fsrq={fsrq}, nav={unit_net_value}, daily_change={daily_change_rate}")
                except Exception as e:
                    print(f"LSJZ接口获取基金 {fund_code} 涨跌幅数据失败: {e}")

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
    @retry_on_failure(max_retries=1, delay=1)
    def get_fund_history_simple(fund_code, timestamp=None):
        """
        获取基金基本涨跌幅数据，不获取完整的历史净值
        :param fund_code: 基金代码
        :param timestamp: 时间戳（用于缓存过期）
        :return: 涨跌幅数据
        """
        print(f"开始获取基金 {fund_code} 的基本涨跌幅数据")

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

        # 尝试1: fundmobapi 接口
        try:
            url = f"https://fundmobapi.eastmoney.com/FundMApi/FundBaseTypeInformation.ashx?FCODE={fund_code}&deviceid=Wap&plat=Wap&product=EFund&version=2.0.0&Uid="
            response = requests.get(url, headers=headers, timeout=3)
            print(f"东方财富API响应状态码: {response.status_code}")
            data = response.json()
            print(f"东方财富API返回数据: {data}")

            # 解析涨跌幅数据
            if data.get('Datas'):
                fsrq = data['Datas'].get('FSRQ', '')
                print(f"基金 {fund_code} 的FSRQ: {fsrq}")
                field_mappings = {
                    'one_month': ['SYL_1M', 'syl_1m', 'SYL_Y', 'syl_y', '近1月', 'OneMonth', 'syly', 'SYLY', '1m', '1M'],
                    'three_month': ['SYL_3M', 'syl_3m', 'SYL_3Y', 'syl_3y', '近3月', 'ThreeMonth', 'syl3y', 'SYL3Y', '3m', '3M'],
                    'one_year': ['SYL_1N', 'syl_1n', '近1年', 'OneYear', 'syl1n', 'SYL1N', '1y', '1Y'],
                    'daily': ['JZZZL', 'jzzzl', 'RZDF', 'rzdf', '日涨跌幅', 'DailyChange', 'rdf', 'RDF', 'daily_change', 'DAILY_CHANGE', 'zdf', 'ZDF'],
                    'unit_net_value': ['DWJZ', 'dwjz', '单位净值', 'UnitNetValue']
                }

                for field in field_mappings['one_month']:
                    if field in data['Datas']:
                        try:
                            one_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1月收益率: {one_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")

                for field in field_mappings['three_month']:
                    if field in data['Datas']:
                        try:
                            three_month_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近3月收益率: {three_month_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")

                for field in field_mappings['one_year']:
                    if field in data['Datas']:
                        try:
                            one_year_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的近1年收益率: {one_year_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")

                for field in field_mappings['daily']:
                    if field in data['Datas']:
                        try:
                            daily_change_rate = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的日涨跌幅: {daily_change_rate}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")

                for field in field_mappings['unit_net_value']:
                    if field in data['Datas']:
                        try:
                            unit_net_value = float(data['Datas'][field])
                            print(f"使用字段 {field} 获取基金 {fund_code} 的单位净值: {unit_net_value}")
                            break
                        except (ValueError, TypeError) as e:
                            print(f"字段 {field} 转换失败: {e}")

            # 如果fundmobapi成功获取到有效数据，直接返回
            if one_month_rate != 0 or three_month_rate != 0 or one_year_rate != 0 or daily_change_rate != 0 or unit_net_value != 0:
                print(f"基金 {fund_code} fundmobapi获取成功: 1m={one_month_rate}, 3m={three_month_rate}, 1y={one_year_rate}, daily={daily_change_rate}, fsrq={fsrq}")
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
            print(f"fundmobapi获取基金 {fund_code} 数据失败: {e}")

        # 尝试2: 回退到 pingzhongdata 接口
        try:
            print(f"基金 {fund_code} 回退到pingzhongdata接口")
            import re
            url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js?v={int(time.time())}"
            response = requests.get(url, headers=headers, timeout=8)
            response.encoding = 'utf-8'
            content = response.text

            # 提取涨跌幅: syl_1n=近1年, syl_3y=近3月, syl_1y=近1月
            m = re.search(r'var\s+syl_1y\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    one_month_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            m = re.search(r'var\s+syl_3y\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    three_month_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            m = re.search(r'var\s+syl_1n\s*=\s*"([-+]?\d+\.?\d*)"', content)
            if m:
                try:
                    one_year_rate = float(m.group(1))
                except (ValueError, TypeError):
                    pass

            # 提取最新净值和日期从 Data_netWorthTrend
            m = re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);', content, re.DOTALL)
            if m:
                try:
                    net_worth_data = json.loads(m.group(1))
                    if net_worth_data:
                        last = net_worth_data[-1]
                        from datetime import datetime as _dt
                        fsrq = _dt.fromtimestamp(last['x'] / 1000).strftime('%Y-%m-%d')
                        unit_net_value = last.get('y', 0)
                        daily_change_rate = float(last.get('equityReturn', 0) or 0)
                        print(f"pingzhongdata提取基金 {fund_code}: fsrq={fsrq}, 净值={unit_net_value}, 日涨幅={daily_change_rate}")
                except Exception as e:
                    print(f"解析基金 {fund_code} 净值趋势数据失败: {e}")

        except Exception as e:
            print(f"pingzhongdata接口获取基金 {fund_code} 数据失败: {e}")

        print(f"基金 {fund_code} 的最终涨跌幅数据: one_month_rate={one_month_rate}, three_month_rate={three_month_rate}, one_year_rate={one_year_rate}, daily_change_rate={daily_change_rate}, unit_net_value={unit_net_value}, fsrq={fsrq}")
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

    _fund_history_cache = {}
    _fund_history_cache_lock = threading.Lock()

    @staticmethod
    def get_fund_history(fund_code, timestamp=None):
        if timestamp is None:
            timestamp = int(time.time() / 3600)

        cache_key = f"{fund_code}_{timestamp}"
        with DataFetcher._fund_history_cache_lock:
            if cache_key in DataFetcher._fund_history_cache:
                return DataFetcher._fund_history_cache[cache_key]

        result = DataFetcher._get_fund_history_impl(fund_code, timestamp)

        with DataFetcher._fund_history_cache_lock:
            DataFetcher._fund_history_cache[cache_key] = result
            if len(DataFetcher._fund_history_cache) > 256:
                oldest_keys = list(DataFetcher._fund_history_cache.keys())[:128]
                for k in oldest_keys:
                    del DataFetcher._fund_history_cache[k]

        return result

    @staticmethod
    def _get_fund_history_impl(fund_code, timestamp):
            rates_data = DataFetcher.get_fund_rates(fund_code, timestamp)
            one_month_rate = rates_data.get('one_month_rate', 0)
            three_month_rate = rates_data.get('three_month_rate', 0)
            one_year_rate = rates_data.get('one_year_rate', 0)
            daily_change_rate = rates_data.get('daily_change_rate', 0)
            fsrq = rates_data.get('fsrq', '')
            unit_net_value = rates_data.get('unit_net_value', 0)

            # 如果 get_fund_rates 返回全0数据（API失败），回退到 _get_fund_rates_no_retry
            if one_month_rate == 0 and three_month_rate == 0 and one_year_rate == 0 and daily_change_rate == 0 and not fsrq:
                print(f"基金 {fund_code} get_fund_rates 返回全0数据，回退到 _get_fund_rates_no_retry")
                fallback_data = DataFetcher._get_fund_rates_no_retry(fund_code, timestamp)
                if fallback_data:
                    one_month_rate = fallback_data.get('one_month_rate', 0)
                    three_month_rate = fallback_data.get('three_month_rate', 0)
                    one_year_rate = fallback_data.get('one_year_rate', 0)
                    daily_change_rate = fallback_data.get('daily_change_rate', 0)
                    fsrq = fallback_data.get('fsrq', '')
                    unit_net_value = fallback_data.get('unit_net_value', 0)

            net_values = []
            try:
                # real-time-fund 项目使用的东方财富K线接口
                # klt=103 表示日线数据，lmt=500 表示获取最近500条记录
                net_values_url = f"https://push2.eastmoney.com/api/qt/fund/kline/get?secid=0.{fund_code}&klt=103&fqt=0&end=20990101&lmt=500"
                headers = {
                    "Referer": f"https://fund.eastmoney.com/{fund_code}.html",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Connection": "keep-alive"
                }
                print(f"基金 {fund_code} 正在请求历史净值: {net_values_url}")
                try:
                    net_values_response = requests.get(net_values_url, headers=headers, timeout=10)
                    print(f"基金 {fund_code} 请求状态码: {net_values_response.status_code}")

                    if net_values_response.status_code == 404:
                        print(f"基金 {fund_code} K线接口返回404，跳过并尝试LSJZ接口")
                    else:
                        net_values_response.encoding = 'utf-8'
                        try:
                            net_values_data = net_values_response.json()
                            print(f"基金 {fund_code} 返回数据结构: keys={list(net_values_data.keys())}")
                            if net_values_data.get('data'):
                                print(f"基金 {fund_code} data字段存在，包含keys={list(net_values_data['data'].keys())}")
                                if net_values_data['data'].get('klines'):
                                    klines = net_values_data['data']['klines']
                                    print(f"基金 {fund_code} klines长度: {len(klines)}")
                                    for kline in klines:
                                        parts = kline.split(',')
                                        if len(parts) >= 6:
                                            net_values.append({
                                                'date': parts[0],
                                                'unit_net_value': parts[2],
                                                'cumulative_net_value': parts[5],
                                                'change_rate': '0'
                                            })
                                    print(f"基金 {fund_code} 历史净值加载成功，获取 {len(net_values)} 条数据")
                                else:
                                    print(f"基金 {fund_code} klines字段为空或不存在")
                            else:
                                print(f"基金 {fund_code} data字段为空或不存在，完整响应: {json.dumps(net_values_data)[:500]}")
                        except json.JSONDecodeError:
                            print(f"基金 {fund_code} 历史净值接口返回非JSON数据: {net_values_response.text[:200]}")
                except Exception as e:
                    print(f"基金 {fund_code} K线接口请求失败: {e}，将尝试回退接口")

                # 如果K线接口失败，回退到pingzhongdata接口（Data_netWorthTrend）
                if not net_values:
                    print(f"基金 {fund_code} K线接口返回空数据，尝试pingzhongdata接口")
                    try:
                        import re as _re
                        from datetime import datetime as _dt
                        pz_url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js?v={int(time.time())}"
                        pz_headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                            'Referer': f'http://fundf10.eastmoney.com/jjjz_{fund_code}.html'
                        }
                        pz_response = requests.get(pz_url, headers=pz_headers, timeout=10)
                        pz_content = pz_response.text

                        m = _re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);', pz_content, _re.DOTALL)
                        if m:
                            net_worth_data = json.loads(m.group(1))
                            # 按时间戳倒序排列，最新的在前面
                            net_worth_data.sort(key=lambda x: x['x'], reverse=True)
                            for item in net_worth_data:
                                date_str = _dt.fromtimestamp(item['x'] / 1000).strftime('%Y-%m-%d')
                                net_values.append({
                                    'date': date_str,
                                    'unit_net_value': str(item.get('y', 0)),
                                    'cumulative_net_value': '',
                                    'change_rate': str(item.get('equityReturn', 0) or 0)
                                })
                            print(f"基金 {fund_code} pingzhongdata接口加载成功，获取 {len(net_values)} 条数据")
                        else:
                            print(f"基金 {fund_code} pingzhongdata接口未找到Data_netWorthTrend数据")
                    except Exception as e:
                        print(f"基金 {fund_code} pingzhongdata接口获取历史净值失败: {e}")

                # 如果pingzhongdata也失败，回退到传统LSJZ接口
                if not net_values:
                    print(f"基金 {fund_code} pingzhongdata接口返回空数据，尝试LSJZ接口")
                    page_index = 1
                    page_size = 100
                    while True:
                        lsjz_url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex={page_index}&pageSize={page_size}"
                        lsjz_headers = {
                            "Referer": f"https://fundf10.eastmoney.com/jjjz_{fund_code}.html",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        print(f"基金 {fund_code} 正在请求LSJZ接口: {lsjz_url}")
                        lsjz_response = requests.get(lsjz_url, headers=lsjz_headers, timeout=10)
                        print(f"基金 {fund_code} LSJZ接口状态码: {lsjz_response.status_code}")
                        try:
                            lsjz_data = lsjz_response.json()
                            print(f"基金 {fund_code} LSJZ返回数据: {json.dumps(lsjz_data)[:300]}")
                            if lsjz_data.get('Data') and lsjz_data['Data'].get('LSJZList'):
                                for item in lsjz_data['Data']['LSJZList']:
                                    if item.get('DWJZ'):
                                        net_values.append({
                                            'date': item.get('FSRQ'),
                                            'unit_net_value': item.get('DWJZ'),
                                            'cumulative_net_value': item.get('LJJZ'),
                                            'change_rate': item.get('JZZZL')
                                        })

                                total_count = lsjz_data.get('TotalCount', 0)
                                if len(net_values) >= total_count or len(net_values) >= 500:
                                    break
                                page_index += 1
                            else:
                                break
                        except Exception as e:
                            print(f"基金 {fund_code} LSJZ接口解析失败: {e}")
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

                # 如果fsrq为空，从历史净值数据中获取最新日期
                if not fsrq and latest_lsjz_date:
                    fsrq = latest_lsjz_date
                    print(f"基金 {fund_code} get_fund_rates未返回日期，使用LSJZList最新日期: {fsrq}")

                if unit_net_value == 0 and latest_lsjz_nav > 0:
                    unit_net_value = latest_lsjz_nav
                    print(f"基金 {fund_code} get_fund_rates未返回净值，使用LSJZList数据更新unit_net_value: {unit_net_value}")
                elif fsrq == latest_lsjz_date and latest_lsjz_nav > 0 and unit_net_value != latest_lsjz_nav:
                    print(f"基金 {fund_code} 净值数据不一致(API: {unit_net_value}, LSJZList: {latest_lsjz_nav}, 日期: {fsrq})，使用LSJZList数据")
                    unit_net_value = latest_lsjz_nav

            # 用估值接口交叉验证fsrq，解决CDN缓存导致日期偏旧的问题
            try:
                gz_url = f"http://fundgz.1234567.com.cn/js/{fund_code}.js"
                gz_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/'}
                gz_response = requests.get(gz_url, headers=gz_headers, timeout=5)
                if gz_response.status_code == 200:
                    import re as _re2
                    gz_match = _re2.search(r'jsonpgz\((.+)\);?', gz_response.text)
                    if gz_match:
                        gz_data = json.loads(gz_match.group(1))
                        gz_jzrq = gz_data.get('jzrq', '')  # 净值日期
                        gz_dwjz = gz_data.get('dwjz', '')   # 单位净值
                        gz_gsz = gz_data.get('gsz', '')      # 估算净值
                        gz_gszzl = gz_data.get('gszzl', '')  # 估算涨跌幅
                        gz_gztime = gz_data.get('gztime', '') # 估值时间

                        # 用估值接口交叉验证fsrq，解决pingzhongdata日期偏移的问题
                        # 估值接口: jzrq=上一个确认净值日期, dwjz=该日单位净值, gztime=估值时间
                        # pingzhongdata的Data_netWorthTrend时间戳有时偏早1天
                        # 验证逻辑: 如果估值接口的dwjz与pingzhongdata最新净值不一致，
                        # 说明pingzhongdata已包含更新一天的确认净值（日期标错了），需要修正
                        gz_date = gz_gztime.split(' ')[0] if gz_gztime else ''
                        if gz_date and fsrq and gz_date > fsrq:
                            # gz_date比fsrq新，但需要确认pingzhongdata确实已包含新净值
                            # 比较估值接口的dwjz（已确认净值）与pingzhongdata最新净值
                            try:
                                gz_dwjz_val = float(gz_dwjz) if gz_dwjz else 0
                            except (ValueError, TypeError):
                                gz_dwjz_val = 0

                            if gz_dwjz_val > 0 and unit_net_value > 0 and abs(gz_dwjz_val - unit_net_value) > 0.0001:
                                # 净值不一致，说明pingzhongdata的最新数据是gz_date那天的确认净值
                                print(f"基金 {fund_code} 估值接口已确认净值({gz_dwjz_val})与pingzhongdata最新净值({unit_net_value})不一致，pingzhongdata日期偏移，修正fsrq为{gz_date}")
                                fsrq = gz_date
                            else:
                                # 净值一致，说明pingzhongdata最新数据就是jzrq那天的，日期没有偏移
                                print(f"基金 {fund_code} 估值接口已确认净值({gz_dwjz_val})与pingzhongdata最新净值({unit_net_value})一致，fsrq保持{fsrq}")
                        elif gz_jzrq and fsrq and gz_jzrq > fsrq:
                            print(f"基金 {fund_code} 估值接口净值日期({gz_jzrq})比fsrq({fsrq})更新，使用估值接口日期")
                            fsrq = gz_jzrq
                            if gz_dwjz:
                                try:
                                    unit_net_value = float(gz_dwjz)
                                except (ValueError, TypeError):
                                    pass
                        elif (gz_date or gz_jzrq) and not fsrq:
                            fsrq = gz_date or gz_jzrq
                            print(f"基金 {fund_code} fsrq为空，使用估值接口日期: {fsrq}")
            except Exception as e:
                print(f"基金 {fund_code} 估值接口校验失败: {e}")

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

            return DataFetcher._get_fund_history_impl(fund_code, timestamp)

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
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._get_fund_rates_no_retry, fund_code, None): fund_code
                    for fund_code in remaining_codes
                }
                try:
                    for future in as_completed(future_to_fund, timeout=15):
                        fund_code = future_to_fund[future]
                        try:
                            data = future.result(timeout=8)
                            if data:
                                results[fund_code] = data
                        except Exception as e:
                            print(f"单只基金接口获取 {fund_code} 数据失败: {e}")
                except TimeoutError:
                    print(f"部分基金数据获取超时，已获取 {len(results)} 个，剩余 {len(remaining_codes) - len(results)} 个未完成")
                    # 超时情况下，继续处理已完成的任务
                    for future in future_to_fund:
                        if future.done():
                            fund_code = future_to_fund[future]
                            if fund_code not in results:
                                try:
                                    data = future.result()
                                    if data:
                                        results[fund_code] = data
                                except Exception as e:
                                    print(f"获取超时任务 {fund_code} 结果失败: {e}")

        return results

    @staticmethod
    def _fetch_eastmoney_batch(fund_codes):
        """
        使用天天基金 pingzhongdata 接口并发获取基金涨跌幅数据
        该接口可达性高，响应快（约0.1秒/只）
        """
        results = {}
        if not fund_codes:
            return results

        def _fetch_single(fund_code):
            try:
                url = f"http://fund.eastmoney.com/pingzhongdata/{fund_code}.js?v={int(time.time())}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': f'http://fundf10.eastmoney.com/jjjz_{fund_code}.html'
                }
                response = requests.get(url, headers=headers, timeout=8)
                content = response.text

                import re as _re
                one_month_rate = 0
                three_month_rate = 0
                one_year_rate = 0
                daily_change_rate = 0
                fsrq = ''
                unit_net_value = 0

                # 提取涨跌幅: syl_1n=近1年, syl_3y=近3月, syl_1y=近1月
                m = _re.search(r'var\s+syl_1y\s*=\s*"([-+]?\d+\.?\d*)"', content)
                if m:
                    try:
                        one_month_rate = float(m.group(1))
                    except (ValueError, TypeError):
                        pass

                m = _re.search(r'var\s+syl_3y\s*=\s*"([-+]?\d+\.?\d*)"', content)
                if m:
                    try:
                        three_month_rate = float(m.group(1))
                    except (ValueError, TypeError):
                        pass

                m = _re.search(r'var\s+syl_1n\s*=\s*"([-+]?\d+\.?\d*)"', content)
                if m:
                    try:
                        one_year_rate = float(m.group(1))
                    except (ValueError, TypeError):
                        pass

                # 提取最新净值和日期从 Data_netWorthTrend
                m = _re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);', content, _re.DOTALL)
                if m:
                    try:
                        net_worth_data = json.loads(m.group(1))
                        if net_worth_data:
                            last = net_worth_data[-1]
                            from datetime import datetime as _dt
                            fsrq = _dt.fromtimestamp(last['x'] / 1000).strftime('%Y-%m-%d')
                            unit_net_value = last.get('y', 0)
                            daily_change_rate = float(last.get('equityReturn', 0) or 0)
                    except Exception as e:
                        print(f"解析基金 {fund_code} 净值趋势数据失败: {e}")

                return fund_code, {
                    'fund_code': fund_code,
                    'one_month_rate': one_month_rate,
                    'three_month_rate': three_month_rate,
                    'one_year_rate': one_year_rate,
                    'daily_change_rate': daily_change_rate,
                    'fsrq': fsrq,
                    'unit_net_value': unit_net_value
                }
            except Exception as e:
                print(f"pingzhongdata接口获取基金 {fund_code} 数据失败: {e}")
                return fund_code, None

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_fund = {
                    executor.submit(_fetch_single, fund_code): fund_code
                    for fund_code in fund_codes
                }
                try:
                    for future in as_completed(future_to_fund, timeout=15):
                        try:
                            fund_code, data = future.result(timeout=8)
                            if data:
                                results[fund_code] = data
                        except Exception as e:
                            print(f"获取基金数据失败: {e}")
                except TimeoutError:
                    print(f"pingzhongdata批量请求超时，已获取 {len(results)} 个，剩余 {len(fund_codes) - len(results)} 个未完成")
                    for future in future_to_fund:
                        if future.done():
                            try:
                                fund_code, data = future.result()
                                if data and fund_code not in results:
                                    results[fund_code] = data
                            except Exception:
                                pass
        except Exception as e:
            print(f"pingzhongdata批量请求异常: {e}")

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
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._fetch_tencent_single, fund_code): fund_code
                    for fund_code in fund_codes
                }

                try:
                    for future in as_completed(future_to_fund, timeout=10):
                        fund_code = future_to_fund[future]
                        try:
                            data = future.result(timeout=5)
                            if data:
                                results[fund_code] = data
                        except Exception as e:
                            print(f"腾讯基金接口获取 {fund_code} 数据失败: {e}")
                except TimeoutError:
                    print(f"腾讯基金批量请求超时，已获取 {len(results)} 个，剩余 {len(fund_codes) - len(results)} 个未完成")
                    # 超时情况下，继续处理已完成的任务
                    for future in future_to_fund:
                        if future.done():
                            fund_code = future_to_fund[future]
                            if fund_code not in results:
                                try:
                                    data = future.result()
                                    if data:
                                        results[fund_code] = data
                                except Exception as e:
                                    print(f"获取超时任务 {fund_code} 结果失败: {e}")
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
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_fund = {
                    executor.submit(DataFetcher._get_fund_valuation_no_retry, fund_code, None): fund_code
                    for fund_code in missing_codes
                }
                try:
                    for future in as_completed(future_to_fund, timeout=15):
                        fund_code = future_to_fund[future]
                        try:
                            data = future.result(timeout=5)
                            if data:
                                results[fund_code] = data
                        except Exception as e:
                            print(f"估值接口获取 {fund_code} 数据失败: {e}")
                except TimeoutError:
                    print(f"估值批量请求超时，已获取 {len(results)} 个，剩余 {len(missing_codes) - (len(results) - len(batch_result))} 个未完成")
                    # 超时情况下，继续处理已完成的任务
                    for future in future_to_fund:
                        if future.done():
                            fund_code = future_to_fund[future]
                            if fund_code not in results:
                                try:
                                    data = future.result()
                                    if data:
                                        results[fund_code] = data
                                except Exception as e:
                                    print(f"获取超时任务 {fund_code} 结果失败: {e}")

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

                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()  # 检查HTTP错误
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
                    else:
                        print(f"东方财富估值批量接口返回数据为空，批次: {fcodes[:50]}...")
                except requests.exceptions.RequestException as e:
                    print(f"东方财富估值批量接口请求失败(批次: {fcodes[:50]}...): {e}")
                except json.JSONDecodeError as e:
                    print(f"东方财富估值批量接口返回非JSON数据(批次: {fcodes[:50]}...): {e}")
        except Exception as e:
            print(f"东方财富估值批量接口处理异常: {e}")

        return results
