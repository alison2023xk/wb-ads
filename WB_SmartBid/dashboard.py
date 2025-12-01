# -*- coding: utf-8 -*-
"""
Streamlit 前端展示模块
提供总览、策略配置、日志查看、系统设置等功能
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from config import (
    WB_API_TOKEN,
    CAMPAIGNS_CACHE_PATH,
    STRATEGIES_CONFIG_PATH,
    LOG_PATH
)
from fetcher import WBFetcher
from strategy import StrategyManager
from logger import BidLogger

# 页面配置
st.set_page_config(
    page_title="WB广告自动出价系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化session state
if "fetcher" not in st.session_state:
    st.session_state.fetcher = None
if "strategy_manager" not in st.session_state:
    st.session_state.strategy_manager = StrategyManager()
if "logger" not in st.session_state:
    st.session_state.logger = BidLogger()


def get_token_from_env_or_secrets() -> str:
    """从环境变量或Streamlit Secrets获取Token"""
    try:
        token = st.secrets.get("WB_API_TOKEN", "")
    except (AttributeError, FileNotFoundError, KeyError):
        token = ""
    if not token:
        token = os.environ.get("WB_API_TOKEN", WB_API_TOKEN)
    return token


def load_campaigns_data() -> pd.DataFrame:
    """加载广告数据"""
    if CAMPAIGNS_CACHE_PATH.exists():
        try:
            df = pd.read_csv(CAMPAIGNS_CACHE_PATH, encoding="utf-8-sig")
            return df
        except Exception as e:
            st.error(f"加载广告数据失败: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def page_overview():
    """总览页"""
    st.header("📊 总览")
    
    # 加载数据
    df = load_campaigns_data()
    
    if df.empty:
        st.warning("暂无广告数据，请先执行数据采集")
        if st.button("🔄 立即采集数据"):
            token = get_token_from_env_or_secrets()
            if not token:
                st.error("未配置WB API Token，请在系统设置中配置")
                return
            
            with st.spinner("正在采集数据..."):
                try:
                    fetcher = WBFetcher()
                    df = fetcher.fetch_all_campaigns_data()
                    st.success(f"成功采集 {len(df)} 条广告数据")
                    st.rerun()
                except Exception as e:
                    st.error(f"采集失败: {e}")
        return
    
    # 计算关键指标
    total_spend = df["spend"].sum() if "spend" in df.columns else 0
    avg_roi = df["roi"].mean() if "roi" in df.columns else 0
    avg_ctr = df["ctr"].mean() if "ctr" in df.columns else 0
    total_clicks = df["clicks"].sum() if "clicks" in df.columns else 0
    total_shows = df["shows"].sum() if "shows" in df.columns else 0
    avg_cpc = total_spend / total_clicks if total_clicks > 0 else 0
    
    # 显示关键指标卡片
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("总花费", f"₽{total_spend:,.2f}")
    with col2:
        st.metric("平均ROI", f"{avg_roi:.2f}")
    with col3:
        st.metric("平均CTR", f"{avg_ctr:.2%}")
    with col4:
        st.metric("总点击", f"{total_clicks:,}")
    with col5:
        st.metric("平均CPC", f"₽{avg_cpc:.2f}")
    
    st.markdown("---")
    
    # 趋势图
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("ROI趋势")
        if "fetch_time" in df.columns:
            df["fetch_time"] = pd.to_datetime(df["fetch_time"], errors="coerce")
            roi_trend = df.groupby(df["fetch_time"].dt.date)["roi"].mean()
            fig_roi = px.line(
                x=roi_trend.index,
                y=roi_trend.values,
                labels={"x": "日期", "y": "ROI"},
                title="平均ROI趋势"
            )
            st.plotly_chart(fig_roi, use_container_width=True)
        else:
            st.info("暂无时间序列数据")
    
    with col2:
        st.subheader("CTR趋势")
        if "fetch_time" in df.columns:
            ctr_trend = df.groupby(df["fetch_time"].dt.date)["ctr"].mean()
            fig_ctr = px.line(
                x=ctr_trend.index,
                y=ctr_trend.values,
                labels={"x": "日期", "y": "CTR"},
                title="平均CTR趋势"
            )
            st.plotly_chart(fig_ctr, use_container_width=True)
        else:
            st.info("暂无时间序列数据")
    
    # 当日出价变更统计
    st.markdown("---")
    st.subheader("📈 当日出价变更统计")
    
    logger = st.session_state.logger
    today = datetime.now().date()
    recent_logs = logger.get_recent_logs(limit=1000)
    
    today_logs = [
        log for log in recent_logs
        if log.get("timestamp") and datetime.fromisoformat(log["timestamp"]).date() == today
    ]
    
    if today_logs:
        today_df = pd.DataFrame(today_logs)
        st.metric("今日出价调整次数", len(today_df))
        
        # 成功/失败统计
        success_count = sum(1 for log in today_logs if log.get("success") == "True")
        fail_count = len(today_logs) - success_count
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("成功", success_count, delta=None)
        with col2:
            st.metric("失败", fail_count, delta=None)
        
        # 显示今日调整记录
        st.dataframe(today_df[["timestamp", "campaign_id", "keyword", "old_bid", "new_bid", "reason", "success"]], 
                    use_container_width=True)
    else:
        st.info("今日暂无出价调整记录")
    
    # 广告列表
    st.markdown("---")
    st.subheader("📋 广告活动列表")
    st.dataframe(df[["campaignId", "name", "status_label", "ctr", "roi", "spend", "clicks", "shows"]], 
                use_container_width=True)


def page_strategy():
    """策略配置页"""
    st.header("⚙️ 策略配置")
    
    manager = st.session_state.strategy_manager
    
    # 显示现有策略
    st.subheader("现有策略")
    strategies = manager.get_all_strategies()
    
    if strategies:
        strategy_data = []
        for s in strategies:
            strategy_data.append({
                "关键词": s.keyword,
                "地区": s.region,
                "CTR下限": s.target_ctr_min,
                "CTR上限": s.target_ctr_max,
                "目标ROI": s.target_roi,
                "最小出价": s.min_bid,
                "最大出价": s.max_bid,
                "步长": s.step,
                "间隔(小时)": s.interval_hours,
                "启用": "✅" if s.enabled else "❌"
            })
        st.dataframe(pd.DataFrame(strategy_data), use_container_width=True)
    else:
        st.info("暂无策略配置")
    
    st.markdown("---")
    
    # 添加新策略
    st.subheader("添加新策略")
    
    with st.form("add_strategy_form"):
        col1, col2 = st.columns(2)
        with col1:
            keyword = st.text_input("关键词 *", placeholder="постельное белье")
            region = st.text_input("地区 *", placeholder="Москва")
            target_ctr_min = st.number_input("CTR下限 *", min_value=0.0, max_value=1.0, value=0.03, step=0.01)
            target_ctr_max = st.number_input("CTR上限 *", min_value=0.0, max_value=1.0, value=0.06, step=0.01)
            target_roi = st.number_input("目标ROI *", min_value=0.0, value=1.8, step=0.1)
        
        with col2:
            min_bid = st.number_input("最小出价 *", min_value=0, value=100, step=10)
            max_bid = st.number_input("最大出价 *", min_value=0, value=500, step=10)
            step = st.number_input("步长 *", min_value=1, value=10, step=1)
            interval_hours = st.number_input("调整间隔(小时) *", min_value=1, value=2, step=1)
            enabled = st.checkbox("启用", value=True)
        
        submitted = st.form_submit_button("➕ 添加策略")
        
        if submitted:
            if not keyword or not region:
                st.error("请填写关键词和地区")
            else:
                strategy_config = {
                    "keyword": keyword,
                    "region": region,
                    "target_ctr_min": target_ctr_min,
                    "target_ctr_max": target_ctr_max,
                    "target_roi": target_roi,
                    "min_bid": int(min_bid),
                    "max_bid": int(max_bid),
                    "step": int(step),
                    "interval_hours": interval_hours,
                    "strategy_type": "optimize",
                    "enabled": enabled
                }
                manager.add_strategy(strategy_config)
                st.success("策略添加成功！")
                st.rerun()
    
    # 编辑/删除策略
    if strategies:
        st.markdown("---")
        st.subheader("编辑/删除策略")
        
        strategy_options = [f"{s.keyword} - {s.region}" for s in strategies]
        selected_strategy = st.selectbox("选择要编辑的策略", strategy_options)
        
        if selected_strategy:
            selected_idx = strategy_options.index(selected_strategy)
            selected_strategy_obj = strategies[selected_idx]
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ 删除策略"):
                    manager.delete_strategy(selected_strategy_obj.keyword, selected_strategy_obj.region)
                    st.success("策略已删除")
                    st.rerun()
            
            with col2:
                new_enabled = st.checkbox("启用状态", value=selected_strategy_obj.enabled)
                if new_enabled != selected_strategy_obj.enabled:
                    manager.update_strategy(
                        selected_strategy_obj.keyword,
                        selected_strategy_obj.region,
                        {"enabled": new_enabled}
                    )
                    st.success("状态已更新")
                    st.rerun()


def page_logs():
    """日志页"""
    st.header("📝 出价调整日志")
    
    logger = st.session_state.logger
    
    # 筛选选项
    col1, col2, col3 = st.columns(3)
    with col1:
        limit = st.number_input("显示条数", min_value=10, max_value=1000, value=100, step=10)
    with col2:
        campaign_id_filter = st.text_input("筛选广告ID（留空显示全部）", "")
    with col3:
        if st.button("🔄 刷新日志"):
            st.rerun()
    
    # 获取日志
    logs = logger.get_recent_logs(limit=limit)
    
    if campaign_id_filter:
        logs = [log for log in logs if log.get("campaign_id") == campaign_id_filter]
    
    if logs:
        logs_df = pd.DataFrame(logs)
        
        # 格式化显示
        display_df = logs_df[[
            "timestamp", "campaign_id", "keyword", "old_bid", "new_bid",
            "reason", "success", "ctr", "roi", "shows", "clicks"
        ]].copy()
        
        # 转换success列
        display_df["success"] = display_df["success"].apply(lambda x: "✅" if x == "True" else "❌")
        
        st.dataframe(display_df, use_container_width=True)
        
        # 导出CSV
        st.markdown("---")
        csv = logs_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 导出CSV报告",
            data=csv,
            file_name=f"bid_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("暂无日志记录")


def page_settings():
    """系统设置页"""
    st.header("⚙️ 系统设置")
    
    # WB Token管理
    st.subheader("WB API Token 管理")
    
    current_token = get_token_from_env_or_secrets()
    if current_token:
        st.success("✅ Token已配置")
        st.code(current_token[:20] + "..." if len(current_token) > 20 else current_token)
        st.info("💡 Token存储在环境变量或Streamlit Secrets中")
    else:
        st.warning("⚠️ 未配置Token")
        st.info("请在环境变量中设置 WB_API_TOKEN 或在 Streamlit Secrets 中配置")
    
    # Timeweb调度时间配置
    st.markdown("---")
    st.subheader("定时任务配置")
    
    st.info("""
    **Timeweb定时任务配置示例：**
    
    ```bash
    # 每60分钟执行一次
    */60 * * * * /usr/bin/python3 /home/wb/WB_SmartBid/main.py --once >> /home/wb/logs/bid.log 2>&1
    ```
    
    **本地测试：**
    ```bash
    # 执行一次
    python main.py --once
    
    # 每1小时执行一次
    python main.py --interval 3600
    ```
    """)
    
    # 系统信息
    st.markdown("---")
    st.subheader("系统信息")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("**数据目录:**")
        st.code(str(CAMPAIGNS_CACHE_PATH.parent))
        st.write("**策略配置:**")
        st.code(str(STRATEGIES_CONFIG_PATH))
        st.write("**日志文件:**")
        st.code(str(LOG_PATH))
    
    with col2:
        st.write("**缓存文件状态:**")
        if CAMPAIGNS_CACHE_PATH.exists():
            size = CAMPAIGNS_CACHE_PATH.stat().st_size
            st.success(f"✅ campaigns.csv ({size:,} 字节)")
        else:
            st.warning("⚠️ campaigns.csv 不存在")
        
        if STRATEGIES_CONFIG_PATH.exists():
            st.success("✅ strategies.json 存在")
        else:
            st.warning("⚠️ strategies.json 不存在")
        
        if Path(LOG_PATH).exists():
            size = Path(LOG_PATH).stat().st_size
            st.success(f"✅ logs.csv ({size:,} 字节)")
        else:
            st.warning("⚠️ logs.csv 不存在")
    
    # 手动执行任务
    st.markdown("---")
    st.subheader("手动执行")
    
    if st.button("🚀 立即执行一次优化任务"):
        token = get_token_from_env_or_secrets()
        if not token:
            st.error("未配置WB API Token")
        else:
            with st.spinner("正在执行优化任务..."):
                try:
                    # 这里可以调用main.py的逻辑
                    st.info("💡 请在服务器上运行: python main.py --once")
                    st.success("提示：实际执行需要在服务器环境中运行main.py")
                except Exception as e:
                    st.error(f"执行失败: {e}")


def main():
    """主函数"""
    st.sidebar.title("📊 WB广告自动出价系统")
    
    # 导航菜单
    page = st.sidebar.radio(
        "选择页面",
        ["总览", "策略配置", "日志", "系统设置"]
    )
    
    # 显示对应页面
    if page == "总览":
        page_overview()
    elif page == "策略配置":
        page_strategy()
    elif page == "日志":
        page_logs()
    elif page == "系统设置":
        page_settings()


if __name__ == "__main__":
    main()

