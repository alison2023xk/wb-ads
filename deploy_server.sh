#!/bin/bash
# -*- coding: utf-8 -*-
# WB广告管理系统 - 服务器部署脚本
# 使用方法: bash deploy_server.sh

set -e

echo "=========================================="
echo "WB广告管理系统 - 服务器部署脚本"
echo "=========================================="

# 配置变量
PROJECT_DIR="/home/wb/wb-ads"
STREAMLIT_PORT=8501
STREAMLIT_HOST="0.0.0.0"

# 检查是否以root或sudo运行
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  请使用 sudo 运行此脚本"
    exit 1
fi

echo ""
echo "📦 步骤1: 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，正在安装..."
    apt-get update
    apt-get install -y python3 python3-pip
fi

PYTHON_VERSION=$(python3 --version)
echo "✅ $PYTHON_VERSION"

echo ""
echo "📦 步骤2: 安装依赖..."
pip3 install --upgrade pip
pip3 install -r requirements.txt

# 检查WB_SmartBid目录的依赖
if [ -d "WB_SmartBid" ]; then
    echo "📦 安装智能出价模块依赖..."
    pip3 install -r WB_SmartBid/requirements.txt
fi

echo ""
echo "📦 步骤3: 创建必要目录..."
mkdir -p $PROJECT_DIR/data
mkdir -p $PROJECT_DIR/logs
mkdir -p /etc/systemd/system

echo ""
echo "📦 步骤4: 创建systemd服务文件..."
cat > /etc/systemd/system/wb-ads-streamlit.service << EOF
[Unit]
Description=WB广告管理系统 Streamlit服务
After=network.target

[Service]
Type=simple
User=wb
WorkingDirectory=$PROJECT_DIR
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="WB_PROMO_TOKEN=${WB_PROMO_TOKEN:-}"
Environment="WB_API_TOKEN=${WB_API_TOKEN:-}"
ExecStart=/usr/bin/python3 -m streamlit run streamlit_app.py --server.port=$STREAMLIT_PORT --server.address=$STREAMLIT_HOST --server.headless=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "✅ 服务文件已创建: /etc/systemd/system/wb-ads-streamlit.service"

echo ""
echo "📦 步骤5: 配置Nginx反向代理（可选）..."
if command -v nginx &> /dev/null; then
    cat > /etc/nginx/sites-available/wb-ads << EOF
server {
    listen 80;
    server_name 194.87.161.126;

    location / {
        proxy_pass http://127.0.0.1:$STREAMLIT_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
EOF

    # 创建软链接
    if [ ! -L /etc/nginx/sites-enabled/wb-ads ]; then
        ln -s /etc/nginx/sites-available/wb-ads /etc/nginx/sites-enabled/
    fi
    
    # 测试nginx配置
    nginx -t && systemctl reload nginx
    echo "✅ Nginx配置完成"
else
    echo "⚠️  Nginx未安装，跳过反向代理配置"
    echo "   可以通过 http://194.87.161.126:$STREAMLIT_PORT 访问"
fi

echo ""
echo "📦 步骤6: 设置权限..."
chown -R wb:wb $PROJECT_DIR
chmod +x $PROJECT_DIR/*.py 2>/dev/null || true

echo ""
echo "📦 步骤7: 启动服务..."
systemctl daemon-reload
systemctl enable wb-ads-streamlit.service
systemctl start wb-ads-streamlit.service

echo ""
echo "=========================================="
echo "✅ 部署完成！"
echo "=========================================="
echo ""
echo "服务状态: systemctl status wb-ads-streamlit"
echo "查看日志: journalctl -u wb-ads-streamlit -f"
echo "重启服务: systemctl restart wb-ads-streamlit"
echo ""
if command -v nginx &> /dev/null; then
    echo "访问地址: http://194.87.161.126"
else
    echo "访问地址: http://194.87.161.126:$STREAMLIT_PORT"
fi
echo ""

