# -*- coding: utf-8 -*-
"""
全局配置与常量模块
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 项目根目录
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

# WB API 配置
WB_API_TOKEN = os.getenv("WB_API_TOKEN", "")
WB_API_URL = os.getenv("WB_API_URL", "https://advert-api.wildberries.ru")

# 时区配置
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

# 日志配置
LOG_PATH = os.getenv("LOG_PATH", str(DATA_DIR / "logs.csv"))
CAMPAIGNS_CACHE_PATH = DATA_DIR / "campaigns.csv"
STRATEGIES_CONFIG_PATH = DATA_DIR / "strategies.json"

# API 请求配置
REQUEST_TIMEOUT = 30
RATE_LIMIT_PER_SECOND = 4

# 数据字段映射
STATUS_LABELS = {
    -1: "deleted",
    4: "ready",
    7: "completed",
    8: "declined",
    9: "active",
    11: "paused",
}

