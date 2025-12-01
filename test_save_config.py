#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地测试脚本：测试配置生成和保存功能
"""
import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

# 模拟 streamlit 的 session_state
class MockSessionState:
    def __init__(self):
        self._data = {}
    
    def get(self, key, default=None):
        return self._data.get(key, default)
    
    def __setitem__(self, key, value):
        self._data[key] = value
    
    def __getitem__(self, key):
        return self._data[key]

# 模拟 streamlit
class MockStreamlit:
    def __init__(self):
        self.session_state = MockSessionState()
    
    def checkbox(self, *args, **kwargs):
        return False
    
    def button(self, *args, **kwargs):
        return False
    
    def error(self, msg):
        print(f"❌ ERROR: {msg}")
    
    def success(self, msg):
        print(f"✅ SUCCESS: {msg}")
    
    def info(self, msg):
        print(f"ℹ️  INFO: {msg}")
    
    def write(self, msg):
        print(msg)

# 替换 streamlit
import streamlit_app
streamlit_app.st = MockStreamlit()

# 导入需要的函数
from streamlit_app import build_yaml_config

def test_config_generation():
    """测试配置生成"""
    print("=" * 60)
    print("测试配置生成功能")
    print("=" * 60)
    
    # 模拟数据
    selected_ids = [28580596]
    id_to_name = {28580596: "PSP400系列 自动 CM 9.12"}
    rules = [
        {
            "name": "规则 1",
            "weekdays": [7],  # 周日
            "periods": [
                {"start": "09:00", "end": "09:01", "action": "start"},
                {"start": "23:45", "end": "23:46", "action": "stop"}
            ],
            "enabled": True
        }
    ]
    timezone = "Europe/Moscow"
    
    print(f"\n输入数据:")
    print(f"- 选中的广告ID: {selected_ids}")
    print(f"- 广告名称映射: {id_to_name}")
    print(f"- 规则数量: {len(rules)}")
    print(f"- 时区: {timezone}")
    
    try:
        yaml_str = build_yaml_config(selected_ids, id_to_name, rules, timezone)
        
        print(f"\n✅ 配置生成成功!")
        print(f"配置长度: {len(yaml_str)} 字符")
        print("\n生成的配置内容:")
        print("-" * 60)
        print(yaml_str)
        print("-" * 60)
        
        # 验证 YAML 格式
        import yaml
        try:
            config = yaml.safe_load(yaml_str)
            print("\n✅ YAML 格式验证通过")
            print(f"配置包含 {len(config.get('rules', []))} 个规则")
        except Exception as e:
            print(f"\n❌ YAML 格式验证失败: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"\n❌ 配置生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_save_logic():
    """测试保存逻辑"""
    print("\n" + "=" * 60)
    print("测试保存逻辑")
    print("=" * 60)
    
    # 模拟 session_state
    st = streamlit_app.st
    st.session_state["selected_ids"] = [28580596]
    st.session_state["rules"] = [
        {
            "name": "规则 1",
            "weekdays": [7],
            "periods": [
                {"start": "09:00", "end": "09:01", "action": "start"},
                {"start": "23:45", "end": "23:46", "action": "stop"}
            ],
            "enabled": True
        }
    ]
    st.session_state["id_to_name"] = {28580596: "PSP400系列 自动 CM 9.12"}
    st.session_state["timezone"] = "Europe/Moscow"
    
    # 生成配置
    selected_ids = st.session_state.get("selected_ids", [])
    rules = st.session_state.get("rules", [])
    id_to_name = st.session_state.get("id_to_name", {})
    timezone = st.session_state.get("timezone", "Europe/Moscow")
    
    print(f"\n从 session_state 获取的数据:")
    print(f"- selected_ids: {selected_ids}")
    print(f"- rules 数量: {len(rules)}")
    print(f"- id_to_name: {id_to_name}")
    print(f"- timezone: {timezone}")
    
    # 检查条件
    if len(selected_ids) == 0:
        print("\n❌ 错误: 没有选中的广告")
        return False
    
    if len(rules) == 0:
        print("\n❌ 错误: 没有规则")
        return False
    
    # 检查规则有效性
    valid_rules = [r for r in rules if r.get("periods") and len(r.get("periods", [])) > 0]
    if len(valid_rules) == 0:
        print("\n❌ 错误: 规则中没有有效的 periods")
        return False
    
    print(f"\n✅ 验证通过: {len(valid_rules)} 个有效规则")
    
    # 生成配置
    try:
        yaml_data = build_yaml_config(selected_ids, id_to_name, rules, timezone)
        st.session_state["yaml_data"] = yaml_data
        
        print(f"\n✅ 配置已生成并保存到 session_state")
        print(f"配置长度: {len(yaml_data)} 字符")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 配置生成失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_save():
    """测试 API 保存（模拟）"""
    print("\n" + "=" * 60)
    print("测试 API 保存（模拟）")
    print("=" * 60)
    
    API_BASE = os.environ.get("API_BASE", "http://194.87.161.126/api")
    HEADERS = {}
    if os.environ.get("API_GATEWAY_TOKEN"):
        HEADERS["Authorization"] = f"Bearer {os.environ['API_GATEWAY_TOKEN']}"
    
    print(f"\nAPI 配置:")
    print(f"- API_BASE: {API_BASE}")
    print(f"- HEADERS: {HEADERS}")
    
    # 生成测试配置
    st = streamlit_app.st
    yaml_data = st.session_state.get("yaml_data", "")
    
    if not yaml_data:
        print("\n❌ 错误: session_state 中没有 yaml_data")
        return False
    
    print(f"\n准备发送的数据:")
    print(f"- 数据长度: {len(yaml_data.encode('utf-8'))} 字节")
    print(f"- 数据预览 (前200字符):\n{yaml_data[:200]}")
    
    # 模拟请求（不实际发送）
    print(f"\n⚠️  这是模拟测试，不会实际发送请求")
    print(f"如果要实际测试，请取消下面的注释")
    
    # 取消注释以实际测试
    # try:
    #     import requests
    #     r = requests.post(f"{API_BASE}/config/save", headers=HEADERS, data=yaml_data.encode("utf-8"), timeout=10)
    #     print(f"\n响应状态码: {r.status_code}")
    #     print(f"响应内容: {r.text}")
    #     if r.status_code == 200:
    #         print("\n✅ 保存成功!")
    #         return True
    #     else:
    #         print(f"\n❌ 保存失败: {r.status_code}")
    #         return False
    # except Exception as e:
    #     print(f"\n❌ 请求失败: {e}")
    #     return False
    
    return True

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("WB 广告配置保存功能 - 本地测试")
    print("=" * 60)
    
    # 运行测试
    test1 = test_config_generation()
    test2 = test_save_logic()
    test3 = test_api_save()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"配置生成测试: {'✅ 通过' if test1 else '❌ 失败'}")
    print(f"保存逻辑测试: {'✅ 通过' if test2 else '❌ 失败'}")
    print(f"API 保存测试: {'✅ 通过' if test3 else '❌ 失败'}")
    
    if test1 and test2 and test3:
        print("\n🎉 所有测试通过!")
    else:
        print("\n⚠️  部分测试失败，请检查上面的错误信息")

