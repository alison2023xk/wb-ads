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
    
    def __init__(self, token: Optional[str] = None):
        """
        初始化采集器
        
        Args:
            token: WB API Token，如果提供则使用，否则从环境变量读取
        """
        self.token = token or WB_API_TOKEN
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
        使用 /adv/v0/auction/adverts 端点（与定时开关功能保持一致）
        """
        try:
            # 尝试使用 /adv/v0/auction/adverts 端点
            params = {"statuses": "4,7,8,9,11"}  # ready, completed, declined, active, paused
            resp = self._request("GET", "/adv/v0/auction/adverts", params=params)
            
            if resp.status_code != 200:
                # 如果失败，尝试备用端点
                resp2 = self._request("GET", "/adv/v2/list")
                if resp2.status_code == 200:
                    data = resp2.json()
                    if isinstance(data, dict):
                        campaigns = data.get("result", data.get("data", []))
                    elif isinstance(data, list):
                        campaigns = data
                    else:
                        campaigns = []
                    return campaigns
                else:
                    raise RuntimeError(f"获取广告列表失败: {resp.status_code} {resp.text}")
            
            data = resp.json()
            
            # 处理 /adv/v0/auction/adverts 返回的扁平化数组格式
            # 参考 streamlit_app.py 中的 wb_get_auction_adverts 函数
            adverts = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("adverts", data.get("data", []))
                if not items and "id" in data:
                    items = [data]
            else:
                items = []
            
            # 按ID分组合并
            adverts_dict = {}
            for item in items:
                if "id" in item:
                    adv_id = item["id"]
                    if adv_id not in adverts_dict:
                        adverts_dict[adv_id] = {
                            "id": adv_id,
                            "name": None,
                            "payment_type": None,
                            "status": None,
                            "placements": None,
                            "nm_settings": []
                        }
                
                if "settings" in item:
                    settings = item["settings"]
                    if isinstance(settings, dict):
                        if "id" in item:
                            adv_id = item["id"]
                        else:
                            adv_id = settings.get("id") or settings.get("advertId")
                        
                        if adv_id and adv_id in adverts_dict:
                            adverts_dict[adv_id]["name"] = settings.get("name") or settings.get("advertName")
                            adverts_dict[adv_id]["payment_type"] = settings.get("payment_type")
                            adverts_dict[adv_id]["placements"] = settings.get("placements")
                
                if "status" in item:
                    if "id" in item:
                        adv_id = item["id"]
                        if adv_id in adverts_dict:
                            adverts_dict[adv_id]["status"] = item["status"]
                
                if "nm_settings" in item:
                    if "id" in item:
                        adv_id = item["id"]
                        if adv_id in adverts_dict:
                            adverts_dict[adv_id]["nm_settings"] = item.get("nm_settings", [])
            
            # 如果上面的逻辑没有工作，尝试直接解析完整对象
            if not adverts_dict and items:
                for item in items:
                    if isinstance(item, dict):
                        advert = {
                            "id": item.get("id") or item.get("advertId"),
                            "name": item.get("name") or item.get("advertName") or item.get("title"),
                            "payment_type": item.get("payment_type"),
                            "status": item.get("status"),
                            "placements": item.get("placements"),
                            "nm_settings": item.get("nm_settings", [])
                        }
                        
                        if "settings" in item and isinstance(item["settings"], dict):
                            s = item["settings"]
                            if not advert["name"]:
                                advert["name"] = s.get("name") or s.get("advertName")
                            if not advert["payment_type"]:
                                advert["payment_type"] = s.get("payment_type")
                            if not advert["placements"]:
                                advert["placements"] = s.get("placements")
                        
                        if advert["id"] is not None:
                            adverts_dict[advert["id"]] = advert
            
            adverts = list(adverts_dict.values())
            return adverts
            
        except Exception as e:
            raise RuntimeError(f"获取广告列表异常: {e}")
    
    def get_campaign_detail(self, campaign_id: int) -> Dict:
        """
        获取广告活动的详细信息
        GET /adv/v0/params 或 /adv/v1/upd
        
        Args:
            campaign_id: 广告活动ID（整数）
        """
        # 确保campaign_id是整数
        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            raise ValueError(f"无效的广告ID: {campaign_id}")
        
        # 尝试获取广告详情
        endpoints_to_try = [
            ("/adv/v0/params", {"id": campaign_id}),
            ("/adv/v1/upd", {"id": campaign_id}),
        ]
        
        for endpoint, params in endpoints_to_try:
            try:
                resp = self._request("GET", endpoint, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    return data
            except Exception:
                continue
        
        return {}
    
    def get_campaign_stats(self, campaign_id: int, date_from: str = None, 
                          date_to: str = None) -> Dict:
        """
        获取广告活动的统计数据
        尝试多个API端点
        
        Args:
            campaign_id: 广告活动ID（整数）
            date_from: 开始日期 (YYYY-MM-DD)，默认7天前
            date_to: 结束日期 (YYYY-MM-DD)，默认今天
        """
        if date_from is None:
            date_from = (datetime.now() - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        if date_to is None:
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        # 确保campaign_id是整数
        try:
            campaign_id = int(campaign_id)
        except (ValueError, TypeError):
            raise ValueError(f"无效的广告ID: {campaign_id}")
        
        # 尝试多个统计数据API端点
        endpoints_to_try = [
            ("/adv/v1/stat", {"id": campaign_id, "dateFrom": date_from, "dateTo": date_to}),
            ("/adv/v0/stat", {"id": campaign_id, "dateFrom": date_from, "dateTo": date_to}),
            ("/adv/v3/fullstats", {"id": campaign_id, "dateFrom": date_from, "dateTo": date_to}),
            ("/adv/v2/stat", {"id": campaign_id, "dateFrom": date_from, "dateTo": date_to}),
        ]
        
        for endpoint, params in endpoints_to_try:
            try:
                resp = self._request("GET", endpoint, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    return data
            except Exception as e:
                # 记录错误但继续尝试下一个端点
                continue
        
        # 如果所有端点都失败，返回空字典
        return {}
    
    def fetch_all_campaigns_data(self) -> pd.DataFrame:
        """
        获取所有广告活动的完整数据
        步骤1: 获取广告ID和状态
        步骤2: 通过广告ID获取每个广告的统计数据
        
        返回DataFrame，包含：campaignId, name, status, ctr, clicks, shows, spend, roi, position等
        """
        # 步骤1: 获取广告列表（ID和状态）
        campaigns_list = self.get_campaigns_list()
        
        if not campaigns_list:
            return pd.DataFrame()
        
        all_data = []
        total = len(campaigns_list)
        
        # 使用进度条显示（如果在Streamlit环境中）
        try:
            import streamlit as st
            progress_bar = st.progress(0)
            status_text = st.empty()
        except:
            progress_bar = None
            status_text = None
        
        # 步骤2: 对每个广告，获取详细数据
        for idx, campaign in enumerate(campaigns_list):
            campaign_id = campaign.get("id") or campaign.get("campaignId")
            if not campaign_id:
                continue
            
            # 确保campaign_id是整数
            try:
                campaign_id = int(campaign_id)
            except (ValueError, TypeError):
                continue
            
            # 更新进度
            if progress_bar and status_text:
                progress = (idx + 1) / total
                progress_bar.progress(progress)
                status_text.text(f"步骤1/2: 获取广告 {idx + 1}/{total} (ID: {campaign_id})")
            
            # 先保存基本信息（ID和状态）
            campaign_data = {
                "campaignId": int(campaign_id),  # 确保是整数类型
                "name": campaign.get("name") or campaign.get("advertName", ""),
                "status": int(campaign.get("status", -1)) if campaign.get("status") is not None else -1,
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
            
            # 步骤2: 通过广告ID获取详细数据和统计数据
            if progress_bar and status_text:
                status_text.text(f"步骤2/2: 获取广告 {idx + 1}/{total} (ID: {campaign_id}) 的统计数据...")
            
            # 尝试获取广告详情
            try:
                detail = self.get_campaign_detail(campaign_id)
                if detail:
                    # 从详情中提取可能的数据
                    if isinstance(detail, dict):
                        # 尝试提取出价、关键词等信息
                        if "params" in detail:
                            params = detail["params"]
                            if isinstance(params, list) and len(params) > 0:
                                # 如果有参数列表，尝试提取第一个的关键词和SKU
                                first_param = params[0] if isinstance(params[0], dict) else {}
                                campaign_data["keyword"] = first_param.get("keyword", "")
                                campaign_data["sku"] = str(first_param.get("sku", ""))
            except Exception:
                pass
            
            # 尝试获取统计数据
            try:
                stats = self.get_campaign_stats(campaign_id)
                if stats:
                    # 尝试从不同格式的响应中提取数据
                    stats_data = stats.get("result", stats.get("data", stats.get("stats", [])))
                    
                    if isinstance(stats_data, list) and len(stats_data) > 0:
                        # 汇总统计数据
                        total_ctr = 0.0
                        total_clicks = 0
                        total_shows = 0
                        total_spend = 0.0
                        total_roi = 0.0
                        count = 0
                        
                        for stat in stats_data:
                            if isinstance(stat, dict):
                                # 尝试多种可能的字段名
                                ctr_val = stat.get("ctr") or stat.get("CTR") or 0.0
                                clicks_val = stat.get("clicks") or stat.get("Clicks") or 0
                                shows_val = stat.get("shows") or stat.get("Shows") or stat.get("views") or 0
                                spend_val = stat.get("spend") or stat.get("Spend") or stat.get("sum") or 0.0
                                roi_val = stat.get("roi") or stat.get("ROI") or 0.0
                                
                                total_ctr += float(ctr_val or 0.0)
                                total_clicks += int(clicks_val or 0)
                                total_shows += int(shows_val or 0)
                                total_spend += float(spend_val or 0.0)
                                total_roi += float(roi_val or 0.0)
                                count += 1
                        
                        if count > 0:
                            campaign_data["ctr"] = total_ctr / count
                            campaign_data["clicks"] = total_clicks
                            campaign_data["shows"] = total_shows
                            campaign_data["spend"] = total_spend
                            campaign_data["roi"] = total_roi / count
                    elif isinstance(stats, dict):
                        # 直接是字典格式
                        campaign_data["ctr"] = float(stats.get("ctr", stats.get("CTR", 0.0)) or 0.0)
                        campaign_data["clicks"] = int(stats.get("clicks", stats.get("Clicks", 0)) or 0)
                        campaign_data["shows"] = int(stats.get("shows", stats.get("Shows", stats.get("views", 0))) or 0)
                        campaign_data["spend"] = float(stats.get("spend", stats.get("Spend", stats.get("sum", 0.0))) or 0.0)
                        campaign_data["roi"] = float(stats.get("roi", stats.get("ROI", 0.0)) or 0.0)
            except Exception as e:
                # 统计数据获取失败，使用默认值0
                # 不打印错误，避免干扰用户
                pass
            
            all_data.append(campaign_data)
        
        # 清除进度条
        if progress_bar:
            progress_bar.empty()
        if status_text:
            status_text.empty()
        
        df = pd.DataFrame(all_data)
        
        # 确保campaignId是整数类型
        if "campaignId" in df.columns:
            df["campaignId"] = df["campaignId"].astype(int)
        
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

