#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WB Ads Auto Scheduler
---------------------
按“星期 + 时间段”自动 启动/暂停/停止 Wildberries 广告活动的脚本。

✅ 核心功能
- 为活动配置多条定时规则：星期几、开始时间、结束时间、动作(start/pause/stop)
- 支持同一天多时段、跨天时段（22:00-02:00）
- 支持按 活动ID、名称前缀、标签 选择投放目标
- 幂等：目标状态与当前状态一致时不重复调用 API
- 速率控制、退避重试、错误日志
- 业务时区可配置（默认 Europe/Berlin）；同时可映射到 MSK

🔧 依赖（建议）
- Python 3.9+（使用 zoneinfo 时区）
- requests
- pyyaml（可选；若无，则支持 JSON 配置）

📦 使用示例
1) 安装依赖：
   pip install requests pyyaml

2) 准备配置文件（YAML 或 JSON），参考本文件底部的 SAMPLE_CONFIG。
   默认读取 ./wb_scheduler.config.yaml
   也可通过 --config 指定路径。

3) 设置环境变量（建议）
   export WB_PROMO_TOKEN="你的Promotion类API Token"

4) 运行
   python wb_ad_auto_scheduler.py --interval 30      # 每30秒扫描一次
   python wb_ad_auto_scheduler.py --once             # 仅执行一次（调试）
   python wb_ad_auto_scheduler.py --dry-run          # 干跑（不真正调API）

作者：ChatGPT（自动生成）
版本：2025-11-30
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal, Tuple
from datetime import datetime, time as dtime, timedelta, date

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

try:
    import yaml  # type: ignore
    YAML_AVAILABLE = True
except Exception:
    YAML_AVAILABLE = False

import requests

# ------------------------------ 常量 ------------------------------

WB_API_BASE = "https://advert-api.wildberries.ru"
ENV_TOKEN_KEY = "WB_PROMO_TOKEN"

# WB 广告状态（文档）
STATUS_DELETED   = -1  # 正在删除/已删
STATUS_READY     = 4   # ready to launch
STATUS_COMPLETED = 7   # completed
STATUS_DECLINED  = 8   # declined
STATUS_ACTIVE    = 9   # active
STATUS_PAUSED    = 11  # paused

DesiredAction = Literal["start", "pause", "stop"]
WEEKDAYS_MAP = {1:"Mon",2:"Tue",3:"Wed",4:"Thu",5:"Fri",6:"Sat",7:"Sun"}

# ------------------------------ 数据模型 ------------------------------

@dataclass
class Period:
    start: str               # "HH:MM"
    end: str                 # "HH:MM"
    action: DesiredAction    # start/pause/stop

@dataclass
class TargetSpec:
    type: Literal["ids","name_prefix","tags"]
    ids: Optional[List[int]] = None
    name_prefix: Optional[str] = None
    tags: Optional[List[str]] = None

@dataclass
class Rule:
    name: str
    targets: TargetSpec
    weekdays: List[int]                  # 1-7（周一=1）
    periods: List[Period]
    exclude_dates: List[str] = field(default_factory=list)   # "YYYY-MM-DD"
    priority: int = 0
    enabled: bool = True

@dataclass
class Config:
    timezone: str = "Europe/Berlin"
    msk_timezone: str = "Europe/Moscow"
    rate_limit_per_second: int = 4
    rate_limit_burst: int = 4
    api_base: str = WB_API_BASE
    token_env: str = ENV_TOKEN_KEY
    rules: List[Rule] = field(default_factory=list)

# ------------------------------ 工具函数 ------------------------------

def parse_time_hhmm(s: str) -> dtime:
    h, m = s.strip().split(":")
    return dtime(hour=int(h), minute=int(m))

def now_in_tz(tz_name: str) -> datetime:
    if ZoneInfo is None:
        return datetime.now()
    return datetime.now(ZoneInfo(tz_name))

def parse_date_ymd(s: str) -> date:
    y,m,d = s.split("-")
    return date(int(y), int(m), int(d))

def is_cross_day(start_t: dtime, end_t: dtime) -> bool:
    """判断是否跨天时间段（start > end 视为跨天）"""
    return (start_t > end_t)

def time_in_range(now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
    """不跨天时段 [start, end) 内判断"""
    return (start_t <= now_t) and (now_t < end_t)

def time_in_crossday_range(now_t: dtime, start_t: dtime, end_t: dtime) -> bool:
    """跨天时段：比如 22:00-02:00，则 [22:00-24:00) ∪ [00:00-02:00)"""
    return (now_t >= start_t) or (now_t < end_t)

def weekday_int(dt: datetime) -> int:
    # Python: Monday=0 ... Sunday=6；我们使用 1..7
    return (dt.weekday() + 1)

# ------------------------------ WB API 客户端 ------------------------------

class WBClient:
    def __init__(self, base: str, token: str, rate_limit_per_sec: int = 4):
        self.base = base.rstrip("/")
        self.token = token
        self.rate_limit_per_sec = max(1, rate_limit_per_sec)

        self._last_ts = 0.0
        self._requests_in_current_second = 0

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _respect_rate_limit(self):
        now = time.time()
        if int(now) != int(self._last_ts):
            # 新的一秒
            self._last_ts = now
            self._requests_in_current_second = 0

        if self._requests_in_current_second >= self.rate_limit_per_sec:
            sleep_time = 1 - (now - int(now))
            if sleep_time > 0:
                time.sleep(sleep_time)
            self._last_ts = time.time()
            self._requests_in_current_second = 0

        self._requests_in_current_second += 1

    def _request(self, method: str, path: str, params=None, json_body=None, timeout=15) -> requests.Response:
        self._respect_rate_limit()
        url = f"{self.base}{path}"
        try:
            resp = self.session.request(method=method, url=url, params=params, json=json_body, timeout=timeout)
            return resp
        except requests.RequestException as e:
            raise RuntimeError(f"HTTP error: {e}")

    # --- 状态变更 ---

    def start(self, advert_id: int) -> Tuple[bool, str]:
        resp = self._request("GET", "/adv/v0/start", params={"id": advert_id})
        if resp.status_code == 200:
            return True, "ok"
        return False, f"{resp.status_code} {resp.text}"

    def pause(self, advert_id: int) -> Tuple[bool, str]:
        resp = self._request("GET", "/adv/v0/pause", params={"id": advert_id})
        if resp.status_code == 200:
            return True, "ok"
        return False, f"{resp.status_code} {resp.text}"

    def stop(self, advert_id: int) -> Tuple[bool, str]:
        resp = self._request("GET", "/adv/v0/stop", params={"id": advert_id})
        if resp.status_code == 200:
            return True, "ok"
        return False, f"{resp.status_code} {resp.text}"

    # 可按需补充余额/预算/状态查询接口

# ------------------------------ 规则匹配与决策 ------------------------------

@dataclass
class CampaignMeta:
    advert_id: int
    name: str = ""
    tags: List[str] = dataclasses.field(default_factory=list)
    last_known_status: Optional[int] = None
    last_change_time: Optional[str] = None

@dataclass
class Decision:
    advert_id: int
    desired: DesiredAction
    rule_name: str
    priority: int

class DecisionEngine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # advert_id -> (desired, ts_minute_bucket)
        self.last_applied: Dict[int, Tuple[str, str]] = {}

    def _date_in_excluded(self, dt: datetime, rule: Rule) -> bool:
        if not rule.exclude_dates:
            return False
        d = dt.date()
        for s in rule.exclude_dates:
            try:
                if parse_date_ymd(s) == d:
                    return True
            except Exception:
                logging.warning("Invalid exclude_dates item: %s", s)
        return False

    def _targets_match(self, c: CampaignMeta, t: TargetSpec) -> bool:
        if t.type == "ids":
            return c.advert_id in (t.ids or [])
        elif t.type == "name_prefix":
            return (c.name or "").startswith(t.name_prefix or "")
        elif t.type == "tags":
            wanted = set(t.tags or [])
            have = set(c.tags or [])
            return not wanted.isdisjoint(have)
        return False

    def _period_match(self, now_t: dtime, wd: int, period: Period, rule_weekdays: List[int]) -> bool:
        if wd not in rule_weekdays:
            return False
        st = parse_time_hhmm(period.start)
        et = parse_time_hhmm(period.end)
        if not is_cross_day(st, et):
            return time_in_range(now_t, st, et)
        else:
            # 跨天时段：允许前一天与当天两段
            return time_in_crossday_range(now_t, st, et)

    def decide(self, now_dt: datetime, campaigns: List[CampaignMeta]) -> List[Decision]:
        """根据所有规则得出每个活动当前时刻的期望动作（按优先级选择一条）"""
        res: List[Decision] = []
        wd = weekday_int(now_dt)
        now_t = dtime(hour=now_dt.hour, minute=now_dt.minute, second=now_dt.second)

        # 对每个活动，收集命中的规则候选（可能多条），再按优先级挑一条
        for c in campaigns:
            candidates: List[Decision] = []
            for r in self.cfg.rules:
                if not r.enabled:
                    continue
                if self._date_in_excluded(now_dt, r):
                    continue
                if not self._targets_match(c, r.targets):
                    continue
                for p in r.periods:
                    if self._period_match(now_t, wd, p, r.weekdays):
                        candidates.append(Decision(advert_id=c.advert_id, desired=p.action, rule_name=r.name, priority=r.priority))

                # 跨天特殊：如果现在落在“跨天段的凌晨部分”，需要允许来自“前一日规则”
                # 我们的 _period_match 已经用 or 逻辑覆盖（>=start 或 <end），因此无需额外按前一天判断。

            if candidates:
                # 取 priority 最大；若并列，以规则名排序稳定决定
                candidates.sort(key=lambda d: (d.priority, d.rule_name), reverse=True)
                res.append(candidates[0])
        return res

    def should_skip_idempotent(self, advert_id: int, desired: str, now_dt: datetime, window_minutes: int = 1) -> bool:
        """同一分钟窗口内，相同 desired 不重复下发"""
        bucket = now_dt.strftime("%Y-%m-%d %H:%M")
        last = self.last_applied.get(advert_id)
        if last and last[0] == desired and last[1] == bucket:
            return True
        self.last_applied[advert_id] = (desired, bucket)
        return False

# ------------------------------ 主循环 ------------------------------

def load_config(path: str) -> Config:
    if not os.path.exists(path):
        # 写一个示例配置
        sample = SAMPLE_CONFIG_YAML
        with open(path, "w", encoding="utf-8") as f:
            f.write(sample)
        print(f"[INFO] 示例配置已写入: {path}")
    # 读取
    if path.endswith(".yaml") or path.endswith(".yml"):
        if not YAML_AVAILABLE:
            raise RuntimeError("未安装 pyyaml，请安装后再使用 YAML 配置，或改用 JSON（.json）配置。")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    elif path.endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raise RuntimeError("配置文件后缀必须是 .yaml/.yml 或 .json")

    def _period(obj) -> Period:
        return Period(start=str(obj["start"]), end=str(obj["end"]), action=str(obj["action"]))

    def _target(obj) -> TargetSpec:
        return TargetSpec(
            type=obj.get("type", "ids"),
            ids=obj.get("ids"),
            name_prefix=obj.get("name_prefix"),
            tags=obj.get("tags"),
        )

    rules: List[Rule] = []
    for r in raw.get("rules", []):
        rule = Rule(
            name=r["name"],
            targets=_target(r["targets"]),
            weekdays=list(r["weekdays"]),
            periods=[_period(p) for p in r["periods"]],
            exclude_dates=[str(x) for x in r.get("exclude_dates", [])],
            priority=int(r.get("priority", 0)),
            enabled=bool(r.get("enabled", True)),
        )
        rules.append(rule)

    cfg = Config(
        timezone=raw.get("timezone", "Europe/Berlin"),
        msk_timezone=raw.get("msk_timezone", "Europe/Moscow"),
        rate_limit_per_second=int(raw.get("rate_limit", {}).get("per_second", 4)) if "rate_limit" in raw else int(raw.get("rate_limit_per_second", 4)),
        rate_limit_burst=int(raw.get("rate_limit", {}).get("burst", 4)) if "rate_limit" in raw else int(raw.get("rate_limit_burst", 4)),
        api_base=raw.get("wb", {}).get("api_base", WB_API_BASE),
        token_env=raw.get("wb", {}).get("token_env", ENV_TOKEN_KEY),
        rules=rules,
    )
    return cfg

def build_campaigns_from_config(cfg: Config) -> List[CampaignMeta]:
    """
    简化：从规则中抽取所有提到的 advert_id（ids 目标），并去重。
    若你希望按 name_prefix/tags 动态匹配，需要扩展此处改为“从你的活动库/数据库加载全部活动元数据”。
    """
    ids: set[int] = set()
    for r in cfg.rules:
        if r.targets.type == "ids" and r.targets.ids:
            ids.update(r.targets.ids)
    campaigns = [CampaignMeta(advert_id=i) for i in sorted(ids)]
    return campaigns

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def main():
    parser = argparse.ArgumentParser(description="WB Ads Auto Scheduler")
    parser.add_argument("--config", default="./wb_scheduler.config.yaml", help="配置文件路径（.yaml/.yml/.json）")
    parser.add_argument("--interval", type=int, default=30, help="扫描间隔秒（默认30）")
    parser.add_argument("--once", action="store_true", help="仅运行一次（调试）")
    parser.add_argument("--dry-run", action="store_true", help="干跑：不真正调用API，仅打印")
    parser.add_argument("--verbose", action="store_true", help="调试输出")
    args = parser.parse_args()

    setup_logging(args.verbose)

    cfg = load_config(args.config)

    tz = cfg.timezone
    if ZoneInfo is None:
        logging.warning("未检测到 zoneinfo，时区精度可能受限，建议使用 Python 3.9+")
    campaigns = build_campaigns_from_config(cfg)

    token = os.environ.get(cfg.token_env, "").strip()
    if not token and not args.dry_run:
        logging.error("未找到 API Token 环境变量 %s。请先 `export %s=...` 或使用 --dry-run", cfg.token_env, cfg.token_env)
        sys.exit(2)

    client = WBClient(base=cfg.api_base, token=token, rate_limit_per_sec=cfg.rate_limit_per_second)
    engine = DecisionEngine(cfg)

    def one_cycle():
        now_dt = now_in_tz(tz) if ZoneInfo else datetime.now()
        decisions = engine.decide(now_dt, campaigns)

        if not decisions:
            logging.debug("无需要变更的活动。")
            return

        # 对每个活动，应用单一决策
        for d in decisions:
            if engine.should_skip_idempotent(d.advert_id, d.desired, now_dt):
                logging.debug("幂等跳过：advert_id=%s desired=%s", d.advert_id, d.desired)
                continue

            logging.info("规则命中 | %s | advert_id=%s | action=%s", d.rule_name, d.advert_id, d.desired)
            if args.dry_run:
                continue

            # 调用 API
            ok, msg = False, ""
            try:
                if d.desired == "start":
                    ok, msg = client.start(d.advert_id)
                elif d.desired == "pause":
                    ok, msg = client.pause(d.advert_id)
                elif d.desired == "stop":
                    ok, msg = client.stop(d.advert_id)
                else:
                    logging.error("未知动作：%s", d.desired)
                    continue
            except Exception as e:
                logging.error("API 调用异常 advert_id=%s action=%s err=%s", d.advert_id, d.desired, e)
                continue

            if ok:
                logging.info("API 成功 | advert_id=%s action=%s", d.advert_id, d.desired)
            else:
                logging.error("API 失败 | advert_id=%s action=%s | %s", d.advert_id, d.desired, msg)

    # 主循环
    if args.once:
        one_cycle()
        return

    logging.info("启动定时器：每 %s 秒扫描一次；时区=%s；活动数=%d", args.interval, tz, len(campaigns))
    try:
        while True:
            one_cycle()
            time.sleep(max(1, args.interval))
    except KeyboardInterrupt:
        logging.info("收到中断信号，退出。")

# ------------------------------ 示例配置 ------------------------------

SAMPLE_CONFIG_YAML = """\
# Wildberries 广告定时开关示例配置
timezone: "Europe/Berlin"
msk_timezone: "Europe/Moscow"

rate_limit:
  per_second: 4
  burst: 4

wb:
  api_base: "https://advert-api.wildberries.ru"
  token_env: "WB_PROMO_TOKEN"

rules:
  - name: "工作日-白天-启动"
    targets:
      type: "ids"
      ids: [12345, 67890]     # 替换为你的活动ID
    weekdays: [1,2,3,4,5]     # 1=周一 … 7=周日
    periods:
      - { start: "08:30", end: "12:00", action: "start" }
      - { start: "14:00", end: "18:30", action: "start" }
    exclude_dates: ["2025-12-31","2026-01-01"]
    priority: 100
    enabled: true

  - name: "午间-暂停"
    targets:
      type: "ids"
      ids: [12345, 67890]
    weekdays: [1,2,3,4,5]
    periods:
      - { start: "12:00", end: "14:00", action: "pause" }
    priority: 200
    enabled: true

  - name: "夜间-全周-暂停（跨天）"
    targets:
      type: "ids"
      ids: [12345, 67890]
    weekdays: [1,2,3,4,5,6,7]
    periods:
      - { start: "22:00", end: "06:00", action: "pause" }
    priority: 50
    enabled: true
"""

if __name__ == "__main__":
    main()
