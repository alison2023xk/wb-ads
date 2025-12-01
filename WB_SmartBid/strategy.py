# -*- coding: utf-8 -*-
"""
出价策略算法模块
根据实时广告表现，自动计算新的出价值
"""
import json
from typing import Dict, List, Optional
from pathlib import Path
from datetime import datetime, timedelta

from config import STRATEGIES_CONFIG_PATH


class BidStrategy:
    """出价策略类"""
    
    def __init__(self, strategy_config: Dict):
        self.keyword = strategy_config.get("keyword", "")
        self.region = strategy_config.get("region", "")
        self.target_ctr_min = strategy_config.get("target_ctr_min", 0.03)
        self.target_ctr_max = strategy_config.get("target_ctr_max", 0.06)
        self.target_roi = strategy_config.get("target_roi", 1.8)
        self.max_bid = strategy_config.get("max_bid", 500)
        self.min_bid = strategy_config.get("min_bid", 100)
        self.step = strategy_config.get("step", 10)
        self.interval_hours = strategy_config.get("interval_hours", 2)
        self.strategy_type = strategy_config.get("strategy_type", "optimize")
        self.enabled = strategy_config.get("enabled", True)
    
    def calculate_new_bid(self, current_bid: float, ctr: float, roi: float, 
                         shows: int = 0) -> float:
        """
        根据当前出价、CTR、ROI计算新出价
        
        Args:
            current_bid: 当前出价
            ctr: 点击率
            roi: 投资回报率
            shows: 曝光量
        
        Returns:
            新的出价值
        """
        if not self.enabled:
            return current_bid
        
        # 策略1: CTR过低且ROI良好 -> 提价
        if ctr < self.target_ctr_min and roi > self.target_roi:
            new_bid = min(current_bid + self.step, self.max_bid)
            return new_bid
        
        # 策略2: CTR过高或ROI下降 -> 降价
        elif ctr > self.target_ctr_max or roi < self.target_roi:
            new_bid = max(current_bid - self.step, self.min_bid)
            return new_bid
        
        # 策略3: 曝光过低 -> 提价
        elif shows < 100:  # 曝光量阈值可配置
            new_bid = min(current_bid + self.step, self.max_bid)
            return new_bid
        
        # 策略4: 其他情况保持当前出价
        else:
            return current_bid
    
    def should_pause_campaign(self, roi_history: List[float]) -> bool:
        """
        判断是否应该暂停广告
        ROI连续3周期低于目标 -> 暂停
        """
        if len(roi_history) < 3:
            return False
        
        recent_roi = roi_history[-3:]
        if all(roi < self.target_roi for roi in recent_roi):
            return True
        
        return False


class StrategyManager:
    """策略管理器"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or STRATEGIES_CONFIG_PATH
        self.strategies: List[BidStrategy] = []
        self.load_strategies()
    
    def load_strategies(self):
        """从配置文件加载策略"""
        try:
            if not self.config_path.exists():
                # 创建默认策略文件
                default_strategies = [
                    {
                        "keyword": "постельное белье",
                        "region": "Москва",
                        "target_ctr_min": 0.03,
                        "target_ctr_max": 0.06,
                        "target_roi": 1.8,
                        "max_bid": 500,
                        "min_bid": 100,
                        "step": 10,
                        "interval_hours": 2,
                        "strategy_type": "optimize",
                        "enabled": True
                    }
                ]
                self.save_strategies(default_strategies)
            
            with open(self.config_path, "r", encoding="utf-8") as f:
                strategies_data = json.load(f)
            
            self.strategies = [BidStrategy(s) for s in strategies_data if s.get("enabled", True)]
        except Exception as e:
            print(f"加载策略配置失败: {e}")
            self.strategies = []
    
    def save_strategies(self, strategies_data: List[Dict]):
        """保存策略到配置文件"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(strategies_data, f, ensure_ascii=False, indent=2)
            self.load_strategies()
        except Exception as e:
            print(f"保存策略配置失败: {e}")
    
    def get_strategy_for_keyword(self, keyword: str, region: str = None) -> Optional[BidStrategy]:
        """根据关键词和地区获取匹配的策略"""
        for strategy in self.strategies:
            if strategy.keyword == keyword:
                if region is None or strategy.region == region:
                    return strategy
        return None
    
    def get_all_strategies(self) -> List[BidStrategy]:
        """获取所有策略"""
        return self.strategies
    
    def add_strategy(self, strategy_config: Dict):
        """添加新策略"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                strategies_data = json.load(f)
            
            strategies_data.append(strategy_config)
            self.save_strategies(strategies_data)
        except Exception as e:
            print(f"添加策略失败: {e}")
    
    def update_strategy(self, keyword: str, region: str, updates: Dict):
        """更新策略"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                strategies_data = json.load(f)
            
            for i, s in enumerate(strategies_data):
                if s.get("keyword") == keyword and s.get("region") == region:
                    strategies_data[i].update(updates)
                    break
            
            self.save_strategies(strategies_data)
        except Exception as e:
            print(f"更新策略失败: {e}")
    
    def delete_strategy(self, keyword: str, region: str):
        """删除策略"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                strategies_data = json.load(f)
            
            strategies_data = [
                s for s in strategies_data 
                if not (s.get("keyword") == keyword and s.get("region") == region)
            ]
            
            self.save_strategies(strategies_data)
        except Exception as e:
            print(f"删除策略失败: {e}")


if __name__ == "__main__":
    # 测试代码
    manager = StrategyManager()
    print(f"加载了 {len(manager.strategies)} 个策略")
    
    # 测试计算新出价
    if manager.strategies:
        strategy = manager.strategies[0]
        current_bid = 200
        ctr = 0.02  # 低于目标下限
        roi = 2.0  # 高于目标
        new_bid = strategy.calculate_new_bid(current_bid, ctr, roi)
        print(f"当前出价: {current_bid}, CTR: {ctr}, ROI: {roi}")
        print(f"新出价: {new_bid}")

