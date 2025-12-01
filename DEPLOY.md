# 服务器部署指南

本文档说明如何在服务器（194.87.161.126）上部署WB广告管理系统。

## 前置要求

- 服务器已安装 Python 3.9+
- 服务器已安装 pip
- 服务器用户：`wb`（或根据实际情况调整）
- 服务器有 sudo 权限

## 部署步骤

### 方法1: 使用自动部署脚本（推荐）

1. **上传代码到服务器**

```bash
# 在本地执行
scp -r /Users/suan/Desktop/wb-ads/wb-ads user@194.87.161.126:/home/wb/
```

2. **SSH登录服务器**

```bash
ssh user@194.87.161.126
cd /home/wb/wb-ads
```

3. **设置环境变量**

```bash
# 编辑 ~/.bashrc 或创建 .env 文件
export WB_PROMO_TOKEN="你的Promotion类API Token"
export WB_API_TOKEN="你的API Token"
export API_BASE="http://194.87.161.126/api"
```

4. **运行部署脚本**

```bash
sudo bash deploy_server.sh
```

### 方法2: 手动部署

#### 步骤1: 安装依赖

```bash
cd /home/wb/wb-ads
pip3 install -r requirements.txt
pip3 install -r WB_SmartBid/requirements.txt
```

#### 步骤2: 创建systemd服务

创建文件 `/etc/systemd/system/wb-ads-streamlit.service`:

```ini
[Unit]
Description=WB广告管理系统 Streamlit服务
After=network.target

[Service]
Type=simple
User=wb
WorkingDirectory=/home/wb/wb-ads
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="WB_PROMO_TOKEN=你的Token"
Environment="WB_API_TOKEN=你的Token"
ExecStart=/usr/bin/python3 -m streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 步骤3: 启动服务

```bash
sudo systemctl daemon-reload
sudo systemctl enable wb-ads-streamlit.service
sudo systemctl start wb-ads-streamlit.service
```

#### 步骤4: 配置Nginx反向代理（可选）

创建文件 `/etc/nginx/sites-available/wb-ads`:

```nginx
server {
    listen 80;
    server_name 194.87.161.126;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/wb-ads /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 服务管理

### 查看服务状态

```bash
sudo systemctl status wb-ads-streamlit
```

### 查看日志

```bash
# 实时查看日志
sudo journalctl -u wb-ads-streamlit -f

# 查看最近100行
sudo journalctl -u wb-ads-streamlit -n 100
```

### 重启服务

```bash
sudo systemctl restart wb-ads-streamlit
```

### 停止服务

```bash
sudo systemctl stop wb-ads-streamlit
```

### 禁用服务

```bash
sudo systemctl disable wb-ads-streamlit
```

## 访问应用

部署完成后，可以通过以下地址访问：

- **直接访问**: `http://194.87.161.126:8501`
- **通过Nginx**: `http://194.87.161.126`（如果配置了Nginx）

## 防火墙配置

如果无法访问，可能需要开放端口：

```bash
# Ubuntu/Debian
sudo ufw allow 8501/tcp
sudo ufw allow 80/tcp  # 如果使用Nginx

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8501/tcp
sudo firewall-cmd --permanent --add-port=80/tcp
sudo firewall-cmd --reload
```

## 定时任务配置

### 定时开关任务

编辑crontab：

```bash
crontab -e
```

添加：

```cron
# 每30秒执行一次定时开关检查
* * * * * /usr/bin/python3 /home/wb/wb-ads/wb_ad_auto_scheduler.py --once >> /home/wb/logs/scheduler.log 2>&1
* * * * * sleep 30; /usr/bin/python3 /home/wb/wb-ads/wb_ad_auto_scheduler.py --once >> /home/wb/logs/scheduler.log 2>&1
```

### 智能出价任务

```cron
# 每60分钟执行一次智能出价优化
*/60 * * * * /usr/bin/python3 /home/wb/wb-ads/WB_SmartBid/main.py --once >> /home/wb/logs/bid.log 2>&1
```

## 故障排查

### 问题1: 服务无法启动

```bash
# 检查服务状态
sudo systemctl status wb-ads-streamlit

# 查看详细错误
sudo journalctl -u wb-ads-streamlit -n 50
```

### 问题2: 端口被占用

```bash
# 查看端口占用
sudo netstat -tulpn | grep 8501

# 或使用
sudo lsof -i :8501
```

### 问题3: 无法访问

1. 检查防火墙设置
2. 检查服务是否运行：`sudo systemctl status wb-ads-streamlit`
3. 检查端口是否监听：`sudo netstat -tulpn | grep 8501`
4. 检查Nginx配置（如果使用）：`sudo nginx -t`

### 问题4: Token错误

确保环境变量已正确设置：

```bash
# 检查环境变量
sudo systemctl show wb-ads-streamlit | grep Environment
```

## 更新部署

当代码更新后：

```bash
# 1. 拉取最新代码
cd /home/wb/wb-ads
git pull  # 或重新上传文件

# 2. 更新依赖（如果需要）
pip3 install -r requirements.txt

# 3. 重启服务
sudo systemctl restart wb-ads-streamlit
```

## 安全建议

1. **使用HTTPS**: 配置SSL证书，使用HTTPS访问
2. **限制访问**: 使用防火墙限制访问IP
3. **定期备份**: 备份 `WB_SmartBid/data/` 目录
4. **监控日志**: 定期检查服务日志
5. **更新依赖**: 定期更新Python依赖包

## 联系支持

如遇到问题，请检查：
- 服务日志：`sudo journalctl -u wb-ads-streamlit -f`
- 系统日志：`/var/log/syslog`
- Streamlit日志：`~/.streamlit/logs/`

