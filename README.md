# WB Ads Scheduler (Streamlit + Worker)

## 目录
- `streamlit_app.py` — 可视化编辑器：选择广告、设置星期与时间段、导出 YAML、Run once
- `wb_ad_auto_scheduler.py` — 定时 worker：读取 YAML，按规则循环执行 API
- `requirements.txt` — 依赖列表

## 使用
1. 将三文件推到 GitHub 仓库。
2. 在 Streamlit Cloud 部署 `streamlit_app.py`，Secrets 添加：
   ```
   WB_PROMO_TOKEN = "你的 Promotion 类 API Token"
   ```
3. 在本地/服务器运行 `wb_ad_auto_scheduler.py`：
   - 首次运行自动生成 `wb_scheduler.config.yaml`
   - 或直接从 Streamlit 下载的 YAML 覆盖本地同名文件
   - 运行：`python wb_ad_auto_scheduler.py --interval 60`

> 说明：Streamlit 不建议在前端应用里跑无限循环的后台任务，因此把“定时循环”放在独立的 worker 脚本中更稳妥；Streamlit 端提供可视化配置与手动一次性执行（Run once）。
