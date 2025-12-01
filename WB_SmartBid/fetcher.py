# -*- coding: utf-8 -*-
"""
广告数据采集模块
负责从WB API拉取广告状态数据并缓存到本地
"""
import time
import requests
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

from config import (
    WB_API_TOKEN,
    WB_API_URL,
    REQUEST_TIMEOUT,
    RATE_LIMIT_PER_SECOND,
    CAMPAIGNS_CACHE_PATH,
    STATUS_LABELS
)


class RateLimiter:
    """简单的速率限制器"""
    def __init__(self, per_second: int):
        self.per_second = per_second
        self.last_request_time = 0.0
        self.requests_in_current_second = 0
        self.current_second = int(time.time())
    
    def wait_if_needed(self):
        """如果需要，等待以遵守速率限制"""
        now = time.time()
        current_second = int(now)
        
        if current_second != self.current_second:
            # 新的一秒，重置计数
            self.current_second = current_second
            self.requests_in_current_second = 0
        
        if self.requests_in_current_second >= self.per_second:
            # 需要等待到下一秒
            sleep_time = 1 - (now - current_second)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.current_second = int(time.time())
            self.requests_in_current_second = 0
        
        self.requests_in_current_second += 1


class WBFetcher:
    """WB广告数据采集器"""
    
    def __init__(self):
        self.token = WB_API_TOKEN
        self.base_url = WB_API_URL.rstrip("/")
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                 json_body: Optional[Dict] = None) -> requests.Response:
        """发送API请求，带速率限制"""
        self.rate_limiter.wait_if_needed()
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                timeout=REQUEST_TIMEOUT
            )
            return resp
        except requests.RequestException as e:
            raise RuntimeError(f"API请求失败: {e}")
    
    def get_campaigns_list(self) -> List[Dict]:
        """
        获取所有活跃广告活动列表
        GET /adv/v2/list
        """
        try:
            resp = self._request("GET", "/adv/v2/list")
            if resp.status_code != 200:
                raise RuntimeError(f"获取广告列表失败: {resp.status_code} {resp.text}")
            
            data = resp.json()
            # 处理不同的API返回格式
            if isinstance(data, dict):
                campaigns = data.get("result", data.get("data", []))
            elif isinstance(data, list):
                campaigns = data
            else:
                campaigns = []
            
            return campaigns
        except Exception as e:
            raise RuntimeError(f"获取广告列表异常: {e}")
    
    def get_campaign_stats(self, campaign_id: int, date_from: str = None, 
                          date_to: str = None) -> Dict:
        """
        获取广告活动的统计数据
        GET /adv/v3/fullstats
        
        Args:
            campaign_id: 广告活动ID
            date_from: 开始日期 (YYYY-MM-DD)，默认7天前
            date_to: 结束日期 (YYYY-MM-DD)，默认今天
        """
        if date_from is None:
            date_from = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        if date_to is None:
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        try:
            params = {
                "id": campaign_id,
                "dateFrom": date_from,
                "dateTo": date_to,
            }
            resp = self._request("GET", "/adv/v3/fullstats", params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"获取统计数据失败: {resp.status_code} {resp.text}")
            
            data = resp.json()
            return data
        except Exception as e:
            raise RuntimeError(f"获取统计数据异常: {e}")
    
    def fetch_all_campaigns_data(self) -> pd.DataFrame:
        """
        获取所有广告活动的完整数据（包括统计信息）
        返回DataFrame，包含：campaignId, name, status, ctr, clicks, shows, spend, roi, position等
        """
        campaigns_list = self.get_campaigns_list()
        
        all_data = []
        for campaign in campaigns_list:
            campaign_id = campaign.get("id") or campaign.get("campaignId")
            if not campaign_id:
                continue
            
            # 获取统计数据
            try:
                stats = self.get_campaign_stats(campaign_id)
                
                # 解析统计数据
                stats_data = stats.get("result", [])
                if isinstance(stats_data, list) and len(stats_data) > 0:
                    # 取最新的统计数据
                    latest_stat = stats_data[-1] if isinstance(stats_data[-1], dict) else {}
                    
                    # 提取关键指标
                    campaign_data = {
                        "campaignId": campaign_id,
                        "name": campaign.get("name") or campaign.get("advertName", ""),
                        "status": campaign.get("status", -1),
                        "status_label": STATUS_LABELS.get(campaign.get("status", -1), "unknown"),
                        "ctr": latest_stat.get("ctr", 0.0),
                        "clicks": latest_stat.get("clicks", 0),
                        "shows": latest_stat.get("shows", 0),
                        "spend": latest_stat.get("spend", 0.0),
                        "roi": latest_stat.get("roi", 0.0),
                        "position": latest_stat.get("position", 0),
                        "sku": latest_stat.get("sku", ""),
                        "keyword": latest_stat.get("keyword", ""),
                        "fetch_time": datetime.now().isoformat(),
                    }
                    all_data.append(campaign_data)
                else:
                    # 如果没有统计数据，至少保存基本信息
                    campaign_data = {
                        "campaignId": campaign_id,
                        "name": campaign.get("name") or campaign.get("advertName", ""),
                        "status": campaign.get("status", -1),
                        "status_label": STATUS_LABELS.get(campaign.get("status", -1), "unknown"),
                        "ctr": 0.0,
                        "clicks": 0,
                        "shows": 0,
                        "spend": 0.0,
                        "roi": 0.0,
                        "position": 0,
                        "sku": "",
                        "keyword": "",
                        "fetch_time": datetime.now().isoformat(),
                    }
                    all_data.append(campaign_data)
            except Exception as e:
                # 如果获取统计数据失败，至少保存基本信息
                print(f"警告: 获取广告 {campaign_id} 统计数据失败: {e}")
                campaign_data = {
                    "campaignId": campaign_id,
                    "name": campaign.get("name") or campaign.get("advertName", ""),
                    "status": campaign.get("status", -1),
                    "status_label": STATUS_LABELS.get(campaign.get("status", -1), "unknown"),
                    "ctr": 0.0,
                    "clicks": 0,
                    "shows": 0,
                    "spend": 0.0,
                    "roi": 0.0,
                    "position": 0,
                    "sku": "",
                    "keyword": "",
                    "fetch_time": datetime.now().isoformat(),
                }
                all_data.append(campaign_data)
        
        df = pd.DataFrame(all_data)
        
        # 保存到缓存
        if len(df) > 0:
            df.to_csv(CAMPAIGNS_CACHE_PATH, index=False, encoding="utf-8-sig")
        
        return df
    
    def get_campaign_bid(self, campaign_id: int, keyword: str = None, sku: str = None) -> Optional[float]:
        """
        获取当前出价
        注意：WB API可能没有直接获取出价的接口，这里可能需要通过其他方式获取
        """
        # 这里需要根据实际API文档实现
        # 暂时返回None，实际使用时需要根据API文档调整
        return None


if __name__ == "__main__":
    # 测试代码
    fetcher = WBFetcher()
    print("开始获取广告数据...")
    df = fetcher.fetch_all_campaigns_data()
    print(f"获取到 {len(df)} 条广告数据")
    print(df.head())

