# WB广告自动出价系统

## 项目概述

本项目是一个自动化的 Wildberries（WB）广告出价优化系统，能够基于广告实时数据和自定义策略，实现 **自动监控 → 智能分析 → 动态出价 → 日志记录 → 可视化展示** 的闭环控制。

### 核心功能

- ✅ 自动监控广告数据（CTR、ROI、CPC、曝光、点击等）
- ✅ 智能出价策略算法（基于CTR和ROI自动调整）
- ✅ 自动执行出价调整
- ✅ 完整的日志记录和报警系统
- ✅ Streamlit可视化前端
- ✅ 支持定时任务调度

## 项目结构

```
WB_SmartBid/
├── main.py              # 主任务调度入口
├── config.py            # 全局配置与常量
├── fetcher.py           # 广告数据采集模块
├── strategy.py          # 出价策略算法模块
├── executor.py          # 出价执行模块
├── logger.py            # 日志与报警模块
├── dashboard.py         # Streamlit 前端入口
├── requirements.txt     # 依赖库清单
├── .env.example         # 环境变量示例
├── README.md            # 本文件
└── data/                # 数据目录
    ├── campaigns.csv    # 广告活动数据缓存
    ├── logs.csv         # 出价调整日志
    └── strategies.json  # 策略配置文件
```

## 安装与配置

### 1. 安装依赖

```bash
cd WB_SmartBid
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
WB_API_TOKEN=your_token_here
WB_API_URL=https://advert-api.wildberries.ru
TIMEZONE=Europe/Moscow
LOG_PATH=./data/logs.csv
```

### 3. 配置策略

编辑 `data/strategies.json` 文件，配置你的出价策略：

```json
[
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
    "enabled": true
  }
]
```

## 使用方法

### 方式1: 命令行执行

#### 执行一次

```bash
python main.py --once
```

#### 定时循环执行（每1小时）

```bash
python main.py --interval 3600
```

### 方式2: Timeweb定时任务

在Timeweb服务器上配置crontab：

```bash
# 每60分钟执行一次
*/60 * * * * /usr/bin/python3 /home/wb/WB_SmartBid/main.py --once >> /home/wb/logs/bid.log 2>&1
```

### 方式3: Streamlit前端

启动Streamlit前端界面：

```bash
streamlit run dashboard.py
```

然后在浏览器中访问 `http://localhost:8501`

前端功能包括：
- **总览页**: 查看广告花费、ROI、CTR、CPC等关键指标和趋势图
- **策略配置页**: 新增/修改/删除出价策略
- **日志页**: 查看历史出价调整记录，导出CSV报告
- **系统设置页**: 管理Token、查看系统信息

## 出价策略说明

系统根据以下规则自动调整出价：

1. **CTR过低且ROI良好** → 提升出价
2. **CTR过高或ROI下降** → 降低出价
3. **曝光过低** → 提升出价
4. **ROI连续3周期低于目标** → 自动暂停广告

## 报警机制

系统会在以下情况触发报警：

- 出价涨幅 > 50%
- ROI连续3周期下降
- 无曝光超过24小时
- API请求错误

## API接口说明

### 使用的WB API端点

- `GET /adv/v2/list` - 获取广告活动列表
- `GET /adv/v3/fullstats` - 获取广告统计数据
- `PATCH /adv/v3/campaigns/{id}/bids` - 更新出价（需根据实际API文档调整）
- `GET /adv/v0/pause` - 暂停广告

**注意**: 实际API端点可能需要根据WB官方文档进行调整。

## 开发说明

### 模块说明

- **config.py**: 全局配置，包括API地址、Token、文件路径等
- **fetcher.py**: 负责从WB API拉取广告数据并缓存
- **strategy.py**: 出价策略算法，根据CTR/ROI计算新出价
- **executor.py**: 执行出价调整，调用WB API更新出价
- **logger.py**: 记录所有出价调整日志，提供报警功能
- **main.py**: 主任务调度，协调各个模块完成优化流程
- **dashboard.py**: Streamlit前端，提供可视化界面

### 扩展开发

- 多账号管理：在config.py中添加多Token支持
- AI预测模型：在strategy.py中集成机器学习模型
- Telegram Bot：在logger.py中实现Telegram推送
- 自动预算分配：新增budget.py模块

## 注意事项

1. **API Token安全**: 不要将Token提交到Git仓库，使用环境变量或Secrets管理
2. **速率限制**: 系统已实现速率限制（默认4次/秒），避免触发API限流
3. **数据备份**: 定期备份 `data/` 目录下的数据文件
4. **测试环境**: 建议先在测试环境验证策略效果

## 故障排查

### 问题1: 无法获取广告数据

- 检查Token是否正确配置
- 检查网络连接
- 查看API返回的错误信息

### 问题2: 出价更新失败

- 检查API端点是否正确
- 确认出价值是否在允许范围内
- 查看日志文件了解详细错误

### 问题3: Streamlit无法启动

- 确认已安装所有依赖: `pip install -r requirements.txt`
- 检查Python版本（建议3.9+）

## 许可证

本项目仅供学习和研究使用。

## 更新日志

### V1.0.0 (2025-01-XX)

- ✅ 实现基础数据采集功能
- ✅ 实现出价策略算法
- ✅ 实现出价执行模块
- ✅ 实现日志记录和报警
- ✅ 实现Streamlit前端界面
- ✅ 支持定时任务调度

