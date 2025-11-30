# streamlit_app.py
# -*- coding: utf-8 -*-
"""
可视化：WB 广告定时规则编辑器（Streamlit）
- 读取卖家广告活动列表（名称 + ID）
- 选择广告、设置星期与时间段、动作
- 一键导出 YAML 配置，兼容 wb_ad_auto_scheduler.py
- 可选：立即执行“当前时刻”的开/停/停用（Run once）

部署：
1) 将此仓库推到 GitHub
2) 在 Streamlit Cloud 选择此仓库部署
3) 在 App Secrets 中添加：
   WB_PROMO_TOKEN = "你的 Promotion 类 API Token"
"""
import os
import time
from datetime import datetime, time as dtime
from typing import List, Dict

import requests
import streamlit as st
import yaml

WB_API_BASE = "https://advert-api.wildberries.ru"

STATUS_LABELS = {
    -1: "deleted",
    4: "ready",
    7: "completed",
    8: "declined",
    9: "active",
    11: "paused",
}

def get_token_from_env_or_secrets() -> str:
    # 优先 Streamlit Secrets，其次环境变量
    token = st.secrets.get("WB_PROMO_TOKEN", "")
    if not token:
        token = os.environ.get("WB_PROMO_TOKEN", "")
    return token

def wb_get_auction_adverts(token: str, statuses: str = "4,7,8,9,11", raw_data=None) -> List[Dict]:
    """
    读取"自定义/统一（类型9）"活动信息，包括名称。
    GET /adv/v0/auction/adverts
    
    WB API可能返回扁平化数组格式，每个元素只包含一个字段（id, settings, status等）
    需要将这些字段合并到同一个广告对象中。
    """
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
    
    # 处理不同的API返回格式
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("adverts", data.get("data", []))
        if not items and "id" in data:
            # 单个对象
            items = [data]
    else:
        items = []
    
    # WB API可能返回扁平化数组，需要按ID分组
    adverts_dict = {}
    
    for item in items:
        # 如果item包含id字段，这是一个新广告的开始
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
        
        # 处理settings字段（包含name等信息）
        if "settings" in item:
            settings = item["settings"]
            if isinstance(settings, dict):
                # 找到对应的广告ID
                if "id" in item:
                    adv_id = item["id"]
                else:
                    # 如果没有id，尝试从settings中找
                    adv_id = settings.get("id") or settings.get("advertId")
                
                if adv_id and adv_id in adverts_dict:
                    adverts_dict[adv_id]["name"] = settings.get("name") or settings.get("advertName")
                    adverts_dict[adv_id]["payment_type"] = settings.get("payment_type")
                    adverts_dict[adv_id]["placements"] = settings.get("placements")
        
        # 处理status字段
        if "status" in item:
            if "id" in item:
                adv_id = item["id"]
                if adv_id in adverts_dict:
                    adverts_dict[adv_id]["status"] = item["status"]
        
        # 处理nm_settings
        if "nm_settings" in item:
            if "id" in item:
                adv_id = item["id"]
                if adv_id in adverts_dict:
                    adverts_dict[adv_id]["nm_settings"] = item.get("nm_settings", [])
    
    # 如果上面的逻辑没有工作，尝试直接解析完整对象
    if not adverts_dict and items:
        for item in items:
            # 尝试作为完整对象解析
            if isinstance(item, dict):
                advert = {
                    "id": item.get("id") or item.get("advertId"),
                    "name": item.get("name") or item.get("advertName") or item.get("title"),
                    "payment_type": item.get("payment_type"),
                    "status": item.get("status"),
                    "placements": item.get("placements"),
                    "nm_settings": item.get("nm_settings", [])
                }
                
                # 如果settings是嵌套的
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
    
    # 转换为列表
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

def build_yaml_config(selected_ids: List[int], id_to_name: Dict[int, str], weekdays: List[int], periods: List[dict], timezone: str) -> str:
    # 构建广告ID到名称的映射信息
    adverts_info = {}
    for adv_id in selected_ids:
        name = id_to_name.get(adv_id, "未命名")
        adverts_info[adv_id] = name
    
    cfg = {
        "timezone": timezone,
        "msk_timezone": "Europe/Moscow",
        "rate_limit": {"per_second": 4, "burst": 4},
        "wb": {
            "api_base": WB_API_BASE,
            "token_env": "WB_PROMO_TOKEN",
        },
        "rules": [
            {
                "name": "可视化创建的规则",
                "targets": {
                    "type": "ids", 
                    "ids": selected_ids,
                    "adverts": adverts_info  # 广告ID到名称的映射
                },
                "weekdays": weekdays,
                "periods": periods,  # [{"start":"08:00","end":"18:00","action":"start"}, ...]
                "exclude_dates": [],
                "priority": 100,
                "enabled": True,
            }
        ],
    }
    yaml_str = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    # 在ids行后添加注释，显示每个ID对应的名称
    if adverts_info:
        lines = yaml_str.split('\n')
        for i, line in enumerate(lines):
            if 'ids:' in line:
                # 找到ids行的缩进
                indent = len(line) - len(line.lstrip())
                # 添加注释行
                comment_lines = []
                for adv_id in selected_ids:
                    name = adverts_info.get(adv_id, "未命名")
                    comment_lines.append(' ' * indent + f"# {name} (ID: {adv_id})")
                # 在ids行后插入注释
                lines.insert(i + 1, '\n'.join(comment_lines))
                break
        yaml_str = '\n'.join(lines)
    return yaml_str

def in_period(now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
    if start_t <= end_t:
        return start_t <= now_t < end_t
    return (now_t >= start_t) or (now_t < end_t)  # 跨天

def decide_now_action(now: dtime, weekdays: List[int], periods: List[dict]) -> str | None:
    import datetime as _dt
    wd = (datetime.now().weekday() + 1)  # 1..7
    if wd not in weekdays:
        return None
    # 简化：多条period命中时，按列表先后为准
    for p in periods:
        st = _dt.time.fromisoformat(p["start"])
        et = _dt.time.fromisoformat(p["end"])
        if in_period(now, st, et):
            return p["action"]
    return None

# ---------------- UI ----------------
st.set_page_config(page_title="WB 广告定时规则编辑器", page_icon="⏰", layout="wide")

st.title("⏰ WB 广告定时规则编辑器（Streamlit）")
with st.expander("使用说明", expanded=False):
    st.markdown("""
- 左侧/下方填写 Token 或在 Secrets 添加 `WB_PROMO_TOKEN`
- 点击“加载广告活动”获取你的活动列表
- 选择广告 + 勾选星期 + 添加时间段，生成 YAML
- 下载配置：用于 `wb_ad_auto_scheduler.py`
- 可选：点击【Run once】立即对当前时刻执行一次开/关（不带循环定时）
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
            # 先获取原始数据用于调试
            url = f"{WB_API_BASE}/adv/v0/auction/adverts"
            headers = {"Authorization": token}
            params = {"statuses": "4,7,8,9,11"}
            r = requests.get(url, headers=headers, params=params, timeout=20)
            if r.status_code != 200:
                raise RuntimeError(f"auction/adverts {r.status_code}: {r.text}")
            raw_data = r.json()
            
            # 显示调试信息
            if show_debug:
                with st.expander("🔍 API原始数据（调试）", expanded=True):
                    st.json(raw_data)
                    # 显示数据结构信息
                    if isinstance(raw_data, list) and len(raw_data) > 0:
                        st.info(f"数据类型: 列表，包含 {len(raw_data)} 个元素")
                        st.json(raw_data[0] if len(raw_data) > 0 else {})
                    elif isinstance(raw_data, dict):
                        st.info(f"数据类型: 字典，键: {list(raw_data.keys())}")
            
            adverts = wb_get_auction_adverts(token, raw_data=raw_data)
            st.session_state["adverts"] = adverts
            st.session_state["raw_data"] = raw_data  # 保存原始数据
            st.success(f"加载到 {len(adverts)} 条活动")
            
            # 显示解析统计
            with_names = sum(1 for a in adverts if a.get("name"))
            st.info(f"其中 {with_names} 条包含名称信息")
        except Exception as e:
            st.error(f"加载失败：{e}")
            import traceback
            if show_debug:
                st.code(traceback.format_exc())

# 展示广告列表并选择
adverts = st.session_state.get("adverts", [])
if adverts:
    import pandas as pd
    df = []
    for a in adverts:
        df.append({
            "ID": a["id"],
            "名称": a.get("name"),
            "状态": STATUS_LABELS.get(a.get("status"), a.get("status")),
            "付费": a.get("payment_type"),
            "placements": (a.get("placements") or {}),
        })
    st.dataframe(pd.DataFrame(df))

    # 选择广告（按名称显示，值为 id）
    options = {f'{row["名称"] or "未命名"} (#{row["ID"]})': row["ID"] for row in df}
    # 创建ID到名称的映射
    id_to_name = {row["ID"]: row["名称"] or "未命名" for row in df}
    selected_labels = st.multiselect("选择要控制的广告活动", list(options.keys()))
    selected_ids = [options[k] for k in selected_labels]
    st.session_state["id_to_name"] = id_to_name
    
    # 显示已选择的广告信息
    if selected_ids:
        st.info(f"已选择 {len(selected_ids)} 个广告活动：")
        selected_info = []
        for adv_id in selected_ids:
            name = id_to_name.get(adv_id, "未命名")
            selected_info.append(f"• {name} (ID: {adv_id})")
        st.markdown("\n".join(selected_info))
else:
    selected_ids = []
    st.session_state["id_to_name"] = {}

st.markdown("---")

# 规则编辑
st.subheader("规则设置")
col1, col2, col3 = st.columns(3)

with col1:
    timezone = st.selectbox("时区（用于时间计算）", ["Europe/Moscow","Europe/Berlin","Asia/Shanghai","UTC"], index=0)

with col2:
    weekdays_map = {"周一":1,"周二":2,"周三":3,"周四":4,"周五":5,"周六":6,"周日":7}
    weekdays_labels = st.multiselect("星期（1=周一…7=周日）", list(weekdays_map.keys()), default=list(weekdays_map.keys()))
    weekdays = [weekdays_map[k] for k in weekdays_labels]

with col3:
    n_periods = st.number_input("时间段数量", min_value=1, max_value=10, value=2, step=1)

periods = []
for i in range(n_periods):
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        st.markdown(f"**时间段 {i+1}**")
    with c2:
        start_time = st.time_input(f"开始时间 {i+1}", value=dtime(9,0), key=f"start_{i}")
    with c3:
        end_time = st.time_input(f"结束时间 {i+1}", value=dtime(18,0), key=f"end_{i}")
    action = st.selectbox(f"动作 {i+1}", ["start","pause","stop"], key=f"act_{i}")
    periods.append({"start": start_time.strftime("%H:%M"), "end": end_time.strftime("%H:%M"), "action": action})

st.markdown("---")

# 生成 YAML
disabled_generate = (len(selected_ids) == 0)
id_to_name = st.session_state.get("id_to_name", {})
yaml_str = build_yaml_config(selected_ids, id_to_name, weekdays, periods, timezone)
st.code(yaml_str, language="yaml")

st.download_button(
    "⬇️ 下载 YAML 配置（wb_scheduler.config.yaml）",
    data=yaml_str.encode("utf-8"),
    file_name="wb_scheduler.config.yaml",
    mime="text/yaml",
    disabled=disabled_generate
)

# Run once（按当前时间立即执行一次）
st.markdown("### ⏱ Run once（当前时刻执行一次）")
if st.button("执行（对所选广告按当前时刻决定 start/pause/stop）", disabled=(not token or disabled_generate)):
    now = datetime.now().time()
    act = decide_now_action(now, weekdays, periods)
    if not act:
        st.info("当前时刻未命中任何时间段，不执行。")
    else:
        results = []
        id_to_name = st.session_state.get("id_to_name", {})
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
        # 以表格形式显示结果
        import pandas as pd
        results_df = pd.DataFrame(results)
        # 重新排列列的顺序，让名称更显眼
        if not results_df.empty:
            results_df = results_df[["name", "id", "action", "result"]]
            results_df.columns = ["广告名称", "广告ID", "执行动作", "执行结果"]
        st.dataframe(results_df, use_container_width=True)
        st.json({"results": results})
