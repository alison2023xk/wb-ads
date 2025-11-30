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
from typing import List, Dict, Tuple

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

def build_yaml_config(selected_ids: List[int], id_to_name: Dict[int, str], rules: List[dict], timezone: str) -> str:
    """
    构建YAML配置
    rules: 规则列表，每个规则包含 {name, weekdays, periods, priority, enabled}
    """
    # 构建广告ID到名称的映射信息
    adverts_info = {}
    for adv_id in selected_ids:
        name = id_to_name.get(adv_id, "未命名")
        adverts_info[adv_id] = name
    
    # 构建规则列表
    yaml_rules = []
    for idx, rule in enumerate(rules):
        yaml_rule = {
            "name": rule.get("name", f"规则 {idx + 1}"),
            "targets": {
                "type": "ids", 
                "ids": selected_ids,
                "adverts": adverts_info  # 广告ID到名称的映射
            },
            "weekdays": rule.get("weekdays", []),
            "periods": rule.get("periods", []),
            "exclude_dates": rule.get("exclude_dates", []),
            "priority": rule.get("priority", 100),
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

def decide_now_action(now: dtime, rules: List[dict]) -> Tuple[str | None, str]:
    """
    根据当前时间和规则列表决定执行的动作
    返回: (action, rule_name) 或 (None, "")
    """
    import datetime as _dt
    wd = (datetime.now().weekday() + 1)  # 1..7
    
    # 收集所有匹配的规则和动作
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
    
    # 按优先级排序，取优先级最高的
    candidates.sort(key=lambda x: x["priority"], reverse=True)
    return candidates[0]["action"], candidates[0]["rule_name"]

# ---------------- UI ----------------
st.set_page_config(page_title="WB 广告定时规则编辑器", page_icon="⏰", layout="wide")

st.title("⏰ WB 广告定时规则编辑器（Streamlit）")
with st.expander("📖 使用说明", expanded=True):
    st.markdown("""
### 这个应用的作用：
1. **配置规则**：可视化设置广告的定时开关规则
2. **生成配置文件**：导出 YAML 配置文件供定时任务使用
3. **测试执行**：可以立即执行一次来测试规则是否正确

### ⚠️ 重要说明：
- **"Run once"按钮**：只执行**一次**，不会自动重复执行
- **不需要保持 Streamlit 运行**：这个应用只是用来配置和测试的
- **要实现定时自动执行**：需要使用 `wb_ad_auto_scheduler.py` 脚本（后台定时任务）

### 使用流程：
1. 填写 Token 或在 Secrets 添加 `WB_PROMO_TOKEN`
2. 点击"加载广告活动"获取活动列表
3. 选择广告 + 设置星期和时间段
4. 下载 YAML 配置文件
5. 使用 `wb_ad_auto_scheduler.py` 脚本加载配置文件，实现定时自动执行
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

# 时区设置
timezone = st.selectbox("时区（用于时间计算）", ["Europe/Moscow","Europe/Berlin","Asia/Shanghai","UTC"], index=0)

# 规则管理
st.markdown("#### 📋 添加多个规则")
st.markdown("""
**使用说明**：
- 可以添加多个规则，每个规则可以设置不同的星期几和时间段
- 例如：规则1设置"周一到周五 13:00-22:00"，规则2设置"周六周日 全天开启"
- 优先级：数字越大优先级越高，当多个规则同时匹配时，优先级高的规则生效
""")

# 初始化规则列表
if "rules" not in st.session_state:
    st.session_state["rules"] = []

weekdays_map = {"周一":1,"周二":2,"周三":3,"周四":4,"周五":5,"周六":6,"周日":7}

# 添加规则按钮
col_add, col_clear = st.columns([1, 1])
with col_add:
    if st.button("➕ 添加新规则", use_container_width=True):
        st.session_state["rules"].append({
            "name": f"规则 {len(st.session_state['rules']) + 1}",
            "weekdays": [],
            "periods": [],
            "priority": 100,
            "enabled": True
        })
with col_clear:
    if st.button("🗑️ 清空所有规则", use_container_width=True):
        st.session_state["rules"] = []

# 显示和编辑规则
rules = st.session_state.get("rules", [])
if not rules:
    st.info("👆 点击「添加新规则」开始配置")

for rule_idx, rule in enumerate(rules):
    with st.expander(f"📌 {rule.get('name', f'规则 {rule_idx + 1}')} {'✅' if rule.get('enabled', True) else '❌'}", expanded=True):
        # 规则名称和基本设置
        col_name, col_priority, col_enabled = st.columns([2, 1, 1])
        with col_name:
            rule["name"] = st.text_input("规则名称", value=rule.get("name", f"规则 {rule_idx + 1}"), key=f"rule_name_{rule_idx}")
        with col_priority:
            rule["priority"] = st.number_input("优先级", min_value=0, max_value=1000, value=rule.get("priority", 100), key=f"rule_priority_{rule_idx}", help="数字越大优先级越高")
        with col_enabled:
            rule["enabled"] = st.checkbox("启用", value=rule.get("enabled", True), key=f"rule_enabled_{rule_idx}")
        
        # 选择星期几
        st.markdown("**选择星期几**")
        weekdays_labels = st.multiselect(
            "星期（可多选）", 
            list(weekdays_map.keys()), 
            default=[k for k, v in weekdays_map.items() if v in rule.get("weekdays", [])],
            key=f"rule_weekdays_{rule_idx}"
        )
        rule["weekdays"] = [weekdays_map[k] for k in weekdays_labels]
        
        # 时间段设置
        st.markdown("**时间段设置**")
        if f"n_periods_{rule_idx}" not in st.session_state:
            st.session_state[f"n_periods_{rule_idx}"] = len(rule.get("periods", [1]))
        
        n_periods = st.number_input(
            "时间段数量", 
            min_value=1, 
            max_value=10, 
            value=st.session_state[f"n_periods_{rule_idx}"],
            step=1,
            key=f"n_periods_input_{rule_idx}"
        )
        st.session_state[f"n_periods_{rule_idx}"] = n_periods
        
        # 初始化periods
        if len(rule.get("periods", [])) < n_periods:
            for i in range(len(rule.get("periods", [])), n_periods):
                rule.setdefault("periods", []).append({"start": "09:00", "end": "18:00", "action": "start"})
        elif len(rule.get("periods", [])) > n_periods:
            rule["periods"] = rule["periods"][:n_periods]
        
        periods = []
        for i in range(n_periods):
            st.markdown(f"**时间段 {i+1}**")
            c1, c2, c3 = st.columns([1, 1, 1])
            
            # 获取已有的时间段数据
            existing_period = rule.get("periods", [{}])[i] if i < len(rule.get("periods", [])) else {}
            start_str = existing_period.get("start", "09:00")
            end_str = existing_period.get("end", "18:00")
            action_str = existing_period.get("action", "start")
            
            # 解析时间字符串
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            
            with c1:
                start_time = st.time_input(f"开始时间", value=dtime(start_h, start_m), key=f"start_{rule_idx}_{i}")
            with c2:
                end_time = st.time_input(f"结束时间", value=dtime(end_h, end_m), key=f"end_{rule_idx}_{i}")
            with c3:
                action = st.selectbox(f"动作", ["start","pause","stop"], index=["start","pause","stop"].index(action_str) if action_str in ["start","pause","stop"] else 0, key=f"act_{rule_idx}_{i}")
            
            periods.append({
                "start": start_time.strftime("%H:%M"), 
                "end": end_time.strftime("%H:%M"), 
                "action": action
            })
        
        rule["periods"] = periods
        
        # 删除规则按钮
        if st.button("🗑️ 删除此规则", key=f"delete_rule_{rule_idx}", use_container_width=True):
            st.session_state["rules"].pop(rule_idx)
            st.rerun()

st.markdown("---")

# 生成 YAML
disabled_generate = (len(selected_ids) == 0) or (len(rules) == 0)
id_to_name = st.session_state.get("id_to_name", {})
yaml_str = build_yaml_config(selected_ids, id_to_name, rules, timezone)
st.code(yaml_str, language="yaml")

st.markdown("#### 📥 下载配置文件")
st.markdown("""
下载的 YAML 配置文件可以用于 `wb_ad_auto_scheduler.py` 脚本实现定时自动执行。

**使用方法**：
1. 下载配置文件到本地
2. 运行 `wb_ad_auto_scheduler.py` 脚本，指定配置文件路径
3. 脚本会在后台持续运行，按照配置的时间规则自动执行
""")
st.download_button(
    "⬇️ 下载 YAML 配置（wb_scheduler.config.yaml）",
    data=yaml_str.encode("utf-8"),
    file_name="wb_scheduler.config.yaml",
    mime="text/yaml",
    disabled=disabled_generate
)

# Run once（按当前时间立即执行一次）
st.markdown("### ⏱ 立即执行一次（测试用）")
st.info("💡 **提示**：此功能只执行一次，不会自动重复。要实现定时自动执行，请使用 `wb_ad_auto_scheduler.py` 脚本。")
if st.button("🚀 立即执行一次（根据当前时间判断应该执行的动作）", disabled=(not token or disabled_generate)):
    now = datetime.now().time()
    act, rule_name = decide_now_action(now, rules)
    if not act:
        st.info("当前时刻未命中任何时间段，不执行。")
    else:
        st.info(f"匹配规则：{rule_name}，执行动作：{act}")
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
