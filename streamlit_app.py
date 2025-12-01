# streamlit_app.py
# -*- coding: utf-8 -*-
"""
WB广告管理系统 - 统一界面
整合定时开关和智能出价两大功能
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime, time as dtime, timedelta, date
from typing import List, Dict, Tuple, Optional

import requests
import streamlit as st
import yaml
import pandas as pd
import plotly.express as px

# 添加WB_SmartBid到路径
WB_SMARTBID_DIR = Path(__file__).parent / "WB_SmartBid"
if str(WB_SMARTBID_DIR) not in sys.path:
    sys.path.insert(0, str(WB_SMARTBID_DIR))

# 尝试导入智能出价模块
try:
    # 直接导入，因为已经添加到sys.path
    from config import (
        CAMPAIGNS_CACHE_PATH,
        STRATEGIES_CONFIG_PATH,
        LOG_PATH
    )
    from fetcher import WBFetcher
    from strategy import StrategyManager
    from logger import BidLogger
    SMARTBID_AVAILABLE = True
except ImportError as e:
    SMARTBID_AVAILABLE = False
    # 只在初始化时显示警告，避免重复显示
    if "smartbid_warning_shown" not in st.session_state:
        st.session_state.smartbid_warning_shown = True
        st.warning(f"⚠️ 智能出价模块导入失败: {e}")

WB_API_BASE = "https://advert-api.wildberries.ru"

STATUS_LABELS = {
    -1: "deleted",
    4: "ready",
    7: "completed",
    8: "declined",
    9: "active",
    11: "paused",
}

# ==================== 通用函数 ====================

def get_token_from_env_or_secrets() -> str:
    """从环境变量或Streamlit Secrets获取Token"""
    # 优先 Streamlit Secrets，其次环境变量
    try:
        token = st.secrets.get("WB_PROMO_TOKEN", "")
    except (AttributeError, FileNotFoundError, KeyError):
        token = ""
    if not token:
        token = os.environ.get("WB_PROMO_TOKEN", "")
    if not token:
        # 尝试智能出价的Token
        try:
            token = st.secrets.get("WB_API_TOKEN", "")
        except:
            pass
        if not token:
            token = os.environ.get("WB_API_TOKEN", "")
    return token

# ==================== 定时开关功能 ====================

def wb_get_auction_adverts(token: str, statuses: str = "4,7,8,9,11", raw_data=None) -> List[Dict]:
    """读取广告活动信息"""
    if raw_data is None:
        url = f"{WB_API_BASE}/adv/v0/auction/adverts"
        headers = {"Authorization": token}
        params = {"statuses": statuses}
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code != 200:
            raise RuntimeError(f"auction/adverts {r.status_code}: {r.text}")
        data = r.json()
    else:
        data = raw_data
    
    adverts = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("adverts", data.get("data", []))
        if not items and "id" in data:
            items = [data]
    else:
        items = []
    
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

def wb_start(token: str, advert_id: int) -> str:
    r = requests.get(f"{WB_API_BASE}/adv/v0/start", headers={"Authorization": token}, params={"id": advert_id}, timeout=20)
    return f"{r.status_code} {r.text}"

def wb_pause(token: str, advert_id: int) -> str:
    r = requests.get(f"{WB_API_BASE}/adv/v0/pause", headers={"Authorization": token}, params={"id": advert_id}, timeout=20)
    return f"{r.status_code} {r.text}"

def wb_stop(token: str, advert_id: int) -> str:
    r = requests.get(f"{WB_API_BASE}/adv/v0/stop", headers={"Authorization": token}, params={"id": advert_id}, timeout=20)
    return f"{r.status_code} {r.text}"

def build_yaml_config(selected_ids: List[int], id_to_name: Dict[int, str], rules: List[dict], timezone: str) -> str:
    """构建YAML配置"""
    adverts_info = {}
    for adv_id in selected_ids:
        name = id_to_name.get(adv_id, "未命名")
        adverts_info[adv_id] = name
    
    yaml_rules = []
    for idx, rule in enumerate(rules):
        yaml_rule = {
            "name": rule.get("name", f"规则 {idx + 1}"),
            "targets": {
                "type": "ids", 
                "ids": selected_ids,
                "adverts": adverts_info
            },
            "weekdays": rule.get("weekdays", []),
            "periods": rule.get("periods", []),
            "exclude_dates": rule.get("exclude_dates", []),
            "priority": 100,
            "enabled": rule.get("enabled", True),
        }
        yaml_rules.append(yaml_rule)
    
    cfg = {
        "timezone": timezone,
        "msk_timezone": "Europe/Moscow",
        "rate_limit": {"per_second": 4, "burst": 4},
        "wb": {
            "api_base": WB_API_BASE,
            "token_env": "WB_PROMO_TOKEN",
        },
        "rules": yaml_rules,
    }
    yaml_str = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    lines = yaml_str.split('\n')
    
    if adverts_info:
        for i, line in enumerate(lines):
            if 'ids:' in line:
                indent = len(line) - len(line.lstrip())
                comment_lines = []
                for adv_id in selected_ids:
                    name = adverts_info.get(adv_id, "未命名")
                    comment_lines.append(' ' * indent + f"# {name} (ID: {adv_id})")
                lines.insert(i + 1, '\n'.join(comment_lines))
                break
    
    for i, line in enumerate(lines):
        if 'periods:' in line:
            indent = len(line) - len(line.lstrip())
            comment = ' ' * indent + "# 说明：每个时间段会生成两个period，开始时间执行start动作，结束时间执行stop动作"
            lines.insert(i + 1, comment)
            break
    
    yaml_str = '\n'.join(lines)
    return yaml_str

def in_period(now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
    if start_t <= end_t:
        return start_t <= now_t < end_t
    return (now_t >= start_t) or (now_t < end_t)

def decide_now_action(now: dtime, rules: List[dict]) -> Tuple[str | None, str]:
    """根据当前时间和规则列表决定执行的动作"""
    import datetime as _dt
    wd = (datetime.now().weekday() + 1)
    
    candidates = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        rule_weekdays = rule.get("weekdays", [])
        if wd not in rule_weekdays:
            continue
        
        periods = rule.get("periods", [])
        for p in periods:
            st = _dt.time.fromisoformat(p["start"])
            et = _dt.time.fromisoformat(p["end"])
            if in_period(now, st, et):
                candidates.append({
                    "action": p["action"],
                    "rule_name": rule.get("name", "未知规则"),
                    "priority": rule.get("priority", 100)
                })
    
    if not candidates:
        return None, ""
    
    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return candidates[0]["action"], candidates[0]["rule_name"]

def page_scheduler():
    """定时开关功能页面"""
    st.header("⏰ 广告定时开关")
    
    with st.expander("📖 使用说明", expanded=False):
        st.markdown("""
        ### 功能说明：
        1. **配置规则**：可视化设置广告的定时开关规则
        2. **生成配置文件**：导出 YAML 配置文件供定时任务使用
        3. **测试执行**：可以立即执行一次来测试规则是否正确
        
        ### ⚠️ 重要说明：
        - **"Run once"按钮**：只执行**一次**，不会自动重复执行
        - **要实现定时自动执行**：需要使用 `wb_ad_auto_scheduler.py` 脚本（后台定时任务）
        """)
    
    # Token 输入
    token_default = get_token_from_env_or_secrets()
    token = st.text_input("Promotion API Token（若已在 Secrets 可留空）", value=token_default, type="password")
    if not token:
        st.warning("未提供 Token。加载活动与执行操作将不可用。")
    
    # 加载广告活动
    left, right = st.columns([1, 2])
    with left:
        show_debug = st.checkbox("显示调试信息", value=False, help="查看API原始返回数据")
        if st.button("🔄 加载广告活动（类型9，自定义/统一）", use_container_width=True, disabled=not token):
            try:
                url = f"{WB_API_BASE}/adv/v0/auction/adverts"
                headers = {"Authorization": token}
                params = {"statuses": "4,7,8,9,11"}
                r = requests.get(url, headers=headers, params=params, timeout=20)
                if r.status_code != 200:
                    raise RuntimeError(f"auction/adverts {r.status_code}: {r.text}")
                raw_data = r.json()
                
                if show_debug:
                    with st.expander("🔍 API原始数据（调试）", expanded=True):
                        st.json(raw_data)
                
                adverts = wb_get_auction_adverts(token, raw_data=raw_data)
                st.session_state["scheduler_adverts"] = adverts
                st.session_state["scheduler_raw_data"] = raw_data
                st.success(f"加载到 {len(adverts)} 条活动")
            except Exception as e:
                st.error(f"加载失败：{e}")
                if show_debug:
                    import traceback
                    st.code(traceback.format_exc())
    
    # 展示广告列表并选择
    adverts = st.session_state.get("scheduler_adverts", [])
    if adverts:
        df = []
        for a in adverts:
            df.append({
                "ID": a["id"],
                "名称": a.get("name"),
                "状态": STATUS_LABELS.get(a.get("status"), a.get("status")),
                "付费": a.get("payment_type"),
            })
        st.dataframe(pd.DataFrame(df))
        
        options = {f'{row["名称"] or "未命名"} (#{row["ID"]})': row["ID"] for row in df}
        id_to_name = {row["ID"]: row["名称"] or "未命名" for row in df}
        selected_labels = st.multiselect("选择要控制的广告活动", list(options.keys()))
        selected_ids = [options[k] for k in selected_labels]
        st.session_state["scheduler_id_to_name"] = id_to_name
        st.session_state["scheduler_selected_ids"] = selected_ids
        
        if selected_ids:
            st.info(f"已选择 {len(selected_ids)} 个广告活动")
    else:
        selected_ids = []
        st.session_state["scheduler_id_to_name"] = {}
        st.session_state["scheduler_selected_ids"] = []
    
    st.markdown("---")
    
    # 规则编辑
    st.subheader("规则设置")
    timezone = st.selectbox("时区（用于时间计算）", ["Europe/Moscow","Europe/Berlin","Asia/Shanghai","UTC"], index=0)
    st.session_state["scheduler_timezone"] = timezone
    
    if "scheduler_rules" not in st.session_state:
        st.session_state["scheduler_rules"] = []
    
    weekdays_map = {"周一":1,"周二":2,"周三":3,"周四":4,"周五":5,"周六":6,"周日":7}
    
    col_add, col_clear = st.columns([1, 1])
    with col_add:
        if st.button("➕ 添加新规则", use_container_width=True):
            st.session_state["scheduler_rules"].append({
                "name": f"规则 {len(st.session_state['scheduler_rules']) + 1}",
                "weekdays": [],
                "time_ranges": [],
                "periods": [],
                "enabled": True
            })
    with col_clear:
        if st.button("🗑️ 清空所有规则", use_container_width=True):
            st.session_state["scheduler_rules"] = []
    
    rules = st.session_state.get("scheduler_rules", [])
    if not rules:
        st.info("👆 点击「添加新规则」开始配置")
    
    rules = [dict(rule) for rule in rules] if rules else []
    
    for rule_idx, rule in enumerate(rules):
        with st.expander(f"📌 {rule.get('name', f'规则 {rule_idx + 1}')} {'✅' if rule.get('enabled', True) else '❌'}", expanded=True):
            col_name, col_enabled = st.columns([3, 1])
            with col_name:
                rule["name"] = st.text_input("规则名称", value=rule.get("name", f"规则 {rule_idx + 1}"), key=f"scheduler_rule_name_{rule_idx}")
            with col_enabled:
                rule["enabled"] = st.checkbox("启用", value=rule.get("enabled", True), key=f"scheduler_rule_enabled_{rule_idx}")
            
            st.markdown("**选择星期几**")
            weekdays_labels = st.multiselect(
                "星期（可多选）", 
                list(weekdays_map.keys()), 
                default=[k for k, v in weekdays_map.items() if v in rule.get("weekdays", [])],
                key=f"scheduler_rule_weekdays_{rule_idx}"
            )
            rule["weekdays"] = [weekdays_map[k] for k in weekdays_labels]
            
            st.markdown("**时间段设置**")
            time_ranges = rule.get("time_ranges", [])
            if time_ranges:
                current_periods_count = len(time_ranges)
            else:
                periods_count = len(rule.get("periods", []))
                current_periods_count = max(1, periods_count // 2) if periods_count > 0 else 1
            
            n_periods = st.number_input(
                "时间段数量", 
                min_value=1, 
                max_value=10, 
                value=current_periods_count,
                step=1,
                key=f"scheduler_n_periods_{rule_idx}"
            )
            
            time_ranges = []
            for i in range(n_periods):
                st.markdown(f"**时间段 {i+1}**")
                existing_ranges = rule.get("time_ranges", [])
                if i < len(existing_ranges):
                    existing_range = existing_ranges[i]
                    start_str = existing_range.get("start", "09:00")
                    end_str = existing_range.get("end", "18:00")
                else:
                    existing_periods = rule.get("periods", [])
                    if existing_periods and len(existing_periods) >= 2 * i + 1:
                        start_period = existing_periods[2 * i]
                        end_period = existing_periods[2 * i + 1] if 2 * i + 1 < len(existing_periods) else existing_periods[2 * i]
                        start_str = start_period.get("start", "09:00")
                        end_str = end_period.get("start", "18:00")
                    else:
                        start_str = "09:00"
                        end_str = "18:00"
                
                start_h, start_m = map(int, start_str.split(":"))
                end_h, end_m = map(int, end_str.split(":"))
                
                c1, c2 = st.columns([1, 1])
                with c1:
                    start_time = st.time_input(f"开始时间（执行开始动作）", value=dtime(start_h, start_m), key=f"scheduler_start_{rule_idx}_{i}")
                with c2:
                    end_time = st.time_input(f"结束时间（执行结束动作）", value=dtime(end_h, end_m), key=f"scheduler_end_{rule_idx}_{i}")
                
                time_ranges.append({
                    "start": start_time.strftime("%H:%M"), 
                    "end": end_time.strftime("%H:%M")
                })
            
            rule["time_ranges"] = time_ranges
            
            periods = []
            for tr in time_ranges:
                start_str = tr["start"]
                end_str = tr["end"]
                
                start_time_obj = datetime.strptime(start_str, "%H:%M").time()
                start_dt = datetime.combine(date.today(), start_time_obj)
                start_plus_1min = (start_dt + timedelta(minutes=1)).time()
                start_end_str = start_plus_1min.strftime("%H:%M")
                
                periods.append({
                    "start": start_str, 
                    "end": start_end_str,
                    "action": "start"
                })
                
                end_time_obj = datetime.strptime(end_str, "%H:%M").time()
                end_dt = datetime.combine(date.today(), end_time_obj)
                end_plus_1min = (end_dt + timedelta(minutes=1)).time()
                end_end_str = end_plus_1min.strftime("%H:%M")
                
                periods.append({
                    "start": end_str, 
                    "end": end_end_str,
                    "action": "stop"
                })
            
            rule["periods"] = periods
            
            if rule_idx < len(st.session_state.get("scheduler_rules", [])):
                st.session_state["scheduler_rules"][rule_idx] = dict(rule)
            else:
                st.session_state["scheduler_rules"] = st.session_state.get("scheduler_rules", [])
                st.session_state["scheduler_rules"].append(dict(rule))
            
            if st.button("🗑️ 删除此规则", key=f"scheduler_delete_rule_{rule_idx}", use_container_width=True):
                st.session_state["scheduler_rules"].pop(rule_idx)
                st.rerun()
    
    st.session_state["scheduler_rules"] = rules
    
    st.markdown("---")
    
    # 生成 YAML
    selected_ids = st.session_state.get("scheduler_selected_ids", [])
    rules = st.session_state.get("scheduler_rules", [])
    id_to_name = st.session_state.get("scheduler_id_to_name", {})
    timezone = st.session_state.get("scheduler_timezone", "Europe/Moscow")
    disabled_generate = (len(selected_ids) == 0) or (len(rules) == 0)
    
    if not disabled_generate:
        yaml_str = build_yaml_config(selected_ids, id_to_name, rules, timezone)
        st.session_state["scheduler_yaml_data"] = yaml_str
    else:
        yaml_str = "# 请先选择广告活动并添加规则，配置将在此显示"
    
    st.markdown("#### 📄 生成的配置文件")
    st.code(yaml_str, language="yaml")
    
    st.markdown("#### 📥 下载配置文件")
    if not disabled_generate:
        st.download_button(
            label="📥 下载YAML配置",
            data=yaml_str,
            file_name=f"wb_scheduler_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml",
            mime="text/yaml"
        )
    
    # 保存到服务器
    st.markdown("---")
    st.markdown("#### 💾 保存配置到服务器")
    if st.button("💾 保存到服务器"):
        yaml_data = st.session_state.get("scheduler_yaml_data", "")
        if not yaml_data or yaml_data.strip().startswith("# 请先"):
            st.error("请先生成有效配置")
        else:
            API_BASE = os.environ.get("API_BASE", "http://194.87.161.126/api")
            HEADERS = {}
            if os.environ.get("API_GATEWAY_TOKEN"):
                HEADERS["Authorization"] = f"Bearer {os.environ['API_GATEWAY_TOKEN']}"
            
            try:
                r = requests.post(f"{API_BASE}/config/save", headers=HEADERS, data=yaml_data.encode("utf-8"), timeout=10)
                if r.status_code == 200:
                    st.success("✅ 配置已保存到服务器！")
                else:
                    st.error(f"⚠️ 保存失败: HTTP {r.status_code}")
            except Exception as e:
                st.error(f"⚠️ 保存时发生错误: {e}")
    
    # 立即执行一次
    st.markdown("---")
    st.markdown("### ⏱ 立即执行一次（测试用）")
    if st.button("🚀 立即执行一次", disabled=(not token or disabled_generate)):
        now = datetime.now().time()
        act, rule_name = decide_now_action(now, rules)
        if not act:
            st.info("当前时刻未命中任何时间段，不执行。")
        else:
            st.info(f"匹配规则：{rule_name}，执行动作：{act}")
            results = []
            id_to_name = st.session_state.get("scheduler_id_to_name", {})
            for adv_id in selected_ids:
                adv_name = id_to_name.get(adv_id, "未命名")
                if act == "start":
                    res = wb_start(token, adv_id)
                elif act == "pause":
                    res = wb_pause(token, adv_id)
                else:
                    res = wb_stop(token, adv_id)
                results.append({
                    "id": adv_id,
                    "name": adv_name,
                    "action": act,
                    "result": res
                })
            st.success("执行完成")
            results_df = pd.DataFrame(results)
            if not results_df.empty:
                results_df = results_df[["name", "id", "action", "result"]]
                results_df.columns = ["广告名称", "广告ID", "执行动作", "执行结果"]
            st.dataframe(results_df, use_container_width=True)

# ==================== 智能出价功能 ====================

def load_campaigns_data() -> pd.DataFrame:
    """加载广告数据"""
    if SMARTBID_AVAILABLE and CAMPAIGNS_CACHE_PATH.exists():
        try:
            df = pd.read_csv(CAMPAIGNS_CACHE_PATH, encoding="utf-8-sig")
            return df
        except Exception as e:
            st.error(f"加载广告数据失败: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def page_smartbid_overview():
    """智能出价 - 总览页"""
    st.header("📊 智能出价 - 总览")
    
    if not SMARTBID_AVAILABLE:
        st.error("智能出价模块不可用，请检查WB_SmartBid目录")
        return
    
    df = load_campaigns_data()
    
    if df.empty:
        st.warning("暂无广告数据，请先执行数据采集")
        if st.button("🔄 立即采集数据"):
            token = get_token_from_env_or_secrets()
            if not token:
                st.error("未配置WB API Token")
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
            fig_roi = px.line(x=roi_trend.index, y=roi_trend.values, labels={"x": "日期", "y": "ROI"}, title="平均ROI趋势")
            st.plotly_chart(fig_roi, use_container_width=True)
        else:
            st.info("暂无时间序列数据")
    
    with col2:
        st.subheader("CTR趋势")
        if "fetch_time" in df.columns:
            ctr_trend = df.groupby(df["fetch_time"].dt.date)["ctr"].mean()
            fig_ctr = px.line(x=ctr_trend.index, y=ctr_trend.values, labels={"x": "日期", "y": "CTR"}, title="平均CTR趋势")
            st.plotly_chart(fig_ctr, use_container_width=True)
        else:
            st.info("暂无时间序列数据")
    
    # 当日出价变更统计
    st.markdown("---")
    st.subheader("📈 当日出价变更统计")
    
    if "smartbid_logger" not in st.session_state:
        st.session_state.smartbid_logger = BidLogger()
    
    logger = st.session_state.smartbid_logger
    today = datetime.now().date()
    recent_logs = logger.get_recent_logs(limit=1000)
    
    today_logs = [log for log in recent_logs if log.get("timestamp") and datetime.fromisoformat(log["timestamp"]).date() == today]
    
    if today_logs:
        today_df = pd.DataFrame(today_logs)
        st.metric("今日出价调整次数", len(today_df))
        success_count = sum(1 for log in today_logs if log.get("success") == "True")
        fail_count = len(today_logs) - success_count
        col1, col2 = st.columns(2)
        with col1:
            st.metric("成功", success_count)
        with col2:
            st.metric("失败", fail_count)
        st.dataframe(today_df[["timestamp", "campaign_id", "keyword", "old_bid", "new_bid", "reason", "success"]], use_container_width=True)
    else:
        st.info("今日暂无出价调整记录")
    
    st.markdown("---")
    st.subheader("📋 广告活动列表")
    st.dataframe(df[["campaignId", "name", "status_label", "ctr", "roi", "spend", "clicks", "shows"]], use_container_width=True)

def page_smartbid_strategy():
    """智能出价 - 策略配置页"""
    st.header("⚙️ 智能出价 - 策略配置")
    
    if not SMARTBID_AVAILABLE:
        st.error("智能出价模块不可用")
        return
    
    if "smartbid_strategy_manager" not in st.session_state:
        st.session_state.smartbid_strategy_manager = StrategyManager()
    
    manager = st.session_state.smartbid_strategy_manager
    
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
                    manager.update_strategy(selected_strategy_obj.keyword, selected_strategy_obj.region, {"enabled": new_enabled})
                    st.success("状态已更新")
                    st.rerun()

def page_smartbid_logs():
    """智能出价 - 日志页"""
    st.header("📝 智能出价 - 出价调整日志")
    
    if not SMARTBID_AVAILABLE:
        st.error("智能出价模块不可用")
        return
    
    if "smartbid_logger" not in st.session_state:
        st.session_state.smartbid_logger = BidLogger()
    
    logger = st.session_state.smartbid_logger
    
    col1, col2, col3 = st.columns(3)
    with col1:
        limit = st.number_input("显示条数", min_value=10, max_value=1000, value=100, step=10)
    with col2:
        campaign_id_filter = st.text_input("筛选广告ID（留空显示全部）", "")
    with col3:
        if st.button("🔄 刷新日志"):
            st.rerun()
    
    logs = logger.get_recent_logs(limit=limit)
    
    if campaign_id_filter:
        logs = [log for log in logs if log.get("campaign_id") == campaign_id_filter]
    
    if logs:
        logs_df = pd.DataFrame(logs)
        display_df = logs_df[["timestamp", "campaign_id", "keyword", "old_bid", "new_bid", "reason", "success", "ctr", "roi", "shows", "clicks"]].copy()
        display_df["success"] = display_df["success"].apply(lambda x: "✅" if x == "True" else "❌")
        st.dataframe(display_df, use_container_width=True)
        
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

# ==================== 主函数 ====================

def main():
    """主函数"""
    st.set_page_config(
        page_title="WB广告管理系统",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.sidebar.title("📊 WB广告管理系统")
    st.sidebar.markdown("---")
    
    # 主导航菜单
    main_page = st.sidebar.radio(
        "主要功能",
        ["⏰ 定时开关", "🤖 智能出价"],
        label_visibility="visible"
    )
    
    st.sidebar.markdown("---")
    
    # 根据主页面显示子菜单
    if main_page == "⏰ 定时开关":
        page_scheduler()
    elif main_page == "🤖 智能出价":
        if not SMARTBID_AVAILABLE:
            st.error("⚠️ 智能出价模块不可用，请检查WB_SmartBid目录是否存在且配置正确")
            return
        
        sub_page = st.sidebar.radio(
            "智能出价功能",
            ["📊 总览", "⚙️ 策略配置", "📝 日志"],
            label_visibility="visible"
        )
        
        if sub_page == "📊 总览":
            page_smartbid_overview()
        elif sub_page == "⚙️ 策略配置":
            page_smartbid_strategy()
        elif sub_page == "📝 日志":
            page_smartbid_logs()

if __name__ == "__main__":
    main()
