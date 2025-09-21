#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
API服务模块
统一处理与AI模型API的交互，支持OpenAI格式的多种API提供商
"""

import base64
import json
import requests
from typing import Optional, Dict, Any
from io import BytesIO
from PyQt6.QtGui import QPixmap


# API提供商预设配置
API_PROVIDERS = {
    "硅基流动": {
        "multimodal_endpoint": "https://api.siliconflow.cn/v1/chat/completions",
        "chat_endpoint": "https://api.siliconflow.cn/v1/chat/completions",
        "multimodal_model": "Qwen/Qwen2-VL-72B-Instruct",
        "chat_model": "Qwen/Qwen2.5-72B-Instruct",
        "vision_support": True
    },
    "豆包": {
        "multimodal_endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "chat_endpoint": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "multimodal_model": "doubao-vision-pro",
        "chat_model": "doubao-pro-128k",
        "vision_support": True
    },
    "自定义": {
        "multimodal_endpoint": "",
        "chat_endpoint": "",
        "multimodal_model": "",
        "chat_model": "",
        "vision_support": True
    }
}


def get_text_from_image(api_key: str, endpoint: str, model: str, pixmap: QPixmap) -> str:
    """
    使用多模态大模型API从图像中提取文字 (OpenAI格式)

    Args:
        api_key: API密钥
        endpoint: API端点URL
        model: 模型名称
        pixmap: 要识别的图像

    Returns:
        str: 识别出的文字内容，失败时返回错误信息
    """
    try:
        # 步骤1: 将QPixmap转换为Base64字符串
        buffer = BytesIO()
        # QPixmap保存到BytesIO需要使用QBuffer
        from PyQt6.QtCore import QBuffer, QIODevice
        qbuffer = QBuffer()
        qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(qbuffer, "PNG")
        image_data = qbuffer.data().data()
        base64_image = base64.b64encode(image_data).decode('utf-8')

        # 步骤2: 构建"画面描述 + 文字提取"的专用Prompt
        system_prompt = (
            "你的任务是扮演一位专业的游戏场景分析师，精确地分析我提供的游戏截图。"
            "请严格按照以下格式进行输出，缺一不可：\n\n"
            "## 画面描述\n"
            "[在这里用1-2句话，客观、精炼地描述画面中的核心内容。例如：在昏暗的审讯室里，一个身穿红衣的女人正低头沉思，对面的宦官打扮的男人表情严肃地看着她。]\n\n"
            "## 对话内容\n"
            "[在这里一字不差地、完整地提取出图片中所有的对话文本、旁白、系统提示或任何形式的文字内容。如果图片中没有任何文字，请在此处明确写出\"无对话文字\"。]"
        )

        # 步骤3: 构造请求体 (OpenAI格式)
        request_body = {
            "model": model,
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的文字内容："
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        }

        # 步骤4: 构造请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        # 步骤5: 发送HTTP请求
        response = requests.post(
            endpoint,
            headers=headers,
            json=request_body,
            timeout=30  # 30秒超时
        )

        # 步骤6: 处理响应
        if response.status_code == 200:
            response_data = response.json()

            # 解析OpenAI格式响应
            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message", {})
                text_content = message.get("content", "")
                return text_content.strip() if text_content else "未识别到文字"
            else:
                return "API返回格式异常，未找到文字内容"
        else:
            # API返回错误
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "未知错误")
                return f"API调用失败 (状态码: {response.status_code}): {error_message}"
            except:
                return f"API调用失败，状态码: {response.status_code}"

    except requests.exceptions.Timeout:
        return "API调用超时，请检查网络连接"
    except requests.exceptions.ConnectionError:
        return "网络连接错误，请检查API端点地址和网络状态"
    except Exception as e:
        return f"图像识别过程中出现错误: {str(e)}"


def send_chat_request(api_key: str, endpoint: str, model: str, messages: list, max_tokens: int = 2000) -> str:
    """
    发送对话请求到对话模型API (OpenAI格式)

    Args:
        api_key: API密钥
        endpoint: API端点URL
        model: 模型名称
        messages: 消息列表
        max_tokens: 最大token数

    Returns:
        str: 模型回复内容，失败时返回错误信息
    """
    try:
        request_body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(
            endpoint,
            headers=headers,
            json=request_body,
            timeout=60  # 对话任务允许更长超时
        )

        if response.status_code == 200:
            response_data = response.json()

            if "choices" in response_data and len(response_data["choices"]) > 0:
                message = response_data["choices"][0].get("message", {})
                text_content = message.get("content", "")
                return text_content.strip() if text_content else "模型未返回有效内容"
            else:
                return "API返回格式异常，未找到回复内容"
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "未知错误")
                return f"API调用失败 (状态码: {response.status_code}): {error_message}"
            except:
                return f"API调用失败，状态码: {response.status_code}"

    except requests.exceptions.Timeout:
        return "API调用超时，请检查网络连接"
    except requests.exceptions.ConnectionError:
        return "网络连接错误，请检查API端点地址和网络状态"
    except Exception as e:
        return f"发送对话请求时出现错误: {str(e)}"


def load_api_config() -> dict:
    """
    从config.json加载API配置

    Returns:
        dict: 包含API配置的字典
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "multimodal_provider": "硅基流动",
            "chat_provider": "硅基流动",
            # 硅基流动配置
            "siliconflow": {
                "multimodal_api_key": "",
                "multimodal_model": "",
                "chat_api_key": "",
                "chat_model": ""
            },
            # 豆包配置
            "doubao": {
                "multimodal_api_key": "",
                "multimodal_model": "",
                "chat_api_key": "",
                "chat_model": ""
            },
            # 自定义配置
            "custom": {
                "multimodal_api_key": "",
                "multimodal_model": "",
                "multimodal_endpoint": "",
                "chat_api_key": "",
                "chat_model": "",
                "chat_endpoint": ""
            }
        }
    except Exception as e:
        print(f"加载API配置失败: {e}")
        return {}


def save_api_config(config: dict) -> bool:
    """
    保存API配置到config.json

    Args:
        config: 要保存的配置字典

    Returns:
        bool: 保存是否成功
    """
    try:
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存API配置失败: {e}")
        return False


def get_provider_config(provider_name: str) -> dict:
    """
    获取指定提供商的预设配置

    Args:
        provider_name: 提供商名称

    Returns:
        dict: 提供商配置
    """
    return API_PROVIDERS.get(provider_name, API_PROVIDERS["自定义"])


def test_api_connectivity(provider: str, api_key: str, api_endpoint: str, model_name: str) -> tuple:
    """
    统一的API连接测试函数

    Args:
        provider: API提供商名称 ("硅基流动", "豆包", "自定义")
        api_key: API密钥
        api_endpoint: API端点URL
        model_name: 模型名称

    Returns:
        tuple: (成功状态, 消息) 例如 (True, "连接成功") 或 (False, "错误信息...")
    """
    try:
        # 根据提供商构建不同的请求体和请求头
        if provider == "硅基流动":
            # 硅基流动使用标准OpenAI格式
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            test_body = {
                "model": model_name,
                "max_tokens": 10,
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello"
                    }
                ]
            }

        elif provider == "豆包":
            # 豆包也使用OpenAI格式，但可能有特殊的认证方式
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            test_body = {
                "model": model_name,
                "max_tokens": 10,
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello"
                    }
                ]
            }

        elif provider == "自定义":
            # 自定义提供商默认使用OpenAI格式
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            test_body = {
                "model": model_name,
                "max_tokens": 10,
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello"
                    }
                ]
            }

        else:
            return (False, f"不支持的API提供商: {provider}")

        # 发送测试请求
        response = requests.post(
            api_endpoint,
            headers=headers,
            json=test_body,
            timeout=10
        )

        if response.status_code == 200:
            return (True, "连接测试成功！")
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return (False, f"API错误: {error_msg}")
            except:
                return (False, f"HTTP错误: {response.status_code}")

    except requests.exceptions.Timeout:
        return (False, "连接超时")
    except requests.exceptions.ConnectionError:
        return (False, "网络连接错误")
    except Exception as e:
        return (False, f"测试异常: {str(e)}")


def test_api_connection(api_key: str, endpoint: str, model: str) -> dict:
    """
    测试API连接

    Args:
        api_key: API密钥
        endpoint: API端点
        model: 模型名称

    Returns:
        dict: 测试结果 {"success": bool, "message": str}
    """
    try:
        test_body = {
            "model": model,
            "max_tokens": 10,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ]
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        response = requests.post(
            endpoint,
            headers=headers,
            json=test_body,
            timeout=10
        )

        if response.status_code == 200:
            return {"success": True, "message": "连接测试成功！"}
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return {"success": False, "message": f"API错误: {error_msg}"}
            except:
                return {"success": False, "message": f"HTTP错误: {response.status_code}"}

    except requests.exceptions.Timeout:
        return {"success": False, "message": "连接超时"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "message": "网络连接错误"}
    except Exception as e:
        return {"success": False, "message": f"测试异常: {str(e)}"}


def get_text_from_audio(api_key: str, audio_data: bytes, sample_rate: int = 16000) -> str:
    """
    使用硅基流动语音识别API将音频转换为文字

    Args:
        api_key: 硅基流动API密钥
        audio_data: WAV格式音频数据
        sample_rate: 采样率，默认16000Hz

    Returns:
        str: 识别出的文字内容，失败时返回错误信息
    """
    try:
        # 硅基流动语音识别API端点
        endpoint = "https://api.siliconflow.cn/v1/audio/transcriptions"

        # 构建请求头 (不设置Content-Type，让requests自动设置)
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        # 构建data参数
        data = {
            "model": "FunAudioLLM/SenseVoiceSmall"
        }

        # 构建files参数 (使用multipart/form-data格式)
        files = {
            "file": ("temp_audio.wav", audio_data, "audio/wav")
        }

        # 发送请求
        response = requests.post(
            endpoint,
            headers=headers,
            data=data,
            files=files,
            timeout=30
        )

        if response.status_code == 200:
            response_data = response.json()
            text = response_data.get("text", "").strip()
            return text if text else "未识别到语音内容"
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", "未知错误")
                return f"语音识别API调用失败 (状态码: {response.status_code}): {error_message}"
            except:
                return f"语音识别API调用失败，状态码: {response.status_code}"

    except requests.exceptions.Timeout:
        return "语音识别API调用超时，请检查网络连接"
    except requests.exceptions.ConnectionError:
        return "网络连接错误，请检查网络状态"
    except Exception as e:
        return f"语音识别过程中出现错误: {str(e)}"


def test_stt_connectivity(api_key: str) -> tuple:
    """
    测试语音识别API连接

    Args:
        api_key: 硅基流动API密钥

    Returns:
        tuple: (成功状态, 消息) 例如 (True, "连接成功") 或 (False, "错误信息...")
    """
    try:
        # 硅基流动语音识别API端点
        endpoint = "https://api.siliconflow.cn/v1/models"

        # 构建请求头
        headers = {
            "Authorization": f"Bearer {api_key}"
        }

        # 发送简单的模型列表请求来测试连接
        response = requests.get(
            endpoint,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            # 检查返回的模型列表中是否包含语音识别模型
            try:
                models_data = response.json()
                models = models_data.get("data", [])

                # 检查是否包含SenseVoice模型
                has_stt_model = any("SenseVoice" in model.get("id", "") for model in models)

                if has_stt_model:
                    return (True, "语音识别API连接成功，支持SenseVoice模型！")
                else:
                    return (True, "API连接成功，但未发现SenseVoice语音识别模型")
            except:
                return (True, "API连接成功！")
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return (False, f"API错误: {error_message}")
            except:
                return (False, f"HTTP错误: {response.status_code}")

    except requests.exceptions.Timeout:
        return (False, "连接超时")
    except requests.exceptions.ConnectionError:
        return (False, "网络连接错误")
    except Exception as e:
        return (False, f"测试异常: {str(e)}")