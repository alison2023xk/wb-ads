# WB广告管理系统

统一的WB广告管理平台，整合**定时开关**和**智能出价**两大核心功能。

## 功能概览

### ⏰ 定时开关功能
- 可视化配置广告定时开关规则
- 支持按星期、时间段设置启动/暂停/停止
- 导出YAML配置文件
- 立即执行测试

### 🤖 智能出价功能
- 自动监控广告数据（CTR、ROI、CPC等）
- 智能出价策略算法
- 自动执行出价调整
- 完整的日志记录和可视化

## 项目结构

```
wb-ads/
├── streamlit_app.py          # 统一前端界面（整合两个功能）
├── wb_ad_auto_scheduler.py   # 定时开关worker脚本
├── requirements.txt          # 依赖库清单
├── README.md                 # 本文件
└── WB_SmartBid/             # 智能出价模块
    ├── main.py              # 智能出价主任务调度
    ├── config.py            # 配置模块
    ├── fetcher.py           # 数据采集模块
    ├── strategy.py          # 出价策略模块
    ├── executor.py          # 出价执行模块
    ├── logger.py            # 日志模块
    ├── dashboard.py         # 智能出价前端（已整合到streamlit_app.py）
    └── data/                # 数据目录
        ├── campaigns.csv    # 广告数据缓存
        ├── logs.csv         # 出价调整日志
        └── strategies.json  # 策略配置文件
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

在Streamlit Cloud的Secrets中或本地环境变量中设置：

```
WB_PROMO_TOKEN=你的Promotion类API Token
WB_API_TOKEN=你的API Token（智能出价功能使用）
```

### 3. 启动应用

```bash
streamlit run streamlit_app.py
```

然后在浏览器访问 `http://localhost:8501`

## 使用说明

### 定时开关功能

1. 在侧边栏选择 **"⏰ 定时开关"**
2. 输入Token并加载广告活动
3. 选择要控制的广告
4. 添加定时规则（星期、时间段）
5. 下载YAML配置文件
6. 使用 `wb_ad_auto_scheduler.py` 脚本实现定时自动执行

**定时任务配置：**
```bash
# 每30秒扫描一次
python wb_ad_auto_scheduler.py --interval 30

# 仅执行一次（测试）
python wb_ad_auto_scheduler.py --once
```

### 智能出价功能

1. 在侧边栏选择 **"🤖 智能出价"**
2. 进入 **"📊 总览"** 查看广告数据（如无数据，点击"立即采集数据"）
3. 进入 **"⚙️ 策略配置"** 添加出价策略
4. 进入 **"📝 日志"** 查看出价调整历史

**定时任务配置（Timeweb）：**
```bash
# 每60分钟执行一次
*/60 * * * * /usr/bin/python3 /home/wb/WB_SmartBid/main.py --once >> /home/wb/logs/bid.log 2>&1
```

## 部署到Streamlit Cloud

1. 将代码推送到GitHub仓库
2. 在Streamlit Cloud选择仓库部署
3. 在App Secrets中添加：
   ```
   WB_PROMO_TOKEN = "你的Promotion类API Token"
   WB_API_TOKEN = "你的API Token"
   ```
4. 设置App路径为：`streamlit_app.py`

## 功能说明

### 定时开关

- **配置规则**：可视化设置广告的定时开关规则
- **生成配置**：导出YAML配置文件供定时任务使用
- **测试执行**：可以立即执行一次来测试规则是否正确
- **自动执行**：使用 `wb_ad_auto_scheduler.py` 脚本实现定时自动执行

### 智能出价

- **数据采集**：自动从WB API拉取广告数据
- **策略算法**：基于CTR和ROI自动计算新出价
- **自动调整**：自动执行出价更新
- **日志记录**：完整的出价调整日志和报警

## 注意事项

1. **Token安全**：不要将Token提交到Git仓库
2. **测试环境**：建议先在测试环境验证功能
3. **速率限制**：系统已实现API速率限制，避免触发限流
4. **数据备份**：定期备份 `WB_SmartBid/data/` 目录下的数据文件

## 更新日志

### V2.0.0 (2025-01-XX)
- ✅ 整合定时开关和智能出价功能到统一界面
- ✅ 优化导航和用户体验
- ✅ 统一Token管理

### V1.0.0
- ✅ 定时开关功能
- ✅ 智能出价功能（独立模块）
