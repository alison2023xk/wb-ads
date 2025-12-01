# API服务器部署指南

## 概述

`api_server.py` 是一个简单的Flask API服务，用于处理配置文件的保存和读取。

## 功能

- `POST /api/config/save` - 保存YAML配置文件
- `GET /api/config/get` - 获取配置文件
- `GET /api/health` - 健康检查
- 自动备份功能

## 安装步骤

### 1. 安装依赖

```bash
pip3 install -r api_requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件或设置环境变量：

```bash
export CONFIG_SAVE_PATH="/opt/adsctl-data/config.yaml"
export CONFIG_BACKUP_DIR="/opt/adsctl-data/backups"
export API_PORT=5000
export API_HOST=0.0.0.0
export API_GATEWAY_TOKEN="你的Token（可选，但推荐设置）"
```

### 3. 创建必要目录

```bash
sudo mkdir -p /opt/adsctl-data/backups
sudo chown -R wb:wb /opt/adsctl-data
```

### 4. 测试运行

```bash
python3 api_server.py
```

应该看到：
```
Starting API server on 0.0.0.0:5000
Config save path: /opt/adsctl-data/config.yaml
Backup directory: /opt/adsctl-data/backups
```

### 5. 配置为系统服务

```bash
# 复制服务文件
sudo cp api_server.service /etc/systemd/system/

# 编辑服务文件，设置正确的路径和Token
sudo nano /etc/systemd/system/api_server.service

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable api_server.service
sudo systemctl start api_server.service

# 查看状态
sudo systemctl status api_server.service
```

### 6. 配置Nginx反向代理（可选）

如果需要通过80端口访问API，可以配置Nginx：

```nginx
server {
    listen 80;
    server_name 194.87.161.126;

    # API端点
    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Streamlit应用
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

然后重新加载Nginx：
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 测试API

### 测试保存配置

```bash
curl -X POST http://194.87.161.126:5000/api/config/save \
  -H "Content-Type: text/yaml" \
  -H "Authorization: Bearer 你的Token" \
  --data-binary @wb_scheduler.config.yaml
```

### 测试获取配置

```bash
curl http://194.87.161.126:5000/api/config/get \
  -H "Authorization: Bearer 你的Token"
```

### 健康检查

```bash
curl http://194.87.161.126:5000/api/health
```

## 安全建议

1. **设置API Token**：在生产环境中，务必设置 `API_GATEWAY_TOKEN`
2. **使用HTTPS**：配置SSL证书，使用HTTPS访问
3. **防火墙**：只开放必要的端口
4. **权限控制**：确保配置文件目录的权限正确

## 故障排查

### 问题1: 服务无法启动

```bash
# 查看日志
sudo journalctl -u api_server -f

# 检查端口是否被占用
sudo netstat -tulpn | grep 5000
```

### 问题2: 权限错误

```bash
# 检查目录权限
ls -la /opt/adsctl-data

# 修复权限
sudo chown -R wb:wb /opt/adsctl-data
sudo chmod 755 /opt/adsctl-data
```

### 问题3: 404错误

- 检查API服务是否运行：`sudo systemctl status api_server`
- 检查Nginx配置是否正确
- 检查防火墙是否开放了5000端口

## 更新Streamlit应用配置

在Streamlit应用中，确保 `API_BASE` 环境变量指向正确的地址：

```bash
export API_BASE="http://194.87.161.126/api"
# 或者如果使用Nginx反向代理
export API_BASE="http://194.87.161.126/api"
```

如果API服务运行在不同的端口，需要调整：
```bash
export API_BASE="http://194.87.161.126:5000/api"
```

