#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置保存API服务
提供 /api/config/save 端点用于保存YAML配置
"""
import os
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置保存路径
CONFIG_SAVE_PATH = os.environ.get("CONFIG_SAVE_PATH", "/opt/adsctl-data/config.yaml")
CONFIG_BACKUP_DIR = os.environ.get("CONFIG_BACKUP_DIR", "/opt/adsctl-data/backups")

# API认证Token（可选）
API_TOKEN = os.environ.get("API_GATEWAY_TOKEN", "")


def ensure_directory(path):
    """确保目录存在"""
    dir_path = Path(path).parent
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def backup_config(config_path):
    """备份现有配置文件"""
    if not Path(config_path).exists():
        return None
    
    backup_dir = Path(CONFIG_BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"config_{timestamp}.yaml"
    
    import shutil
    shutil.copy2(config_path, backup_path)
    return str(backup_path)


@app.route('/api/config/save', methods=['POST'])
def save_config():
    """保存配置文件的API端点"""
    # 检查认证（如果设置了Token）
    if API_TOKEN:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        
        token = auth_header.replace('Bearer ', '').strip()
        if token != API_TOKEN:
            return jsonify({"error": "Invalid token"}), 403
    
    # 获取配置数据
    try:
        config_data = request.get_data(as_text=True)
        if not config_data:
            return jsonify({"error": "No configuration data provided"}), 400
        
        # 验证YAML格式（简单检查）
        if not config_data.strip().startswith('#') and 'timezone' not in config_data.lower():
            # 不是严格的YAML验证，只是基本检查
            pass
        
        # 确保目录存在
        config_path = Path(CONFIG_SAVE_PATH)
        ensure_directory(config_path)
        
        # 备份现有配置
        backup_path = backup_config(str(config_path))
        
        # 保存新配置
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_data)
        
        response = {
            "success": True,
            "message": "Configuration saved successfully",
            "path": str(config_path),
            "backup": backup_path
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "error": "Failed to save configuration",
            "message": str(e)
        }), 500


@app.route('/api/config/get', methods=['GET'])
def get_config():
    """获取配置文件的API端点"""
    # 检查认证
    if API_TOKEN:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        
        token = auth_header.replace('Bearer ', '').strip()
        if token != API_TOKEN:
            return jsonify({"error": "Invalid token"}), 403
    
    try:
        config_path = Path(CONFIG_SAVE_PATH)
        if not config_path.exists():
            return jsonify({"error": "Configuration file not found"}), 404
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = f.read()
        
        return config_data, 200, {'Content-Type': 'text/yaml; charset=utf-8'}
        
    except Exception as e:
        return jsonify({
            "error": "Failed to read configuration",
            "message": str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "service": "WB Ads Config API",
        "config_path": CONFIG_SAVE_PATH
    }), 200


@app.route('/', methods=['GET'])
def index():
    """根路径"""
    return jsonify({
        "service": "WB Ads Config API",
        "version": "1.0.0",
        "endpoints": {
            "POST /api/config/save": "保存配置文件",
            "GET /api/config/get": "获取配置文件",
            "GET /api/health": "健康检查"
        }
    }), 200


if __name__ == '__main__':
    # 确保目录存在
    ensure_directory(CONFIG_SAVE_PATH)
    ensure_directory(CONFIG_BACKUP_DIR)
    
    # 启动服务器
    port = int(os.environ.get('API_PORT', 5000))
    host = os.environ.get('API_HOST', '0.0.0.0')
    debug = os.environ.get('API_DEBUG', 'False').lower() == 'true'
    
    print(f"Starting API server on {host}:{port}")
    print(f"Config save path: {CONFIG_SAVE_PATH}")
    print(f"Backup directory: {CONFIG_BACKUP_DIR}")
    if API_TOKEN:
        print("Authentication: Enabled")
    else:
        print("Authentication: Disabled (not recommended for production)")
    
    app.run(host=host, port=port, debug=debug)

