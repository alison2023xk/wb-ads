# -*- coding: utf-8 -*-
"""
主任务调度入口
定期执行：拉取数据 -> 计算新出价 -> 执行出价调整 -> 记录日志
"""
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import TIMEZONE
from fetcher import WBFetcher
from strategy import StrategyManager
from executor import BidExecutor
from logger import BidLogger, AlertManager
import pandas as pd


class BidOptimizer:
    """出价优化器主类"""
    
    def __init__(self):
        self.fetcher = WBFetcher()
        self.strategy_manager = StrategyManager()
        self.executor = BidExecutor()
        self.logger = BidLogger()
        self.alert_manager = AlertManager()
    
    def run_once(self):
        """执行一次完整的优化流程"""
        print(f"[{datetime.now().isoformat()}] 开始执行出价优化任务...")
        
        try:
            # 1. 拉取最新广告数据
            print("步骤1: 拉取广告数据...")
            campaigns_df = self.fetcher.fetch_all_campaigns_data()
            print(f"获取到 {len(campaigns_df)} 条广告数据")
            
            if len(campaigns_df) == 0:
                print("未获取到广告数据，跳过本次执行")
                return
            
            # 2. 遍历每个广告，应用策略
            print("步骤2: 应用出价策略...")
            updated_count = 0
            paused_count = 0
            
            for _, row in campaigns_df.iterrows():
                campaign_id = int(row.get("campaignId", 0))
                keyword = str(row.get("keyword", ""))
                sku = str(row.get("sku", ""))
                
                if not keyword:
                    continue
                
                # 获取匹配的策略
                strategy = self.strategy_manager.get_strategy_for_keyword(keyword)
                if not strategy:
                    continue
                
                # 获取当前出价（如果API支持）
                # 注意：WB API可能没有直接获取出价的接口
                # 这里可以从日志中获取最后一次出价，或使用策略的默认值
                current_bid = self.executor.get_current_bid(campaign_id, keyword)
                if current_bid is None:
                    # 尝试从日志中获取最后一次出价
                    campaign_logs = self.logger.get_campaign_logs(campaign_id, limit=1)
                    if campaign_logs:
                        last_log = campaign_logs[-1]
                        last_bid = last_log.get("new_bid")
                        if last_bid:
                            try:
                                current_bid = float(last_bid)
                            except (ValueError, TypeError):
                                current_bid = strategy.min_bid
                        else:
                            current_bid = strategy.min_bid
                    else:
                        # 如果无法获取当前出价，使用策略的最小出价作为起始值
                        current_bid = strategy.min_bid
                
                # 获取广告指标
                ctr = float(row.get("ctr", 0.0))
                roi = float(row.get("roi", 0.0))
                shows = int(row.get("shows", 0))
                clicks = int(row.get("clicks", 0))
                
                # 检查报警条件
                alerts = self.alert_manager.check_alerts(
                    campaign_id, keyword, ctr, roi, shows, self.logger
                )
                for alert in alerts:
                    print(f"  {alert}")
                
                # 检查是否需要暂停
                roi_history = self.logger.get_campaign_logs(campaign_id, limit=10)
                roi_values = [
                    float(log.get("roi", 0)) 
                    for log in roi_history 
                    if log.get("roi") and log.get("keyword") == keyword
                ]
                
                if strategy.should_pause_campaign(roi_values):
                    print(f"  暂停广告 {campaign_id} (关键词: {keyword}) - ROI连续3周期低于目标")
                    success, msg = self.executor.pause_campaign(campaign_id)
                    if success:
                        paused_count += 1
                    continue
                
                # 计算新出价
                new_bid = strategy.calculate_new_bid(current_bid, ctr, roi, shows)
                
                # 如果出价有变化，执行更新
                if abs(new_bid - current_bid) >= 1:  # 至少变化1个单位
                    print(f"  调整出价: 广告 {campaign_id} 关键词 '{keyword}' "
                          f"从 {current_bid} 调整为 {new_bid} (CTR: {ctr:.4f}, ROI: {roi:.2f})")
                    
                    success, msg = self.executor.update_bid(
                        campaign_id=campaign_id,
                        keyword=keyword,
                        new_bid=new_bid,
                        sku=sku if sku else None
                    )
                    
                    if success:
                        updated_count += 1
                        # 记录详细日志
                        self.logger.log_bid_change(
                            campaign_id=campaign_id,
                            keyword=keyword,
                            old_bid=current_bid,
                            new_bid=new_bid,
                            reason="策略自动调整",
                            success=True,
                            ctr=ctr,
                            roi=roi,
                            shows=shows,
                            clicks=clicks
                        )
                    else:
                        print(f"    更新失败: {msg}")
                else:
                    print(f"  广告 {campaign_id} 关键词 '{keyword}' 出价无需调整 "
                          f"(当前: {current_bid}, CTR: {ctr:.4f}, ROI: {roi:.2f})")
            
            print(f"步骤3: 任务完成 - 更新 {updated_count} 个出价, 暂停 {paused_count} 个广告")
            
        except Exception as e:
            print(f"执行过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            # 记录错误日志
            self.logger.log_bid_change(
                campaign_id=0,
                keyword="",
                old_bid=None,
                new_bid=None,
                reason="系统错误",
                success=False,
                error=str(e)
            )


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="WB广告自动出价优化系统")
    parser.add_argument("--once", action="store_true", help="仅执行一次（不循环）")
    parser.add_argument("--interval", type=int, default=3600, 
                       help="循环执行间隔（秒），默认3600秒（1小时）")
    args = parser.parse_args()
    
    optimizer = BidOptimizer()
    
    if args.once:
        # 仅执行一次
        optimizer.run_once()
    else:
        # 循环执行
        print(f"启动定时任务，每 {args.interval} 秒执行一次")
        print("按 Ctrl+C 停止")
        try:
            while True:
                optimizer.run_once()
                print(f"等待 {args.interval} 秒后执行下一次...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n收到中断信号，退出程序")


if __name__ == "__main__":
    main()

