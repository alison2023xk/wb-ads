# 快速部署API服务器 - 解决404错误

## 问题

Streamlit应用尝试保存配置到 `http://194.87.161.126/api/config/save`，但返回404错误。

## 解决方案

### 步骤1: 上传API服务器文件到服务器

```bash
# 在本地执行
scp api_server.py user@194.87.161.126:/home/wb/wb-ads/
scp quick_deploy_api.sh user@194.87.161.126:/home/wb/wb-ads/
```

### 步骤2: SSH登录服务器并部署

```bash
ssh user@194.87.161.126
cd /home/wb/wb-ads
sudo bash quick_deploy_api.sh
```

### 步骤3: 配置Nginx反向代理

编辑nginx配置：

```bash
sudo nano /etc/nginx/sites-available/default
# 或
sudo nano /etc/nginx/conf.d/wb-ads.conf
```

添加以下配置（参考 `nginx_api_config.conf`）：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 10M;
}
```

测试并重新加载：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 步骤4: 测试API

```bash
# 健康检查
curl http://194.87.161.126/api/health

# 应该返回：
# {"status":"ok","service":"WB Ads Config API",...}
```

### 步骤5: 在Streamlit应用中测试

现在可以在Streamlit应用中点击"保存到服务器"按钮，应该可以正常工作了。

## 如果仍然404

### 检查1: API服务是否运行

```bash
sudo systemctl status wb-ads-api
```

### 检查2: 端口是否监听

```bash
sudo netstat -tulpn | grep 5000
# 应该看到 python3 在监听 5000 端口
```

### 检查3: Nginx配置是否正确

```bash
# 检查nginx配置
sudo nginx -t

# 查看nginx错误日志
sudo tail -f /var/log/nginx/error.log
```

### 检查4: 防火墙

```bash
# 检查防火墙
sudo ufw status

# 如果需要，开放端口
sudo ufw allow 5000/tcp
```

## 临时解决方案：直接保存文件

如果API服务器暂时无法部署，可以使用以下方法：

### 方法1: 通过SSH直接保存

1. 在Streamlit应用中点击"下载YAML配置"
2. 下载配置文件
3. SSH登录服务器
4. 执行：

```bash
# 创建目录（如果不存在）
sudo mkdir -p /opt/adsctl-data
sudo chown -R wb:wb /opt/adsctl-data

# 上传文件（使用scp）
# 在本地执行：
scp wb_scheduler_config_*.yaml user@194.87.161.126:/opt/adsctl-data/config.yaml

# 或在服务器上直接创建：
cat > /opt/adsctl-data/config.yaml << 'EOF'
# 粘贴YAML内容
EOF
```

### 方法2: 修改API地址

如果API服务运行在不同的端口或路径，可以在Streamlit应用中设置环境变量：

```bash
export API_BASE="http://194.87.161.126:5000/api"
```

## 验证部署

部署完成后，应该能够：

1. ✅ 访问 `http://194.87.161.126/api/health` 返回健康状态
2. ✅ 在Streamlit应用中点击"保存到服务器"成功
3. ✅ 配置文件保存到 `/opt/adsctl-data/config.yaml`

## 故障排查命令

```bash
# 查看API服务日志
sudo journalctl -u wb-ads-api -f

# 查看nginx访问日志
sudo tail -f /var/log/nginx/access.log

# 测试API端点
curl -X POST http://127.0.0.1:5000/api/config/save \
  -H "Content-Type: text/yaml" \
  --data-binary @test_config.yaml
```

