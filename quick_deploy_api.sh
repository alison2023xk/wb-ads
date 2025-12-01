#!/bin/bash
# 快速部署API服务器脚本
# 在服务器上执行此脚本

set -e

echo "=========================================="
echo "快速部署API服务器"
echo "=========================================="

# 检查是否以root运行
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  请使用 sudo 运行此脚本"
    exit 1
fi

PROJECT_DIR="/home/wb/wb-ads"

echo ""
echo "📦 步骤1: 安装依赖..."
pip3 install flask flask-cors

echo ""
echo "📦 步骤2: 创建目录..."
mkdir -p /opt/adsctl-data/backups
chown -R wb:wb /opt/adsctl-data 2>/dev/null || true

echo ""
echo "📦 步骤3: 创建systemd服务..."
cat > /etc/systemd/system/wb-ads-api.service << 'EOF'
[Unit]
Description=WB广告配置API服务
After=network.target

[Service]
Type=simple
User=wb
WorkingDirectory=/home/wb/wb-ads
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="CONFIG_SAVE_PATH=/opt/adsctl-data/config.yaml"
Environment="CONFIG_BACKUP_DIR=/opt/adsctl-data/backups"
Environment="API_PORT=5000"
Environment="API_HOST=0.0.0.0"
ExecStart=/usr/bin/python3 /home/wb/wb-ads/api_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo "📦 步骤4: 启动服务..."
systemctl daemon-reload
systemctl enable wb-ads-api.service
systemctl start wb-ads-api.service

echo ""
echo "📦 步骤5: 检查服务状态..."
sleep 2
systemctl status wb-ads-api.service --no-pager

echo ""
echo "=========================================="
echo "✅ API服务器部署完成！"
echo "=========================================="
echo ""
echo "服务状态: systemctl status wb-ads-api"
echo "查看日志: journalctl -u wb-ads-api -f"
echo "API地址: http://194.87.161.126:5000/api/config/save"
echo ""
echo "⚠️  注意：如果使用Nginx，需要配置反向代理"
echo ""

