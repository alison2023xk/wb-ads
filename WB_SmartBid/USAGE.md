# 使用指南

## 快速开始

### 1. 环境准备

```bash
# 安装Python依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 WB_API_TOKEN
```

### 2. 配置策略

编辑 `data/strategies.json`，设置你的出价策略参数。

### 3. 运行系统

#### 方式A: 单次执行（测试）

```bash
python main.py --once
```

#### 方式B: 定时循环执行

```bash
# 每1小时执行一次
python main.py --interval 3600
```

#### 方式C: 使用Streamlit前端

```bash
streamlit run dashboard.py
```

然后在浏览器访问 `http://localhost:8501`

## 策略配置详解

### 策略参数说明

- `keyword`: 关键词（必填）
- `region`: 地区（必填）
- `target_ctr_min`: CTR目标下限（0-1之间的小数）
- `target_ctr_max`: CTR目标上限（0-1之间的小数）
- `target_roi`: 目标ROI值（建议1.5-2.5）
- `min_bid`: 最小出价（整数，单位：分）
- `max_bid`: 最大出价（整数，单位：分）
- `step`: 每次调整的步长（整数，单位：分）
- `interval_hours`: 调整间隔（小时）
- `enabled`: 是否启用（true/false）

### 策略逻辑

1. **CTR < 目标下限 且 ROI > 目标ROI** → 提升出价（+step，不超过max_bid）
2. **CTR > 目标上限 或 ROI < 目标ROI** → 降低出价（-step，不低于min_bid）
3. **曝光 < 100** → 提升出价
4. **ROI连续3周期 < 目标ROI** → 自动暂停广告

## Timeweb部署

### 1. 上传代码到服务器

```bash
# 使用git或scp上传WB_SmartBid目录到服务器
scp -r WB_SmartBid user@your-server:/home/wb/
```

### 2. 安装依赖

```bash
ssh user@your-server
cd /home/wb/WB_SmartBid
pip3 install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 编辑 ~/.bashrc 或创建 .env 文件
export WB_API_TOKEN="your_token_here"
export WB_API_URL="https://advert-api.wildberries.ru"
export TIMEZONE="Europe/Moscow"
```

### 4. 配置Crontab定时任务

```bash
crontab -e
```

添加以下行（每60分钟执行一次）：

```cron
*/60 * * * * /usr/bin/python3 /home/wb/WB_SmartBid/main.py --once >> /home/wb/logs/bid.log 2>&1
```

### 5. 查看日志

```bash
tail -f /home/wb/logs/bid.log
```

## Streamlit Cloud部署

### 1. 推送代码到GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/wb-smartbid.git
git push -u origin main
```

### 2. 在Streamlit Cloud部署

1. 访问 https://streamlit.io/cloud
2. 选择你的GitHub仓库
3. 设置App路径为: `WB_SmartBid/dashboard.py`
4. 在Secrets中添加:
   ```
   WB_API_TOKEN = "your_token_here"
   ```

## 常见问题

### Q: 如何查看出价调整历史？

A: 使用Streamlit前端，进入"日志"页面，或直接查看 `data/logs.csv` 文件。

### Q: 如何暂停某个策略？

A: 在Streamlit前端的"策略配置"页面，取消勾选"启用"选项。

### Q: API调用失败怎么办？

A: 
1. 检查Token是否正确
2. 检查网络连接
3. 查看日志文件了解详细错误
4. 确认API端点是否正确（可能需要根据WB文档调整）

### Q: 如何调整策略参数？

A: 
1. 在Streamlit前端"策略配置"页面修改
2. 或直接编辑 `data/strategies.json` 文件

## 注意事项

⚠️ **重要提示**:

1. 首次使用前，建议先用 `--once` 参数测试，确认策略效果
2. 出价调整会影响实际广告花费，请谨慎设置策略参数
3. 定期检查日志，确保系统正常运行
4. 建议设置合理的 `min_bid` 和 `max_bid` 范围，避免出价异常

