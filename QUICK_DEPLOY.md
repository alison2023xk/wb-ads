# 快速部署指南

## 一键部署到服务器

### 步骤1: 上传代码

```bash
# 在本地执行（替换user为你的服务器用户名）
scp -r /Users/suan/Desktop/wb-ads/wb-ads user@194.87.161.126:/home/wb/
```

### 步骤2: SSH登录服务器

```bash
ssh user@194.87.161.126
cd /home/wb/wb-ads
```

### 步骤3: 设置Token环境变量

编辑 `/etc/systemd/system/wb-ads-streamlit.service` 文件，在 `Environment=` 行填入你的Token：

```bash
sudo nano /etc/systemd/system/wb-ads-streamlit.service
```

或者创建 `.env` 文件：

```bash
cat > .env << EOF
WB_PROMO_TOKEN=你的Promotion类API Token
WB_API_TOKEN=你的API Token
API_BASE=http://194.87.161.126/api
EOF
```

### 步骤4: 运行部署脚本

```bash
sudo bash deploy_server.sh
```

### 步骤5: 访问应用

部署完成后，访问：
- **直接访问**: http://194.87.161.126:8501
- **通过Nginx**: http://194.87.161.126（如果配置了Nginx）

## 常用命令

```bash
# 查看服务状态
sudo systemctl status wb-ads-streamlit

# 查看实时日志
sudo journalctl -u wb-ads-streamlit -f

# 重启服务
sudo systemctl restart wb-ads-streamlit

# 停止服务
sudo systemctl stop wb-ads-streamlit
```

## 如果遇到问题

1. **检查服务是否运行**
   ```bash
   sudo systemctl status wb-ads-streamlit
   ```

2. **查看错误日志**
   ```bash
   sudo journalctl -u wb-ads-streamlit -n 50
   ```

3. **检查端口是否被占用**
   ```bash
   sudo netstat -tulpn | grep 8501
   ```

4. **检查防火墙**
   ```bash
   sudo ufw status
   sudo ufw allow 8501/tcp
   ```

## 手动启动（测试用）

如果systemd服务有问题，可以手动启动测试：

```bash
cd /home/wb/wb-ads
export WB_PROMO_TOKEN="你的Token"
export WB_API_TOKEN="你的Token"
streamlit run streamlit_app.py --server.port=8501 --server.address=0.0.0.0
```

然后访问 http://194.87.161.126:8501

