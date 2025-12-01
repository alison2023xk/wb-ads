# -*- coding: utf-8 -*-
"""
日志与报警模块
保存系统运行记录、出价变化与异常状态
"""
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque

from config import LOG_PATH


class BidLogger:
    """出价日志记录器"""
    
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = Path(log_path) if log_path else Path(LOG_PATH)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化CSV文件（如果不存在）
        if not self.log_path.exists():
            self._init_csv()
    
    def _init_csv(self):
        """初始化CSV文件，写入表头"""
        with open(self.log_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "campaign_id", "keyword", "old_bid", "new_bid",
                "reason", "success", "error", "ctr", "roi", "shows", "clicks"
            ])
    
    def log_bid_change(self, campaign_id: int, keyword: str, old_bid: Optional[float],
                      new_bid: Optional[float], reason: str, success: bool,
                      error: Optional[str] = None, ctr: Optional[float] = None,
                      roi: Optional[float] = None, shows: Optional[int] = None,
                      clicks: Optional[int] = None):
        """
        记录出价变更日志
        
        Args:
            campaign_id: 广告活动ID
            keyword: 关键词
            old_bid: 旧出价
            new_bid: 新出价
            reason: 变更原因
            success: 是否成功
            error: 错误信息（如果有）
            ctr: 点击率
            roi: 投资回报率
            shows: 曝光量
            clicks: 点击量
        """
        timestamp = datetime.now().isoformat()
        
        with open(self.log_path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, campaign_id, keyword, old_bid, new_bid,
                reason, success, error, ctr, roi, shows, clicks
            ])
        
        # 检查是否需要报警
        if success and old_bid and new_bid:
            self._check_alerts(campaign_id, keyword, old_bid, new_bid, roi)
    
    def _check_alerts(self, campaign_id: int, keyword: str, old_bid: float,
                     new_bid: float, roi: Optional[float]):
        """检查是否需要触发报警"""
        # 报警规则1: 出价涨幅 > 50%
        if old_bid > 0:
            change_percent = abs((new_bid - old_bid) / old_bid) * 100
            if change_percent > 50:
                self._send_alert(
                    f"⚠️ 出价大幅变化: 广告 {campaign_id} 关键词 '{keyword}' "
                    f"出价从 {old_bid} 调整为 {new_bid} (变化 {change_percent:.1f}%)"
                )
        
        # 报警规则2: ROI过低
        if roi is not None and roi < 1.0:
            self._send_alert(
                f"⚠️ ROI过低: 广告 {campaign_id} 关键词 '{keyword}' ROI = {roi:.2f}"
            )
    
    def _send_alert(self, message: str):
        """发送报警（可扩展为Telegram Bot等）"""
        print(f"[ALERT] {datetime.now().isoformat()} - {message}")
        # TODO: 集成Telegram Bot推送通知
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict]:
        """获取最近的日志记录"""
        logs = []
        if not self.log_path.exists():
            return logs
        
        with open(self.log_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            # 取最后limit条
            for row in rows[-limit:]:
                logs.append({
                    "timestamp": row.get("timestamp", ""),
                    "campaign_id": row.get("campaign_id", ""),
                    "keyword": row.get("keyword", ""),
                    "old_bid": row.get("old_bid", ""),
                    "new_bid": row.get("new_bid", ""),
                    "reason": row.get("reason", ""),
                    "success": row.get("success", ""),
                    "error": row.get("error", ""),
                    "ctr": row.get("ctr", ""),
                    "roi": row.get("roi", ""),
                    "shows": row.get("shows", ""),
                    "clicks": row.get("clicks", ""),
                })
        
        return logs
    
    def get_campaign_logs(self, campaign_id: int, limit: int = 50) -> List[Dict]:
        """获取特定广告的日志记录"""
        all_logs = self.get_recent_logs(limit=1000)
        campaign_logs = [
            log for log in all_logs 
            if log.get("campaign_id") == str(campaign_id)
        ]
        return campaign_logs[-limit:]
    
    def check_roi_trend(self, campaign_id: int, keyword: str, periods: int = 3) -> bool:
        """
        检查ROI趋势
        返回True表示ROI连续periods周期下降
        """
        logs = self.get_campaign_logs(campaign_id, limit=periods * 2)
        keyword_logs = [
            log for log in logs 
            if log.get("keyword") == keyword and log.get("roi")
        ]
        
        if len(keyword_logs) < periods:
            return False
        
        # 提取ROI值
        roi_values = []
        for log in keyword_logs[-periods:]:
            try:
                roi = float(log.get("roi", 0))
                if roi > 0:
                    roi_values.append(roi)
            except (ValueError, TypeError):
                continue
        
        if len(roi_values) < periods:
            return False
        
        # 检查是否连续下降
        is_decreasing = all(
            roi_values[i] > roi_values[i + 1] 
            for i in range(len(roi_values) - 1)
        )
        
        return is_decreasing
    
    def check_no_shows(self, campaign_id: int, hours: int = 24) -> bool:
        """
        检查是否无曝光超过指定小时数
        """
        logs = self.get_campaign_logs(campaign_id, limit=100)
        if not logs:
            return False
        
        # 获取最近的日志
        latest_log = logs[-1]
        latest_time_str = latest_log.get("timestamp", "")
        if not latest_time_str:
            return False
        
        try:
            latest_time = datetime.fromisoformat(latest_time_str)
            hours_since = (datetime.now() - latest_time).total_seconds() / 3600
            
            shows = latest_log.get("shows", "0")
            try:
                shows_int = int(shows)
                if shows_int == 0 and hours_since >= hours:
                    return True
            except (ValueError, TypeError):
                pass
        except Exception:
            pass
        
        return False


class AlertManager:
    """报警管理器"""
    
    def __init__(self):
        self.roi_history: Dict[str, deque] = {}  # campaign_id+keyword -> ROI历史
    
    def check_alerts(self, campaign_id: int, keyword: str, ctr: float, roi: float,
                    shows: int, logger: BidLogger) -> List[str]:
        """检查所有报警条件，返回报警消息列表"""
        alerts = []
        key = f"{campaign_id}_{keyword}"
        
        # 初始化历史记录
        if key not in self.roi_history:
            self.roi_history[key] = deque(maxlen=3)
        
        self.roi_history[key].append(roi)
        
        # 报警1: ROI连续3周期下降
        if logger.check_roi_trend(campaign_id, keyword, periods=3):
            alerts.append(
                f"⚠️ 广告 {campaign_id} 关键词 '{keyword}' ROI连续3周期下降"
            )
        
        # 报警2: 无曝光超24小时
        if logger.check_no_shows(campaign_id, hours=24):
            alerts.append(
                f"⚠️ 广告 {campaign_id} 无曝光超过24小时"
            )
        
        # 报警3: API请求错误（在executor中处理）
        
        return alerts


if __name__ == "__main__":
    # 测试代码
    logger = BidLogger()
    logger.log_bid_change(
        campaign_id=12345,
        keyword="test",
        old_bid=100.0,
        new_bid=150.0,
        reason="测试",
        success=True,
        ctr=0.05,
        roi=2.0,
        shows=1000,
        clicks=50
    )
    print("日志记录完成")
    print(f"最近日志: {logger.get_recent_logs(limit=5)}")

