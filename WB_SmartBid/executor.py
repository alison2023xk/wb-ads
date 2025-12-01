# -*- coding: utf-8 -*-
"""
出价执行模块
通过WB广告API自动更新出价
"""
import time
import requests
from typing import Dict, Optional, Tuple
from datetime import datetime

from config import (
    WB_API_TOKEN,
    WB_API_URL,
    REQUEST_TIMEOUT,
    RATE_LIMIT_PER_SECOND
)
from logger import BidLogger


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
            self.current_second = current_second
            self.requests_in_current_second = 0
        
        if self.requests_in_current_second >= self.per_second:
            sleep_time = 1 - (now - current_second)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.current_second = int(time.time())
            self.requests_in_current_second = 0
        
        self.requests_in_current_second += 1


class BidExecutor:
    """出价执行器"""
    
    def __init__(self):
        self.token = WB_API_TOKEN
        self.base_url = WB_API_URL.rstrip("/")
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
        self.logger = BidLogger()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 json_body: Optional[Dict] = None, max_retries: int = 3) -> requests.Response:
        """发送API请求，带重试机制"""
        self.rate_limiter.wait_if_needed()
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(max_retries):
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
                if attempt == max_retries - 1:
                    raise RuntimeError(f"API请求失败（已重试{max_retries}次）: {e}")
                time.sleep(2 ** attempt)  # 指数退避
        
        raise RuntimeError("请求失败")
    
    def update_bid(self, campaign_id: int, keyword: str, new_bid: float, 
                   sku: Optional[str] = None) -> Tuple[bool, str]:
        """
        更新广告出价
        PATCH /api/v3/campaigns/{id}/bids
        
        Args:
            campaign_id: 广告活动ID
            keyword: 关键词
            new_bid: 新出价
            sku: SKU（可选）
        
        Returns:
            (成功标志, 消息)
        """
        try:
            # 构建请求体
            payload = {
                "campaignId": campaign_id,
                "keyword": keyword,
                "bid": int(new_bid)  # 出价通常为整数
            }
            if sku:
                payload["sku"] = sku
            
            # 注意：实际API端点可能需要根据WB文档调整
            # 这里使用通用的端点格式
            endpoint = f"/adv/v3/campaigns/{campaign_id}/bids"
            
            resp = self._request("PATCH", endpoint, json_body=payload)
            
            if resp.status_code in [200, 201, 204]:
                # 记录成功日志
                self.logger.log_bid_change(
                    campaign_id=campaign_id,
                    keyword=keyword,
                    old_bid=None,  # 如果无法获取旧出价
                    new_bid=new_bid,
                    reason="策略自动调整",
                    success=True
                )
                return True, "出价更新成功"
            else:
                error_msg = f"HTTP {resp.status_code}: {resp.text}"
                # 记录失败日志
                self.logger.log_bid_change(
                    campaign_id=campaign_id,
                    keyword=keyword,
                    old_bid=None,
                    new_bid=new_bid,
                    reason="策略自动调整",
                    success=False,
                    error=error_msg
                )
                return False, error_msg
                
        except Exception as e:
            error_msg = f"更新出价异常: {e}"
            self.logger.log_bid_change(
                campaign_id=campaign_id,
                keyword=keyword,
                old_bid=None,
                new_bid=new_bid,
                reason="策略自动调整",
                success=False,
                error=error_msg
            )
            return False, error_msg
    
    def pause_campaign(self, campaign_id: int) -> Tuple[bool, str]:
        """
        暂停广告活动
        GET /adv/v0/pause
        """
        try:
            resp = self._request("GET", "/adv/v0/pause", params={"id": campaign_id})
            if resp.status_code == 200:
                self.logger.log_bid_change(
                    campaign_id=campaign_id,
                    keyword="",
                    old_bid=None,
                    new_bid=None,
                    reason="ROI连续低于目标，自动暂停",
                    success=True
                )
                return True, "暂停成功"
            else:
                return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"暂停异常: {e}"
    
    def get_current_bid(self, campaign_id: int, keyword: str) -> Optional[float]:
        """
        获取当前出价
        注意：WB API可能没有直接获取出价的接口，这里可能需要通过其他方式获取
        """
        # 这里需要根据实际API文档实现
        # 暂时返回None，实际使用时需要根据API文档调整
        return None


if __name__ == "__main__":
    # 测试代码
    executor = BidExecutor()
    print("出价执行器初始化完成")
    # 注意：实际测试需要有效的token和campaign_id

