#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
互动游戏AI军师 (Interactive Game AI Counsel)
主程序文件
"""

import sys
import os
import datetime
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QLineEdit, QInputDialog, QMessageBox,
    QMenuBar, QMenu
)
from PyQt6.QtCore import Qt, QRect, QTimer, QThread, pyqtSignal, QObject, QSize
from PyQt6.QtGui import QFont, QPixmap, QClipboard, QAction, QKeySequence, QIcon, QShortcut

# 启用高DPI缩放支持
# 这会让应用能够正确感知到操作系统的显示缩放比例
if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

# 导入截图工具
from snipping_tool import SnippingWidget

# 导入API服务
from api_service import get_text_from_image, load_api_config, save_api_config, get_provider_config, test_api_connectivity, API_PROVIDERS

# 导入音频处理模块
from audio_processing import AudioRecorder, STTWorker



## 已移除低级键盘钩子实现，采用消息窗口+WM_HOTKEY 方案。
class WinHotkeyWorker(QThread):
    """基于隐藏消息窗口的 WM_HOTKEY 监听（推荐路径）。"""
    hotkey = pyqtSignal(str)

    def run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p)==8 else ctypes.c_long,
                                     wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        self.WM_HOTKEY = 0x0312
        self.MOD_CONTROL = 0x0002
        self.VK_1 = 0x31
        self.VK_2 = 0x32

        class WNDCLASS(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint),
                        ("lpfnWndProc", ctypes.c_void_p),
                        ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE),
                        ("hIcon", ctypes.c_void_p),
                        ("hCursor", ctypes.c_void_p),
                        ("hbrBackground", ctypes.c_void_p),
                        ("lpszMenuName", wintypes.LPCWSTR),
                        ("lpszClassName", wintypes.LPCWSTR)]

        self.hwnd = None

        # 明确声明 DefWindowProcW 的签名，避免 64 位下参数溢出告警
        LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p)==8 else ctypes.c_long
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        @WNDPROC
        def _wnd_proc(hWnd, msg, wParam, lParam):
            if msg == self.WM_HOTKEY:
                hotkey_id = int(wParam)
                if hotkey_id == 101:
                    self.hotkey.emit("ctrl+1")
                elif hotkey_id == 102:
                    self.hotkey.emit("ctrl+2")
                return 0
            elif msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hWnd, msg, wParam, lParam)

        hInstance = kernel32.GetModuleHandleW(None)
        className = "QtHotkeyMsgWnd"

        wndclass = WNDCLASS()
        wndclass.style = 0
        wndclass.lpfnWndProc = ctypes.cast(_wnd_proc, ctypes.c_void_p).value
        wndclass.cbClsExtra = 0
        wndclass.cbWndExtra = 0
        wndclass.hInstance = hInstance
        wndclass.hIcon = 0
        wndclass.hCursor = 0
        wndclass.hbrBackground = 0
        wndclass.lpszMenuName = None
        wndclass.lpszClassName = className

        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        if not atom:
            # 可能已注册，继续
            pass

        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                           wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, ctypes.c_void_p, wintypes.HINSTANCE, ctypes.c_void_p]
        user32.CreateWindowExW.restype = wintypes.HWND

        self.hwnd = user32.CreateWindowExW(0, className, "", 0,
                                           0, 0, 0, 0,
                                           0, 0, hInstance, None)
        if not self.hwnd:
            print("消息窗口创建失败")
            return

        # 注册热键到此隐藏窗口
        if not user32.RegisterHotKey(self.hwnd, 101, self.MOD_CONTROL, self.VK_1):
            print("RegisterHotKey(hwnd, Ctrl+1) 失败")
        if not user32.RegisterHotKey(self.hwnd, 102, self.MOD_CONTROL, self.VK_2):
            print("RegisterHotKey(hwnd, Ctrl+2) 失败")

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # 清理
        user32.UnregisterHotKey(self.hwnd, 101)
        user32.UnregisterHotKey(self.hwnd, 102)
        user32.DestroyWindow(self.hwnd)
        self.hwnd = None

    def stop(self):
        if hasattr(self, 'hwnd') and self.hwnd:
            ctypes.windll.user32.PostMessageW(self.hwnd, 0x0010, 0, 0)  # WM_CLOSE


class VoiceInputManager(QObject):
    """语音输入管理器 - 负责所有语音输入相关功能"""

    # 信号定义
    status_updated = pyqtSignal(str, str)  # 状态文本, 颜色代码
    text_recognized = pyqtSignal(str)      # 识别出的文字

    def __init__(self, api_config):
        super().__init__()

        # 保存API配置引用
        self.api_config = api_config

        # 内部状态
        self.service_enabled = False
        self.is_recording = False

        # 音频相关组件
        self.audio_recorder = AudioRecorder()
        self.stt_worker = None
        self.recording_timer = None

        # 重置定时器句柄
        self.reset_timer = None

    def toggle_service(self, enabled: bool):
        """启用或禁用语音服务"""
        self.service_enabled = enabled

        if enabled:
            # 检查API配置
            stt_api_key = self.api_config.get("stt_siliconflow_api_key", "")
            if not stt_api_key:
                self.status_updated.emit("请先配置语音识别API Key", "#F44336")
                return False

            self.status_updated.emit("语音功能开启 (按Shift键切换录音)", "#4CAF50")
        else:
            # 如果正在录音，先停止
            if self.is_recording:
                self._stop_recording()
            self.status_updated.emit("语音功能关闭", "#888888")

        return True

    def handle_key_press(self, event):
        """处理键盘按下事件"""
        # 只处理我们关心的Shift键
        if (self.service_enabled and
            event.key() == Qt.Key.Key_Shift and
            not event.isAutoRepeat()):

            # 切换录音状态
            if self.is_recording:
                self._stop_recording()
            else:
                self._start_recording()

            # 管理器自己消费掉处理的事件
            event.accept()
            return True  # 表示事件已被处理

        return False  # 表示事件未被处理

    def _start_recording(self):
        """开始录音"""
        # 关键修复：在开始新录音前，取消任何等待重置的旧定时器
        if self.reset_timer:
            self.reset_timer.stop()

        try:
            if self.audio_recorder.start_recording():
                self.is_recording = True
                self.status_updated.emit("🔴 正在录音... (再按Shift键停止)", "#F44336")

                # 启动录制定时器
                self.recording_timer = QTimer()
                self.recording_timer.timeout.connect(self.audio_recorder.record_chunk)
                self.recording_timer.start(50)  # 每50ms录制一次

        except Exception as e:
            self.status_updated.emit(f"录音启动失败: {str(e)}", "#F44336")

    def _stop_recording(self):
        """停止录音"""
        try:
            self.is_recording = False

            # 停止录制定时器
            if self.recording_timer:
                self.recording_timer.stop()
                self.recording_timer = None

            # 获取录制的音频数据
            audio_data = self.audio_recorder.stop_recording()

            if audio_data:
                self.status_updated.emit("🔄 正在识别中...", "#FF9800")

                # 启动语音转文字
                stt_api_key = self.api_config.get("stt_siliconflow_api_key", "")
                self.stt_worker = STTWorker(audio_data, stt_api_key)
                self.stt_worker.stt_completed.connect(self._on_stt_completed)
                self.stt_worker.stt_failed.connect(self._on_stt_failed)
                self.stt_worker.start()
            else:
                self.status_updated.emit("语音功能开启 (按Shift键切换录音)", "#4CAF50")

        except Exception as e:
            self.status_updated.emit(f"录音停止失败: {str(e)}", "#F44336")

    def _on_stt_completed(self, text: str):
        """语音识别完成"""
        if text and text != "未识别到语音内容":
            self.text_recognized.emit(text)
            self.status_updated.emit(f"✅ 识别成功: {text[:20]}...", "#4CAF50")
        else:
            self.status_updated.emit("❌ 未识别到有效语音", "#FF9800")

        # 如果已有定时器在运行，先停止它
        if self.reset_timer:
            self.reset_timer.stop()

        # 创建新的定时器实例并连接
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self._reset_status)
        self.reset_timer.start(3000)

    def _on_stt_failed(self, error_message: str):
        """语音识别失败"""
        self.status_updated.emit("❌ 识别失败", "#F44336")

        # 如果已有定时器在运行，先停止它
        if self.reset_timer:
            self.reset_timer.stop()

        # 创建新的定时器实例并连接
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self._reset_status)
        self.reset_timer.start(3000)

    def _reset_status(self):
        """重置状态"""
        if self.service_enabled:
            self.status_updated.emit("语音功能开启 (按Shift键切换录音)", "#4CAF50")


class OCRWorker(QThread):
    """OCR工作线程，用于在后台调用多模态API"""

    # 定义信号
    ocr_completed = pyqtSignal(str)  # OCR完成信号，传递识别结果
    ocr_failed = pyqtSignal(str)     # OCR失败信号，传递错误信息

    def __init__(self, pixmap: QPixmap, api_key: str, endpoint: str, model: str):
        super().__init__()
        self.pixmap = pixmap
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model

    def run(self):
        """在后台线程中执行OCR"""
        try:
            # 调用多模态API进行图像识别
            result = get_text_from_image(self.api_key, self.endpoint, self.model, self.pixmap)

            # 检查结果是否包含错误信息
            if result.startswith(("API调用失败", "网络连接错误", "API调用超时", "图像识别过程中出现错误")):
                self.ocr_failed.emit(result)
            else:
                self.ocr_completed.emit(result)

        except Exception as e:
            self.ocr_failed.emit(f"OCR工作线程异常: {str(e)}")


class ChatWorker(QThread):
    """对话API工作线程，用于在后台调用对话模型进行内容整合润色"""

    # 定义信号
    chat_completed = pyqtSignal(str)  # 对话完成信号，传递处理结果
    chat_failed = pyqtSignal(str)     # 对话失败信号，传递错误信息

    def __init__(self, messages: list, api_key: str, endpoint: str, model: str):
        super().__init__()
        self.messages = messages
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model

    def run(self):
        """在后台线程中执行对话API调用"""
        try:
            # 调用对话API进行内容整合
            from api_service import send_chat_request
            result = send_chat_request(self.api_key, self.endpoint, self.model, self.messages)

            # 检查结果是否包含错误信息
            if result.startswith(("API调用失败", "网络连接错误", "API调用超时", "发送对话请求时出现错误")):
                self.chat_failed.emit(result)
            else:
                self.chat_completed.emit(result)

        except Exception as e:
            self.chat_failed.emit(f"对话工作线程异常: {str(e)}")



class DecisionAnalysisWorker(QThread):
    """抉择分析工作线程，用于在后台调用多模态API进行画面分析"""

    # 定义信号
    analysis_completed = pyqtSignal(str)  # 分析完成信号，传递分析结果
    analysis_failed = pyqtSignal(str)     # 分析失败信号，传递错误信息

    def __init__(self, pixmap: QPixmap, api_key: str, endpoint: str, model: str, decision_prompt: str):
        super().__init__()
        self.pixmap = pixmap
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.decision_prompt = decision_prompt

    def run(self):
        """在后台线程中执行抉择分析"""
        try:
            # 调用多模态API进行画面分析
            import base64
            from io import BytesIO
            from PyQt6.QtCore import QBuffer, QIODevice
            import requests

            # 将QPixmap转换为Base64字符串
            qbuffer = QBuffer()
            qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
            self.pixmap.save(qbuffer, "PNG")
            image_data = qbuffer.data().data()
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # 构造请求体
            request_body = {
                "model": self.model,
                "max_tokens": 1500,
                "messages": [
                    {
                        "role": "system",
                        "content": self.decision_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请分析这张游戏截图："
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

            # 构造请求头
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            # 发送HTTP请求
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=request_body,
                timeout=30
            )

            # 处理响应
            if response.status_code == 200:
                response_data = response.json()

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    message = response_data["choices"][0].get("message", {})
                    text_content = message.get("content", "")
                    self.analysis_completed.emit(text_content.strip() if text_content else "分析结果为空")
                else:
                    self.analysis_failed.emit("API返回格式异常，未找到分析内容")
            else:
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", {}).get("message", "未知错误")
                    self.analysis_failed.emit(f"API调用失败 (状态码: {response.status_code}): {error_message}")
                except:
                    self.analysis_failed.emit(f"API调用失败，状态码: {response.status_code}")

        except requests.exceptions.Timeout:
            self.analysis_failed.emit("API调用超时，请检查网络连接")
        except requests.exceptions.ConnectionError:
            self.analysis_failed.emit("网络连接错误，请检查API端点地址和网络状态")
        except Exception as e:
            self.analysis_failed.emit(f"画面分析过程中出现错误: {str(e)}")


class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()
        # 全局热键与截图重入控制
        self.is_capturing = False
        # 定义常量
        self.NO_CHARACTER_NOTICE = "暂无角色档案"

        self.init_directories()
        self.init_ui()
        self.load_character_list()

        # 初始化截图工具
        self.snipping_widget = None

        # 初始化OCR工作线程
        self.ocr_worker = None

        # 初始化抉择分析工作线程
        self.decision_worker = None

        # 初始化对话工作线程
        self.chat_worker = None

        # 加载API配置
        self.api_config = load_api_config()

        # 创建语音输入管理器
        self.voice_manager = VoiceInputManager(self.api_config)

        # 连接语音管理器的信号
        self.voice_manager.status_updated.connect(self.on_voice_status_updated)
        self.voice_manager.text_recognized.connect(self.insert_text_to_focused_widget)

        # 加载配置到UI (必须在UI创建之后)
        self.load_api_config_to_ui()

        # 初始化全局热键（Windows），保留原有局部快捷键作为备用
        # 延迟到事件循环启动后注册，更稳定
        QTimer.singleShot(0, self.setup_hotkeys)

    def closeEvent(self, event):
        """窗口关闭时自动保存配置并注销全局热键"""
        try:
            # 停止消息窗口热键监听线程
            if hasattr(self, 'hotkey_worker') and self.hotkey_worker and self.hotkey_worker.isRunning():
                try:
                    self.hotkey_worker.stop()
                except Exception:
                    pass
                self.hotkey_worker.wait(300)
            # 保存当前的API配置
            self.save_api_config()
        except Exception as e:
            print(f"保存配置时出错: {e}")
        finally:
            # 确保窗口正常关闭
            event.accept()

    def setup_hotkeys(self):
        """初始化全局热键（Windows），失败则继续使用窗口内快捷键。"""
        if sys.platform != "win32":
            print("非Windows平台，跳过全局热键。")
            return
        # 使用专用隐藏消息窗口监听 WM_HOTKEY（最稳定路径）
        try:
            self.hotkey_worker = WinHotkeyWorker()
            self.hotkey_worker.hotkey.connect(self.on_hotkey_triggered)
            self.hotkey_worker.start()
            print("全局热键监听已启动 (消息窗口)")
        except Exception as exc:
            print(f"全局热键监听启动失败: {exc}")

    def on_hotkey_triggered(self, hotkey_name: str):
        print(f"全局热键触发: {hotkey_name}")
        if hotkey_name == "ctrl+1":
            self.start_smart_screenshot()
        elif hotkey_name == "ctrl+2":
            self.capture_fullscreen_and_analyze()

    def show_message(self, title: str, text: str, icon: str = "information"):
        """显示消息弹窗（白底黑字）

        Args:
            title: 弹窗标题
            text: 弹窗内容
            icon: 图标类型 ("information", "warning", "critical", "question")

        Returns:
            对于question类型返回True/False，其他类型无返回值
        """
        msg = QMessageBox(self)

        # 设置图标
        if icon == "information":
            msg.setIcon(QMessageBox.Icon.Information)
        elif icon == "warning":
            msg.setIcon(QMessageBox.Icon.Warning)
        elif icon == "critical":
            msg.setIcon(QMessageBox.Icon.Critical)
        elif icon == "question":
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.No)

        msg.setWindowTitle(title)
        msg.setText(text)

        # 专门设置浅色主题样式
        msg.setStyleSheet("""
            QMessageBox {
                background-color: #EFEFEF;
                color: #000000;
            }
            QMessageBox QLabel {
                color: #000000;
                background-color: #EFEFEF;
            }
            QMessageBox QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
            QMessageBox QPushButton:hover {
                background-color: #F0F0F0;
            }
            QMessageBox QPushButton:pressed {
                background-color: #E0E0E0;
            }
        """)

        if icon == "question":
            return msg.exec() == QMessageBox.StandardButton.Yes
        else:
            msg.exec()

    def test_multimodal_connection(self):
        """测试多模态API连接"""
        # 从UI控件收集配置信息
        provider = self.multimodal_provider_combo.currentText()
        api_key = self.multimodal_api_key_edit.text().strip()
        endpoint = self.multimodal_endpoint_edit.text().strip()
        model = self.multimodal_model_edit.text().strip()

        if not api_key or not endpoint or not model:
            self.show_message("配置不完整", "请先填写多模态模型的API Key、端点和模型名称！", "warning")
            return

        self.test_multimodal_button.setText("测试中...")
        self.test_multimodal_button.setEnabled(False)

        try:
            # 调用api_service中的统一测试函数
            success, message = test_api_connectivity(provider, api_key, endpoint, model)

            if success:
                self.show_message("测试成功", message, "information")
            else:
                self.show_message("测试失败", f"多模态API测试失败：\n{message}", "warning")

        except Exception as e:
            self.show_message("测试失败", f"测试过程中出现错误：\n{str(e)}", "critical")
        finally:
            self.test_multimodal_button.setText("测试多模态连接")
            self.test_multimodal_button.setEnabled(True)

    def test_chat_connection(self):
        """测试对话API连接"""
        # 从UI控件收集配置信息
        provider = self.chat_provider_combo.currentText()
        api_key = self.chat_api_key_edit.text().strip()
        endpoint = self.chat_endpoint_edit.text().strip()
        model = self.chat_model_edit.text().strip()

        if not api_key or not endpoint or not model:
            self.show_message("配置不完整", "请先填写对话模型的API Key、端点和模型名称！", "warning")
            return

        self.test_chat_button.setText("测试中...")
        self.test_chat_button.setEnabled(False)

        try:
            # 调用api_service中的统一测试函数
            success, message = test_api_connectivity(provider, api_key, endpoint, model)

            if success:
                self.show_message("测试成功", message, "information")
            else:
                self.show_message("测试失败", f"对话API测试失败：\n{message}", "warning")

        except Exception as e:
            self.show_message("测试失败", f"测试过程中出现错误：\n{str(e)}", "critical")
        finally:
            self.test_chat_button.setText("测试对话连接")
            self.test_chat_button.setEnabled(True)

    def test_stt_connection(self):
        """测试语音识别API连接"""
        # 获取语音识别API配置
        stt_api_key = self.stt_api_key_edit.text().strip()

        if not stt_api_key:
            self.show_message("配置不完整", "请先填写语音识别API Key！", "warning")
            return

        self.test_stt_button.setText("测试中...")
        self.test_stt_button.setEnabled(False)

        try:
            # 调用api_service中的语音识别测试函数
            from api_service import test_stt_connectivity
            success, message = test_stt_connectivity(stt_api_key)

            if success:
                self.show_message("测试成功", message, "information")
            else:
                self.show_message("测试失败", f"语音识别API测试失败：\n{message}", "warning")

        except Exception as e:
            self.show_message("测试失败", f"测试过程中出现错误：\n{str(e)}", "critical")
        finally:
            self.test_stt_button.setText("测试语音识别")
            self.test_stt_button.setEnabled(True)

    def build_polish_prompt(self, ocr_result: str, user_context: str) -> list:
        """构建内容整合润色的Prompt消息列表"""
        prompt_template = """# 角色与任务
你是一位严谨的助理，负责整理对话记录。你的任务是经过思考后，将【原始对话】和【背景补充】两部分信息，整合成一段或数段通顺、连贯、适合存档的文本。
**重要原则：** 【原始对话】内容来自截图，是绝对准确的基准。【背景补充】可能来自语音输入，其中或许存在错别字。你在整合时，必须以【原始对话】的上下文为准，去理解和修正【背景补充】中可能不通顺或错误的地方，最终输出一段完美的记录。请不要进行分析、评价或添加任何原始信息之外的内容。

---
# 原始对话 (可能包含画面场景)
{ocr_result_text}

---
# 背景补充 (由用户提供)
{user_context_text}

---
# 整合后的记录文本："""

        # 填充模板
        filled_prompt = prompt_template.format(
            ocr_result_text=ocr_result.strip() if ocr_result else "无",
            user_context_text=user_context.strip() if user_context else "无"
        )

        # 构建消息列表
        messages = [
            {
                "role": "user",
                "content": filled_prompt
            }
        ]

        return messages

    def run_content_polish(self):
        """运行内容整合润色"""
        try:
            # 获取输入内容
            ocr_result = self.ocr_result_text.toPlainText().strip()
            user_context = self.user_context_text.toPlainText().strip()

            # 验证输入
            if not ocr_result and not user_context:
                # 使用整合润色状态标签显示错误
                self.polish_status_label.setText("❌ 内容为空")
                self.polish_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.polish_status_label.setText(""))
                return

            # 检查对话API配置
            chat_provider = self.api_config.get("chat_provider", "硅基流动")
            provider_key = self.get_provider_key(chat_provider)
            provider_config = self.api_config.get(provider_key, {})

            api_key = provider_config.get("chat_api_key", "")
            model = provider_config.get("chat_model", "")

            # 获取端点
            if provider_key == "custom":
                endpoint = provider_config.get("chat_endpoint", "")
            elif chat_provider == "硅基流动":
                endpoint = "https://api.siliconflow.cn/v1/chat/completions"
            elif chat_provider == "豆包":
                endpoint = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
            else:
                endpoint = ""

            if not api_key or not endpoint or not model:
                # 使用整合润色状态标签显示错误
                self.polish_status_label.setText("❌ API配置不完整")
                self.polish_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(4000, lambda: self.polish_status_label.setText(""))
                return

            # 显示处理中状态
            self.polished_content_text.setPlainText("🔄 正在整合润色中，请稍候...")
            self.run_polish_button.setText("处理中...")
            self.run_polish_button.setEnabled(False)

            # 停止之前的对话任务（如果存在）
            if self.chat_worker and self.chat_worker.isRunning():
                self.chat_worker.terminate()
                self.chat_worker.wait()

            # 构建Prompt消息
            messages = self.build_polish_prompt(ocr_result, user_context)

            # 创建并启动对话工作线程
            self.chat_worker = ChatWorker(messages, api_key, endpoint, model)
            self.chat_worker.chat_completed.connect(self.on_polish_completed)
            self.chat_worker.chat_failed.connect(self.on_polish_failed)
            self.chat_worker.start()

        except Exception as e:
            # 使用整合润色状态标签显示错误
            self.polish_status_label.setText("❌ 处理失败")
            self.polish_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
            QTimer.singleShot(5000, lambda: self.polish_status_label.setText(""))

            # 恢复按钮状态
            self.run_polish_button.setText("🔄 整合润色")
            self.run_polish_button.setEnabled(True)

    def on_polish_completed(self, result: str):
        """内容整合完成的回调"""
        # 显示处理结果
        self.polished_content_text.setPlainText(result)

        # 恢复按钮状态
        self.run_polish_button.setText("🔄 整合润色")
        self.run_polish_button.setEnabled(True)

        # 显示内联状态反馈
        self.polish_status_label.setText(f"✅ 整合完成，生成 {len(result)} 个字符")
        self.polish_status_label.setStyleSheet("color: #4CAF50; margin-left: 10px;")

        # 3秒后自动消失
        QTimer.singleShot(3000, lambda: self.polish_status_label.setText(""))

    def on_polish_failed(self, error_message: str):
        """内容整合失败的回调"""
        # 显示错误信息
        self.polished_content_text.setPlainText(f"❌ 整合失败: {error_message}")

        # 恢复按钮状态
        self.run_polish_button.setText("🔄 整合润色")
        self.run_polish_button.setEnabled(True)

        # 显示内联状态反馈
        self.polish_status_label.setText("❌ 整合失败")
        self.polish_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")

        # 5秒后自动消失
        QTimer.singleShot(5000, lambda: self.polish_status_label.setText(""))

    def record_to_character_dossier(self):
        """将整理后内容记录到角色档案"""
        try:
            # 获取要记录的内容
            content_to_record = self.polished_content_text.toPlainText().strip()

            if not content_to_record:
                # 显示内联状态反馈
                self.record_status_label.setText("❌ 内容为空")
                self.record_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.record_status_label.setText(""))
                return

            # 检查内容是否为错误信息
            if content_to_record.startswith(("❌ 整合失败", "🔄 正在整合润色中")):
                # 显示内联状态反馈
                self.record_status_label.setText("❌ 内容无效")
                self.record_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.record_status_label.setText(""))
                return

            # 获取选中的角色
            selected_character = self.record_character_combo.currentText()

            if not selected_character or selected_character == self.NO_CHARACTER_NOTICE:
                # 显示内联状态反馈
                self.record_status_label.setText("❌ 未选择角色")
                self.record_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.record_status_label.setText(""))
                return

            # 构建要追加的内容（添加时间戳）
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record_content = f"\n\n## 记录时间: {timestamp}\n\n{content_to_record}\n"

            # 直接记录，不再弹窗确认
            # 构建文件路径
            file_path = os.path.join(self.characters_dir, f"{selected_character}.md")

            # 追加内容到文件
            with open(file_path, 'a', encoding='utf-8') as file:
                file.write(record_content)

            # 显示内联状态反馈
            self.record_status_label.setText(f"✅ 已记录到「{selected_character}」档案")
            self.record_status_label.setStyleSheet("color: #4CAF50; margin-left: 10px;")
            QTimer.singleShot(4000, lambda: self.record_status_label.setText(""))

            # **任务二：实现自动同步刷新**
            # 获取当前"角色档案"标签页中正在显示的角色名
            current_viewing_character = self.character_combo.currentText()

            # 判断是否为同一个角色
            if selected_character == current_viewing_character:
                # 如果相同，强制刷新角色档案视图
                self.on_character_changed(selected_character)

            # 自动清空内容，为下次使用做准备
            self.polished_content_text.clear()
            self.ocr_result_text.clear()
            self.user_context_text.clear()

        except Exception as e:
            # 显示内联状态反馈
            self.record_status_label.setText("❌ 记录失败")
            self.record_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
            QTimer.singleShot(5000, lambda: self.record_status_label.setText(""))

    def init_directories(self):
        """初始化目录结构"""
        # 创建 characters 文件夹
        self.characters_dir = "characters"
        if not os.path.exists(self.characters_dir):
            os.makedirs(self.characters_dir)
            print(f"创建 {self.characters_dir} 文件夹")

    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口基本属性
        self.setWindowTitle("互动游戏AI狗头军师")
        self.setGeometry(100, 100, 1200, 800)

        # 创建主布局
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # 创建顶部工具栏
        self.create_top_toolbar()
        main_layout.addWidget(self.top_toolbar)

        # 创建中心部件 - 标签页组件
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # 创建四个标签页
        self.create_quick_notes_tab()
        self.create_decision_assistance_tab()
        self.create_character_profiles_tab()
        self.create_api_settings_tab()

        # 设置窗口样式（深色主题）
        self.set_dark_theme()

        # 创建快捷键
        self.create_shortcuts()

    def create_shortcuts(self):
        """创建应用程序级别的快捷键"""
        # 创建 Ctrl+2 快捷键
        self.fullscreen_shortcut = QShortcut(QKeySequence("Ctrl+2"), self)
        # 连接快捷键的 activated 信号到新的截图方法
        self.fullscreen_shortcut.activated.connect(self.capture_fullscreen_and_analyze)

    def create_top_toolbar(self):
        """创建顶部工具栏"""
        self.top_toolbar = QWidget()
        self.top_toolbar.setMaximumHeight(50)
        toolbar_layout = QHBoxLayout(self.top_toolbar)

        # 左侧占位
        toolbar_layout.addStretch()

        # 截图功能区域
        screenshot_widget = QWidget()
        screenshot_layout = QHBoxLayout(screenshot_widget)
        screenshot_layout.setContentsMargins(0, 0, 0, 0)

        # 截图按钮
        self.screenshot_button = QPushButton()
        self.screenshot_button.setIcon(QIcon("assets/icons/screenshot.png"))
        self.screenshot_button.setIconSize(QSize(20, 20))
        self.screenshot_button.setFixedSize(40, 30)
        self.screenshot_button.setShortcut("Ctrl+1")  # 恢复快捷键
        self.screenshot_button.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                border: 2px solid #666666;
                border-radius: 6px;
                background-color: #4a4a4a;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
                border-color: #2196F3;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
        """)
        self.screenshot_button.setToolTip("智能截图 (Ctrl+1)")
        self.screenshot_button.clicked.connect(self.start_smart_screenshot)
        screenshot_layout.addWidget(self.screenshot_button)

        toolbar_layout.addWidget(screenshot_widget)

        # 截图和语音功能之间的间距
        toolbar_layout.addSpacing(15)

        # 语音功能区域
        voice_widget = QWidget()
        voice_layout = QHBoxLayout(voice_widget)
        voice_layout.setContentsMargins(0, 0, 0, 0)

        # 语音开关按钮
        self.voice_toggle_button = QPushButton()
        self.voice_toggle_button.setIcon(QIcon("assets/icons/microphone.png"))
        self.voice_toggle_button.setIconSize(QSize(20, 20))
        self.voice_toggle_button.setCheckable(True)
        self.voice_toggle_button.setFixedSize(40, 30)
        self.voice_toggle_button.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                border: 2px solid #666666;
                border-radius: 6px;
                background-color: #4a4a4a;
            }
            QPushButton:checked {
                background-color: #4CAF50;
                border-color: #4CAF50;
            }
        """)
        self.voice_toggle_button.clicked.connect(self.toggle_voice_function)
        voice_layout.addWidget(self.voice_toggle_button)

        # 语音状态标签
        self.voice_status_label = QLabel("语音功能关闭")
        self.voice_status_label.setStyleSheet("color: #888888; margin-left: 8px; font-size: 12px;")
        voice_layout.addWidget(self.voice_status_label)

        toolbar_layout.addWidget(voice_widget)

        # 右侧间距
        toolbar_layout.addSpacing(20)

    def create_quick_notes_tab(self):
        """创建速记与整理台标签页"""
        quick_notes_widget = QWidget()
        layout = QVBoxLayout()

        # 标题
        title_label = QLabel("速记与整理台")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # OCR结果显示区域
        ocr_header_layout = QHBoxLayout()

        ocr_label = QLabel("📸 截图识别结果 (Ctrl+1 框选截图 | Ctrl+2 全屏截图)")
        ocr_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        ocr_label.setStyleSheet("color: #4CAF50; margin-top: 10px;")
        ocr_header_layout.addWidget(ocr_label)

        # OCR状态标签
        self.ocr_status_label = QLabel("")
        self.ocr_status_label.setFont(QFont("Microsoft YaHei", 9))
        self.ocr_status_label.setStyleSheet("color: #888888; margin-left: 10px; margin-top: 10px;")
        ocr_header_layout.addWidget(self.ocr_status_label)

        ocr_header_layout.addStretch()
        layout.addLayout(ocr_header_layout)

        self.ocr_result_text = QTextEdit()
        self.ocr_result_text.setObjectName("ocr_result_text")
        self.ocr_result_text.setPlaceholderText("截图识别出的文字将显示在这里...\n\n使用快捷键 Ctrl+1 或菜单中的「截图识别」开始截图。")
        self.ocr_result_text.setMaximumHeight(150)  # 限制高度
        layout.addWidget(self.ocr_result_text)

        # 用户补充信息区域
        context_label = QLabel("📝 补充信息/背景")
        context_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        context_label.setStyleSheet("color: #2196F3; margin-top: 10px;")
        layout.addWidget(context_label)

        self.user_context_text = QTextEdit()
        self.user_context_text.setObjectName("user_context_text")
        self.user_context_text.setPlaceholderText("请在此处添加对上述OCR内容的背景说明、上下文信息或任何补充描述...\n\n例如：\n• 说话的角色身份\n• 对话发生的场景\n• 需要重点关注的内容\n• 其他有助于理解的信息")
        self.user_context_text.setMaximumHeight(120)  # 限制高度
        layout.addWidget(self.user_context_text)

        # 整合润色按钮和状态标签
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.run_polish_button = QPushButton("🔄 整合润色")
        self.run_polish_button.setObjectName("run_polish_button")
        self.run_polish_button.clicked.connect(self.run_content_polish)
        self.run_polish_button.setMinimumHeight(35)
        self.run_polish_button.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        button_layout.addWidget(self.run_polish_button)

        # 整合润色状态标签
        self.polish_status_label = QLabel("")
        self.polish_status_label.setStyleSheet("color: #888888; margin-left: 10px;")
        self.polish_status_label.setFont(QFont("Microsoft YaHei", 9))
        button_layout.addWidget(self.polish_status_label)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # 整理后内容显示区域
        result_label = QLabel("✨ 整理后内容")
        result_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        result_label.setStyleSheet("color: #FF9800; margin-top: 10px;")
        layout.addWidget(result_label)

        self.polished_content_text = QTextEdit()
        self.polished_content_text.setObjectName("polished_content_text")
        self.polished_content_text.setPlaceholderText("AI整合润色后的内容将显示在这里...\n\n点击上方的「整合润色」按钮开始处理。")
        layout.addWidget(self.polished_content_text)

        # 记录到档案区域
        record_layout = QHBoxLayout()
        record_layout.addWidget(QLabel("记录到角色档案:"))

        self.record_character_combo = QComboBox()
        self.record_character_combo.setObjectName("record_character_combo")
        record_layout.addWidget(self.record_character_combo)

        self.record_to_dossier_button = QPushButton("📋 记录到档案")
        self.record_to_dossier_button.setObjectName("record_to_dossier_button")
        self.record_to_dossier_button.clicked.connect(self.record_to_character_dossier)
        record_layout.addWidget(self.record_to_dossier_button)

        # 记录到档案状态标签
        self.record_status_label = QLabel("")
        self.record_status_label.setStyleSheet("color: #888888; margin-left: 10px;")
        self.record_status_label.setFont(QFont("Microsoft YaHei", 9))
        record_layout.addWidget(self.record_status_label)

        record_layout.addStretch()
        layout.addLayout(record_layout)

        quick_notes_widget.setLayout(layout)
        self.tab_widget.addTab(quick_notes_widget, "速记与整理台")

    def create_decision_assistance_tab(self):
        """创建抉择辅助标签页"""
        decision_widget = QWidget()
        layout = QVBoxLayout()

        # 标题
        title_label = QLabel("游戏抉择辅助")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 画面分析结果区域
        analysis_label = QLabel("🖼️ 当前游戏画面分析 (Ctrl+1 框选截图 | Ctrl+2 全屏截图)")
        analysis_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        analysis_label.setStyleSheet("color: #4CAF50; margin-top: 10px;")
        layout.addWidget(analysis_label)

        self.game_analysis_text = QTextEdit()
        self.game_analysis_text.setObjectName("game_analysis_text")
        self.game_analysis_text.setPlaceholderText("截图或手动输入当前游戏画面情景...\n\n这里可以是:\n• 游戏中的对话内容\n• 场景描述\n• 需要做出选择的具体情况\n• 任何你想让AI军师了解的背景信息")
        self.game_analysis_text.setMaximumHeight(150)
        layout.addWidget(self.game_analysis_text)

        # 角色选择区域
        characters_label = QLabel("👥 角色设定")
        characters_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        characters_label.setStyleSheet("color: #2196F3; margin-top: 15px;")
        layout.addWidget(characters_label)

        # 角色选择布局
        char_layout = QGridLayout()

        # 提问者
        char_layout.addWidget(QLabel("提问者:"), 0, 0)
        self.questioner_combo = QComboBox()
        self.questioner_combo.setObjectName("questioner_combo")
        char_layout.addWidget(self.questioner_combo, 0, 1)

        # 相关人1
        char_layout.addWidget(QLabel("相关人1:"), 0, 2)
        self.related_person1_combo = QComboBox()
        self.related_person1_combo.setObjectName("related_person1_combo")
        char_layout.addWidget(self.related_person1_combo, 0, 3)

        # 相关人2
        char_layout.addWidget(QLabel("相关人2:"), 1, 0)
        self.related_person2_combo = QComboBox()
        self.related_person2_combo.setObjectName("related_person2_combo")
        char_layout.addWidget(self.related_person2_combo, 1, 1)

        # 相关人3
        char_layout.addWidget(QLabel("相关人3:"), 1, 2)
        self.related_person3_combo = QComboBox()
        self.related_person3_combo.setObjectName("related_person3_combo")
        char_layout.addWidget(self.related_person3_combo, 1, 3)

        layout.addLayout(char_layout)

        # 补充说明区域
        supplement_label = QLabel("📝 补充说明")
        supplement_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        supplement_label.setStyleSheet("color: #FF9800; margin-top: 15px;")
        layout.addWidget(supplement_label)

        self.supplement_text = QTextEdit()
        self.supplement_text.setObjectName("supplement_text")
        self.supplement_text.setPlaceholderText("在此处添加任何额外的背景信息、具体问题或特殊要求...\n\n例如:\n• 当前的游戏进度\n• 角色之间的特殊关系\n• 你希望AI重点考虑的因素\n• 具体的抉择问题")
        self.supplement_text.setMaximumHeight(120)
        layout.addWidget(self.supplement_text)

        # 获取建议按钮和状态区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.get_advice_button = QPushButton("🚀 获取抉择建议")
        self.get_advice_button.setObjectName("get_advice_button")
        self.get_advice_button.clicked.connect(self.get_decision_advice)
        self.get_advice_button.setMinimumHeight(40)
        self.get_advice_button.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        button_layout.addWidget(self.get_advice_button)

        # 状态指示器
        self.advice_status_label = QLabel("")
        self.advice_status_label.setStyleSheet("color: #888888; margin-left: 10px;")
        self.advice_status_label.setFont(QFont("Microsoft YaHei", 9))
        button_layout.addWidget(self.advice_status_label)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # AI分析结果显示区域
        result_label = QLabel("🎯 AI军师分析结果")
        result_label.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        result_label.setStyleSheet("color: #9C27B0; margin-top: 15px;")
        layout.addWidget(result_label)

        self.advice_result_text = QTextEdit()
        self.advice_result_text.setObjectName("advice_result_text")
        self.advice_result_text.setPlaceholderText("AI军师的抉择建议将显示在这里...\n\n点击上方的「获取抉择建议」按钮开始分析。")
        self.advice_result_text.setReadOnly(True)  # 设置为只读
        layout.addWidget(self.advice_result_text)

        # 添加弹性空间
        layout.addStretch()

        decision_widget.setLayout(layout)
        self.tab_widget.addTab(decision_widget, "抉择辅助")

    def get_decision_advice(self):
        """获取抉择建议的核心方法"""
        try:
            # 第一步：数据收集
            game_analysis = self.game_analysis_text.toPlainText().strip()
            supplement = self.supplement_text.toPlainText().strip()
            questioner = self.questioner_combo.currentText()
            related1 = self.related_person1_combo.currentText()
            related2 = self.related_person2_combo.currentText()
            related3 = self.related_person3_combo.currentText()

            # 数据验证
            if not game_analysis and not supplement:
                self.advice_status_label.setText("❌ 请输入游戏画面分析或补充说明")
                self.advice_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.advice_status_label.setText(""))
                return

            if not questioner or questioner == self.NO_CHARACTER_NOTICE:
                self.advice_status_label.setText("❌ 请选择提问者角色")
                self.advice_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(3000, lambda: self.advice_status_label.setText(""))
                return

            # 第二步：档案读取
            character_profiles = {}

            # 读取提问者档案
            questioner_file = os.path.join(self.characters_dir, f"{questioner}.md")
            if os.path.exists(questioner_file):
                with open(questioner_file, 'r', encoding='utf-8') as f:
                    character_profiles[questioner] = f.read()
            else:
                character_profiles[questioner] = "档案内容为空"

            # 读取相关人档案
            related_characters = []
            for related_person in [related1, related2, related3]:
                if related_person and related_person != "无" and related_person != self.NO_CHARACTER_NOTICE:
                    related_characters.append(related_person)
                    related_file = os.path.join(self.characters_dir, f"{related_person}.md")
                    if os.path.exists(related_file):
                        with open(related_file, 'r', encoding='utf-8') as f:
                            character_profiles[related_person] = f.read()
                    else:
                        character_profiles[related_person] = "档案内容为空"

            # 第三步：Prompt构建
            messages = self.build_decision_prompt(
                game_analysis, supplement, questioner,
                related_characters, character_profiles
            )

            # 第四步：检查对话API配置
            chat_provider = self.api_config.get("chat_provider", "硅基流动")
            provider_key = self.get_provider_key(chat_provider)
            provider_config = self.api_config.get(provider_key, {})

            api_key = provider_config.get("chat_api_key", "")
            model = provider_config.get("chat_model", "")

            # 获取端点
            if provider_key == "custom":
                endpoint = provider_config.get("chat_endpoint", "")
            elif chat_provider == "硅基流动":
                endpoint = "https://api.siliconflow.cn/v1/chat/completions"
            elif chat_provider == "豆包":
                endpoint = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
            else:
                endpoint = ""

            if not api_key or not endpoint or not model:
                self.advice_status_label.setText("❌ 对话API配置不完整")
                self.advice_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
                QTimer.singleShot(4000, lambda: self.advice_status_label.setText(""))
                return

            # 第五步：显示处理中状态并禁用按钮
            self.get_advice_button.setText("🧠 AI军师思考中...")
            self.get_advice_button.setEnabled(False)
            self.advice_status_label.setText("🧠 AI军师思考中...")
            self.advice_status_label.setStyleSheet("color: #FF9800; margin-left: 10px;")

            # 停止之前的对话任务（如果存在）
            if hasattr(self, 'advice_worker') and self.advice_worker and self.advice_worker.isRunning():
                self.advice_worker.terminate()
                self.advice_worker.wait()

            # 第六步：创建并启动AI工作线程
            self.advice_worker = ChatWorker(messages, api_key, endpoint, model)
            self.advice_worker.chat_completed.connect(self.on_advice_completed)
            self.advice_worker.chat_failed.connect(self.on_advice_failed)
            self.advice_worker.start()

        except Exception as e:
            self.advice_status_label.setText("❌ 处理失败")
            self.advice_status_label.setStyleSheet("color: #F44336; margin-left: 10px;")
            QTimer.singleShot(5000, lambda: self.advice_status_label.setText(""))

            # 恢复按钮状态
            self.get_advice_button.setText("🚀 获取抉择建议")
            self.get_advice_button.setEnabled(True)

    def build_decision_prompt(self, game_analysis, supplement, questioner, related_characters, character_profiles):
        """构建游戏抉择建议的Prompt消息列表（最终战略版）"""

        # 最终版Prompt模板，融合了需求文档的结构和用户最新的优化要求
        prompt_template = """# 身份与任务
你是一位顶级的互动游戏剧情分析师与心理侧写专家。你的核心任务是基于我提供的全部信息，进行滴水不漏的逻辑推理，预测每个选项可能带来的短期和长期后果，并为我推荐一个最符合长远利益的最佳选项。
**特别注意：** 以下"关键人物背景档案"是玩家在不同时间点记录的"印象笔记"，其中可能包含玩家主观的、甚至是前后矛盾的判断。记录中的时间戳（如有）非常关键，越晚的记录越能反映玩家当前的认知。你在分析时，必须像一位真正的侦探一样，考虑到这些记录的时效性和潜在的认知偏差，而不是将所有内容都当成绝对事实。

---
## 第一部分：当前游戏画面情景分析
{multimodal_result_text}

---
## 第二部分：关键人物背景档案

### 提问者
* **角色名**: {questioner_name}
* **此人全部已知信息与历史言行记录**:
{questioner_dossier_content}
{related_profiles_section}
---
## 第三部分：我的补充说明
{additional_context_text}

---
## 第四部分：你的分析任务
请严格按照以下结构进行分析和输出：

1.  **当前局势分析**: 结合画面、提问者和相关人，一句话总结当前的核心矛盾或抉择点是什么。
2.  **人物动机判断**: 结合档案中带有时间戳的记录，分析各相关角色的可能想法、情感状态和动机。如果档案中出现了前后矛盾的描述，请特别指出，并优先采信时间点更靠后的记录进行分析。
    * **提问者 ({questioner_name})**:
    * **相关人**:
3.  **选项后果推演**: (假设游戏选项已在画面分析中被识别)
    * **【选项A: 文字内容】**:
        * **短期后果**:
        * **长期影响**:
        * **风险评估**: (极高/高/中/低/安全)
    * **【选项B: 文字内容】**:
        * ... (重复以上结构)
4.  **【最终建议】**
    * **推荐选项**: 我建议你选择 **【选项X】**。
    * **核心理由**: """

        # 处理游戏情景分析部分
        if game_analysis and supplement:
            multimodal_result_text = f"{game_analysis}\n\n{supplement}"
        elif game_analysis:
            multimodal_result_text = game_analysis
        elif supplement:
            multimodal_result_text = supplement
        else:
            multimodal_result_text = "（暂无具体画面分析）"

        # 处理提问者档案
        questioner_dossier = character_profiles.get(questioner, "暂无此人的档案信息")

        # 处理相关人档案部分
        related_profiles_section = ""
        if related_characters:
            related_profiles_section = "\n### 相关人物\n"
            for char_name in related_characters:
                char_profile = character_profiles.get(char_name, "暂无此人的档案信息")
                related_profiles_section += f"* **{char_name}**:\n{char_profile}\n\n"
        else:
            related_profiles_section = "\n### 相关人物\n暂无相关人物档案"

        # 处理补充说明
        additional_context = supplement if supplement else "（暂无补充说明）"

        # 构建最终Prompt
        filled_prompt = prompt_template.format(
            multimodal_result_text=multimodal_result_text,
            questioner_name=questioner,
            questioner_dossier_content=questioner_dossier,
            related_profiles_section=related_profiles_section,
            additional_context_text=additional_context
        )

        # 构建消息列表
        messages = [
            {
                "role": "user",
                "content": filled_prompt
            }
        ]

        return messages

    def build_decision_image_prompt(self):
        """构建抉择辅助专用的画面分析Prompt - 只分析画面不提取文字"""
        decision_prompt = (
            "你是一位专业的游戏场景分析师，正在协助玩家进行游戏抉择。"
            "请仔细观察这张游戏截图，专注于分析画面中的情境、角色状态、环境氛围等要素，"
            "为后续的抉择建议提供基础信息。\n\n"
            "请按照以下要求进行分析：\n"
            "1. 描述当前场景：地点、环境、氛围等\n"
            "2. 分析角色状态：表情、动作、服装、位置关系等\n"
            "3. 识别关键线索：任何可能影响抉择的重要细节\n"
            "4. 评估整体情况：当前情境的紧张程度、重要性等\n\n"
            "请用客观、详细的语言进行描述，为AI军师的后续分析提供充分的画面信息。"
            "注意：专注于画面分析，无需提取或转录任何文字内容。"
        )
        return decision_prompt

    def on_advice_completed(self, advice_result: str):
        """抉择建议完成的回调"""
        # 恢复按钮状态
        self.get_advice_button.setText("🚀 获取抉择建议")
        self.get_advice_button.setEnabled(True)
        self.advice_status_label.setText("")

        # 将结果显示在文本框中
        self.advice_result_text.setPlainText(advice_result)

    def on_advice_failed(self, error_message: str):
        """抉择建议失败的回调"""
        # 恢复按钮状态
        self.get_advice_button.setText("🚀 获取抉择建议")
        self.get_advice_button.setEnabled(True)
        self.advice_status_label.setText("")

        # 在结果框中显示错误信息
        self.advice_result_text.setPlainText(f"❌ 获取抉择建议失败：\n\n{error_message}")

    def on_decision_analysis_completed(self, analysis_result: str):
        """抉择辅助画面分析完成的回调"""
        # 将分析结果填入游戏画面分析文本框
        self.game_analysis_text.setPlainText(analysis_result)

        # 显示成功状态（如果需要的话，可以添加状态提示）
        print(f"抉择辅助画面分析完成，结果长度: {len(analysis_result)} 字符")

    def on_decision_analysis_failed(self, error_message: str):
        """抉择辅助画面分析失败的回调"""
        # 在游戏画面分析文本框中显示错误信息
        self.game_analysis_text.setPlainText(f"❌ 画面分析失败：\n\n{error_message}")

    def create_character_profiles_tab(self):
        """创建角色档案标签页"""
        character_widget = QWidget()
        layout = QVBoxLayout()

        # 创建顶部控制区域
        top_layout = QHBoxLayout()

        # 角色选择下拉框
        self.character_combo = QComboBox()
        self.character_combo.setObjectName("character_combo")
        self.character_combo.currentTextChanged.connect(self.on_character_changed)
        top_layout.addWidget(QLabel("选择角色:"))
        top_layout.addWidget(self.character_combo)

        # 创建新角色按钮
        self.create_character_button = QPushButton("创建新角色")
        self.create_character_button.setObjectName("create_character_button")
        self.create_character_button.clicked.connect(self.create_new_character)
        top_layout.addWidget(self.create_character_button)

        # 添加弹性空间
        top_layout.addStretch()

        layout.addLayout(top_layout)

        # 档案内容编辑区域
        self.dossier_text_edit = QTextEdit()
        self.dossier_text_edit.setObjectName("dossier_text_edit")
        self.dossier_text_edit.setPlaceholderText("请选择一个角色查看档案内容，或创建新角色...")
        layout.addWidget(self.dossier_text_edit)

        # 保存按钮
        self.save_dossier_button = QPushButton("保存当前修改")
        self.save_dossier_button.setObjectName("save_dossier_button")
        self.save_dossier_button.clicked.connect(self.save_current_dossier)
        layout.addWidget(self.save_dossier_button)

        character_widget.setLayout(layout)
        self.tab_widget.addTab(character_widget, "角色档案")

    def create_api_settings_tab(self):
        """创建API设置标签页"""
        api_widget = QWidget()
        layout = QVBoxLayout()

        # 创建标题
        title_label = QLabel("AI模型API配置")
        title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 创建配置表单
        form_layout = QGridLayout()

        # 多模态模型API配置
        multimodal_title = QLabel("多模态模型API (用于图像识别)")
        multimodal_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        multimodal_title.setStyleSheet("color: #4CAF50; margin-top: 10px;")
        form_layout.addWidget(multimodal_title, 0, 0, 1, 3)

        # 多模态提供商选择
        form_layout.addWidget(QLabel("提供商:"), 1, 0)
        self.multimodal_provider_combo = QComboBox()
        self.multimodal_provider_combo.setObjectName("multimodal_provider_combo")
        self.multimodal_provider_combo.addItems(["硅基流动", "豆包", "自定义"])
        self.multimodal_provider_combo.currentTextChanged.connect(self.on_multimodal_provider_changed)
        form_layout.addWidget(self.multimodal_provider_combo, 1, 1, 1, 2)

        form_layout.addWidget(QLabel("API Key:"), 2, 0)
        self.multimodal_api_key_edit = QLineEdit()
        self.multimodal_api_key_edit.setObjectName("multimodal_api_key_edit")
        self.multimodal_api_key_edit.setPlaceholderText("请输入多模态模型的API Key...")
        self.multimodal_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.multimodal_api_key_edit, 2, 1, 1, 2)

        form_layout.addWidget(QLabel("API端点:"), 3, 0)
        self.multimodal_endpoint_edit = QLineEdit()
        self.multimodal_endpoint_edit.setObjectName("multimodal_endpoint_edit")
        self.multimodal_endpoint_edit.setPlaceholderText("多模态模型API端点...")
        form_layout.addWidget(self.multimodal_endpoint_edit, 3, 1, 1, 2)

        form_layout.addWidget(QLabel("模型名称:"), 4, 0)
        self.multimodal_model_edit = QLineEdit()
        self.multimodal_model_edit.setObjectName("multimodal_model_edit")
        self.multimodal_model_edit.setPlaceholderText("多模态模型名称...")
        form_layout.addWidget(self.multimodal_model_edit, 4, 1, 1, 2)

        # 对话模型API配置
        chat_title = QLabel("对话模型API (用于文本处理和游戏分析)")
        chat_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        chat_title.setStyleSheet("color: #2196F3; margin-top: 20px;")
        form_layout.addWidget(chat_title, 5, 0, 1, 3)

        # 对话提供商选择
        form_layout.addWidget(QLabel("提供商:"), 6, 0)
        self.chat_provider_combo = QComboBox()
        self.chat_provider_combo.setObjectName("chat_provider_combo")
        self.chat_provider_combo.addItems(["硅基流动", "豆包", "自定义"])
        self.chat_provider_combo.currentTextChanged.connect(self.on_chat_provider_changed)
        form_layout.addWidget(self.chat_provider_combo, 6, 1, 1, 2)

        form_layout.addWidget(QLabel("API Key:"), 7, 0)
        self.chat_api_key_edit = QLineEdit()
        self.chat_api_key_edit.setObjectName("chat_api_key_edit")
        self.chat_api_key_edit.setPlaceholderText("请输入对话模型的API Key...")
        self.chat_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.chat_api_key_edit, 7, 1, 1, 2)

        form_layout.addWidget(QLabel("API端点:"), 8, 0)
        self.chat_endpoint_edit = QLineEdit()
        self.chat_endpoint_edit.setObjectName("chat_endpoint_edit")
        self.chat_endpoint_edit.setPlaceholderText("对话模型API端点...")
        form_layout.addWidget(self.chat_endpoint_edit, 8, 1, 1, 2)

        form_layout.addWidget(QLabel("模型名称:"), 9, 0)
        self.chat_model_edit = QLineEdit()
        self.chat_model_edit.setObjectName("chat_model_edit")
        self.chat_model_edit.setPlaceholderText("对话模型名称...")
        form_layout.addWidget(self.chat_model_edit, 9, 1, 1, 2)

        # 语音识别API配置区域
        stt_title = QLabel("语音识别API (用于语音输入)")
        stt_title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        stt_title.setStyleSheet("color: #9C27B0; margin-top: 20px;")
        form_layout.addWidget(stt_title, 10, 0, 1, 3)

        # 提供商说明
        form_layout.addWidget(QLabel("提供商:"), 11, 0)
        stt_provider_label = QLabel("硅基流动 (固定)")
        stt_provider_label.setStyleSheet("color: #666666; font-size: 10px;")
        form_layout.addWidget(stt_provider_label, 11, 1, 1, 2)

        # API Key输入
        form_layout.addWidget(QLabel("API Key:"), 12, 0)
        self.stt_api_key_edit = QLineEdit()
        self.stt_api_key_edit.setObjectName("stt_api_key_edit")
        self.stt_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.stt_api_key_edit.setPlaceholderText("请输入硅基流动API Key...")
        form_layout.addWidget(self.stt_api_key_edit, 12, 1, 1, 2)

        # 注册链接
        stt_link_label = QLabel('<a href="https://cloud.siliconflow.cn/i/My0p5Jgs" style="color: #2196F3;">点击注册硅基流动账号</a>')
        stt_link_label.setOpenExternalLinks(True)
        stt_link_label.setStyleSheet("margin-bottom: 10px;")
        form_layout.addWidget(stt_link_label, 13, 1, 1, 2)

        layout.addLayout(form_layout)

        # 添加说明文字
        help_text = QLabel("""
配置说明：
• 多模态模型：用于处理截图识别和游戏画面分析
• 对话模型：用于内容整合润色和游戏抉择建议
• 语音识别：用于语音转文字输入功能
• 可以分别选择不同的提供商，也可以使用同一个
• 所有字段都可以手动编辑和调整""")
        help_text.setStyleSheet("color: #888888; margin: 10px; padding: 10px; background-color: #3c3c3c; border-radius: 5px;")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        # 添加弹性空间
        layout.addStretch()

        # 创建按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 测试多模态连接按钮
        self.test_multimodal_button = QPushButton("测试多模态连接")
        self.test_multimodal_button.setObjectName("test_multimodal_button")
        self.test_multimodal_button.clicked.connect(self.test_multimodal_connection)
        button_layout.addWidget(self.test_multimodal_button)

        # 测试对话连接按钮
        self.test_chat_button = QPushButton("测试对话连接")
        self.test_chat_button.setObjectName("test_chat_button")
        self.test_chat_button.clicked.connect(self.test_chat_connection)
        button_layout.addWidget(self.test_chat_button)

        # 测试语音识别按钮
        self.test_stt_button = QPushButton("测试语音识别")
        self.test_stt_button.setObjectName("test_stt_button")
        self.test_stt_button.clicked.connect(self.test_stt_connection)
        button_layout.addWidget(self.test_stt_button)

        # 保存配置按钮
        self.save_config_button = QPushButton("保存配置")
        self.save_config_button.setObjectName("save_config_button")
        self.save_config_button.clicked.connect(self.save_api_config)
        button_layout.addWidget(self.save_config_button)

        layout.addLayout(button_layout)

        api_widget.setLayout(layout)
        self.tab_widget.addTab(api_widget, "API设置")

    def load_api_config_to_ui(self):
        """将配置加载到UI控件中"""
        # 阻塞信号，防止加载时触发保存操作
        self.multimodal_provider_combo.blockSignals(True)
        self.chat_provider_combo.blockSignals(True)

        # 加载提供商选择
        multimodal_provider = self.api_config.get("multimodal_provider", "硅基流动")
        chat_provider = self.api_config.get("chat_provider", "硅基流动")

        self.multimodal_provider_combo.setCurrentText(multimodal_provider)
        self.chat_provider_combo.setCurrentText(chat_provider)

        # 加载语音识别API配置
        if hasattr(self, 'stt_api_key_edit'):
            stt_api_key = self.api_config.get("stt_siliconflow_api_key", "")
            self.stt_api_key_edit.setText(stt_api_key)

        # 触发配置加载（不会触发保存）
        self.on_multimodal_provider_changed(multimodal_provider)
        self.on_chat_provider_changed(chat_provider)

        # 恢复信号，恢复正常响应用户操作
        self.multimodal_provider_combo.blockSignals(False)
        self.chat_provider_combo.blockSignals(False)

    def get_provider_key(self, provider_name: str) -> str:
        """获取提供商在配置中的key"""
        if provider_name == "硅基流动":
            return "siliconflow"
        elif provider_name == "豆包":
            return "doubao"
        else:
            return "custom"

    def on_multimodal_provider_changed(self, provider_name: str):
        """当多模态提供商改变时，加载对应配置"""
        # 如果是用户操作导致的切换，先保存当前配置
        if not self.multimodal_provider_combo.signalsBlocked():
            self.save_current_multimodal_config()

        # 设置端点
        if provider_name == "硅基流动":
            self.multimodal_endpoint_edit.setText("https://api.siliconflow.cn/v1/chat/completions")
        elif provider_name == "豆包":
            self.multimodal_endpoint_edit.setText("https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        elif provider_name == "自定义":
            # 从配置加载自定义端点
            custom_config = self.api_config.get("custom", {})
            self.multimodal_endpoint_edit.setText(custom_config.get("multimodal_endpoint", ""))

        # 加载对应提供商的配置
        provider_key = self.get_provider_key(provider_name)
        provider_config = self.api_config.get(provider_key, {})

        self.multimodal_api_key_edit.setText(provider_config.get("multimodal_api_key", ""))
        self.multimodal_model_edit.setText(provider_config.get("multimodal_model", ""))

    def on_chat_provider_changed(self, provider_name: str):
        """当对话提供商改变时，加载对应配置"""
        # 如果是用户操作导致的切换，先保存当前配置
        if not self.chat_provider_combo.signalsBlocked():
            self.save_current_chat_config()

        # 设置端点
        if provider_name == "硅基流动":
            self.chat_endpoint_edit.setText("https://api.siliconflow.cn/v1/chat/completions")
        elif provider_name == "豆包":
            self.chat_endpoint_edit.setText("https://ark.cn-beijing.volces.com/api/v3/chat/completions")
        elif provider_name == "自定义":
            # 从配置加载自定义端点
            custom_config = self.api_config.get("custom", {})
            self.chat_endpoint_edit.setText(custom_config.get("chat_endpoint", ""))

        # 加载对应提供商的配置
        provider_key = self.get_provider_key(provider_name)
        provider_config = self.api_config.get(provider_key, {})

        self.chat_api_key_edit.setText(provider_config.get("chat_api_key", ""))
        self.chat_model_edit.setText(provider_config.get("chat_model", ""))

    def save_current_multimodal_config(self):
        """保存当前多模态配置到对应提供商"""
        if not hasattr(self, 'multimodal_provider_combo'):
            return

        current_provider = self.multimodal_provider_combo.currentText()
        provider_key = self.get_provider_key(current_provider)

        if provider_key not in self.api_config:
            self.api_config[provider_key] = {}

        self.api_config[provider_key]["multimodal_api_key"] = self.multimodal_api_key_edit.text().strip()
        self.api_config[provider_key]["multimodal_model"] = self.multimodal_model_edit.text().strip()

        if provider_key == "custom":
            self.api_config[provider_key]["multimodal_endpoint"] = self.multimodal_endpoint_edit.text().strip()

    def save_current_chat_config(self):
        """保存当前对话配置到对应提供商"""
        if not hasattr(self, 'chat_provider_combo'):
            return

        current_provider = self.chat_provider_combo.currentText()
        provider_key = self.get_provider_key(current_provider)

        if provider_key not in self.api_config:
            self.api_config[provider_key] = {}

        self.api_config[provider_key]["chat_api_key"] = self.chat_api_key_edit.text().strip()
        self.api_config[provider_key]["chat_model"] = self.chat_model_edit.text().strip()

        if provider_key == "custom":
            self.api_config[provider_key]["chat_endpoint"] = self.chat_endpoint_edit.text().strip()

    def save_api_config(self):
        """保存API配置"""
        try:
            # 先保存当前界面的配置
            self.save_current_multimodal_config()
            self.save_current_chat_config()

            # 更新提供商选择
            self.api_config["multimodal_provider"] = self.multimodal_provider_combo.currentText()
            self.api_config["chat_provider"] = self.chat_provider_combo.currentText()

            # 保存语音识别API配置
            if hasattr(self, 'stt_api_key_edit'):
                self.api_config["stt_siliconflow_api_key"] = self.stt_api_key_edit.text().strip()

            # 调用API服务保存配置
            if save_api_config(self.api_config):
                self.show_message("保存成功", "API配置已成功保存到config.json文件！", "information")
            else:
                self.show_message("保存失败", "无法保存配置文件，请检查文件权限！", "critical")

        except Exception as e:
            self.show_message("保存失败", f"保存配置时出错: {str(e)}", "critical")

    def set_dark_theme(self):
        """设置深色主题"""
        dark_style = """
        QMainWindow {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QTabWidget::pane {
            border: 1px solid #555555;
            background-color: #2b2b2b;
        }
        QTabWidget::tab-bar {
            left: 5px;
        }
        QTabBar::tab {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
            border-bottom-color: #2b2b2b;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            min-width: 120px;
            padding: 8px;
        }
        QTabBar::tab:selected {
            background-color: #2b2b2b;
            border-bottom-color: #2b2b2b;
        }
        QTabBar::tab:!selected {
            margin-top: 2px;
        }
        QLabel {
            color: #ffffff;
        }
        QComboBox {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox::down-arrow {
            width: 12px;
            height: 12px;
        }
        QPushButton {
            background-color: #4a4a4a;
            color: #ffffff;
            border: 1px solid #666666;
            border-radius: 4px;
            padding: 8px 16px;
        }
        QPushButton:hover {
            background-color: #5a5a5a;
        }
        QPushButton:pressed {
            background-color: #3a3a3a;
        }
        QTextEdit {
            background-color: #2b2b2b;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
        }
        QLineEdit {
            background-color: #3c3c3c;
            color: #ffffff;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
        }
        QLineEdit:focus {
            border-color: #4CAF50;
        }
        QGridLayout {
            margin: 10px;
        }
        """
        self.setStyleSheet(dark_style)

    def load_character_list(self):
        """加载角色列表"""
        self.character_combo.clear()

        # 扫描 characters 文件夹下的所有 .md 文件
        if os.path.exists(self.characters_dir):
            md_files = [f for f in os.listdir(self.characters_dir) if f.endswith('.md')]
            character_names = [os.path.splitext(f)[0] for f in md_files]

            if character_names:
                self.character_combo.addItems(character_names)

                # 同时更新速记台的角色下拉框
                if hasattr(self, 'record_character_combo'):
                    self.record_character_combo.clear()
                    self.record_character_combo.addItems(character_names)

                # 更新抉择辅助标签页的角色下拉框
                if hasattr(self, 'questioner_combo'):
                    self.questioner_combo.clear()
                    self.questioner_combo.addItems(character_names)

                # 更新相关人下拉框（包含"无"选项）
                related_options = ["无"] + character_names

                if hasattr(self, 'related_person1_combo'):
                    self.related_person1_combo.clear()
                    self.related_person1_combo.addItems(related_options)
                    self.related_person1_combo.setCurrentText("无")

                if hasattr(self, 'related_person2_combo'):
                    self.related_person2_combo.clear()
                    self.related_person2_combo.addItems(related_options)
                    self.related_person2_combo.setCurrentText("无")

                if hasattr(self, 'related_person3_combo'):
                    self.related_person3_combo.clear()
                    self.related_person3_combo.addItems(related_options)
                    self.related_person3_combo.setCurrentText("无")
            else:
                self.character_combo.addItem(self.NO_CHARACTER_NOTICE)
                if hasattr(self, 'record_character_combo'):
                    self.record_character_combo.clear()
                    self.record_character_combo.addItem(self.NO_CHARACTER_NOTICE)

                # 抉择辅助页面无角色时的处理
                if hasattr(self, 'questioner_combo'):
                    self.questioner_combo.clear()
                    self.questioner_combo.addItem(self.NO_CHARACTER_NOTICE)

                no_char_options = ["无", self.NO_CHARACTER_NOTICE]
                if hasattr(self, 'related_person1_combo'):
                    self.related_person1_combo.clear()
                    self.related_person1_combo.addItems(no_char_options)
                    self.related_person1_combo.setCurrentText("无")

                if hasattr(self, 'related_person2_combo'):
                    self.related_person2_combo.clear()
                    self.related_person2_combo.addItems(no_char_options)
                    self.related_person2_combo.setCurrentText("无")

                if hasattr(self, 'related_person3_combo'):
                    self.related_person3_combo.clear()
                    self.related_person3_combo.addItems(no_char_options)
                    self.related_person3_combo.setCurrentText("无")
        else:
            self.character_combo.addItem(self.NO_CHARACTER_NOTICE)
            if hasattr(self, 'record_character_combo'):
                self.record_character_combo.clear()
                self.record_character_combo.addItem(self.NO_CHARACTER_NOTICE)

            # 抉择辅助页面无字符文件夹时的处理
            if hasattr(self, 'questioner_combo'):
                self.questioner_combo.clear()
                self.questioner_combo.addItem(self.NO_CHARACTER_NOTICE)

            no_char_options = ["无", self.NO_CHARACTER_NOTICE]
            if hasattr(self, 'related_person1_combo'):
                self.related_person1_combo.clear()
                self.related_person1_combo.addItems(no_char_options)
                self.related_person1_combo.setCurrentText("无")

            if hasattr(self, 'related_person2_combo'):
                self.related_person2_combo.clear()
                self.related_person2_combo.addItems(no_char_options)
                self.related_person2_combo.setCurrentText("无")

            if hasattr(self, 'related_person3_combo'):
                self.related_person3_combo.clear()
                self.related_person3_combo.addItems(no_char_options)
                self.related_person3_combo.setCurrentText("无")

    def on_character_changed(self, character_name):
        """当角色选择改变时，加载对应的档案内容"""
        if character_name and character_name != self.NO_CHARACTER_NOTICE:
            file_path = os.path.join(self.characters_dir, f"{character_name}.md")

            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        content = file.read()
                        self.dossier_text_edit.setPlainText(content)
                except Exception as e:
                    self.dossier_text_edit.setPlainText(f"读取档案失败: {str(e)}")
            else:
                self.dossier_text_edit.setPlainText("档案文件不存在")
        else:
            self.dossier_text_edit.setPlainText("")

    def create_new_character(self):
        """创建新角色"""
        # 1. 创建QInputDialog实例
        dialog = QInputDialog(self)
        dialog.setWindowTitle("创建新角色")
        dialog.setLabelText("请输入新角色的名称:")
        dialog.setTextValue("")  # 设置初始文本为空

        # 2. 为该实例单独设置浅色主题样式
        dialog.setStyleSheet("""
            QInputDialog {
                background-color: #EFEFEF;
                color: #000000;
            }
            QInputDialog QLabel {
                color: #000000;
            }
            QInputDialog QLineEdit {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
            QInputDialog QPushButton {
                background-color: #FFFFFF;
                color: #000000;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 6px 12px;
                min-width: 60px;
            }
            QInputDialog QPushButton:hover {
                background-color: #F0F0F0;
            }
            QInputDialog QPushButton:pressed {
                background-color: #E0E0E0;
            }
        """)

        # 3. 执行对话框并获取结果
        ok = dialog.exec()
        character_name = dialog.textValue()

        # 4. 后续逻辑保持不变
        if ok and character_name.strip():
            character_name = character_name.strip()
            file_path = os.path.join(self.characters_dir, f"{character_name}.md")

            if os.path.exists(file_path):
                self.show_message("创建失败", f"角色 '{character_name}' 已存在！", "warning")
                return

            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(f"# {character_name}\n\n## 基本信息\n\n## 性格特点\n\n## 背景故事\n\n")

                self.load_character_list()

                index = self.character_combo.findText(character_name)
                if index >= 0:
                    self.character_combo.setCurrentIndex(index)

                self.show_message("创建成功", f"角色 '{character_name}' 创建成功！", "information")

            except Exception as e:
                self.show_message("创建失败", f"创建角色档案时出错: {str(e)}", "critical")

    def save_current_dossier(self):
        """保存当前修改"""
        current_character = self.character_combo.currentText()

        # 检查是否选中了有效角色
        if not current_character or current_character == self.NO_CHARACTER_NOTICE:
            self.show_message("保存失败", "请先选择一个有效的角色！", "warning")
            return

        # 二次确认
        if self.show_message("确认保存", "是否确定要保存修改？", "question"):
            try:
                # 获取文本内容
                content = self.dossier_text_edit.toPlainText()
                file_path = os.path.join(self.characters_dir, f"{current_character}.md")

                # 保存到文件
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(content)

                self.show_message("保存成功", f"角色 '{current_character}' 的档案已保存！", "information")

            except Exception as e:
                self.show_message("保存失败", f"保存档案时出错: {str(e)}", "critical")

    def start_smart_screenshot(self):
        """智能截图统一入口 - 根据当前标签页选择不同的分析模式"""
        if self.is_capturing:
            print("捕获已在进行中，忽略此次触发。")
            return
        try:
            # 获取当前激活的标签页索引
            current_index = self.tab_widget.currentIndex()

            # 根据索引设置截图目标
            if current_index == 0:  # 速记台
                self.screenshot_target = "notes"
            elif current_index == 1:  # 抉择辅助
                self.screenshot_target = "decision"
            else:
                # 其他标签页不支持截图功能
                self.show_message(
                    "功能提示",
                    "截图功能仅在「速记与整理台」和「抉择辅助」标签页中可用。\n\n请切换到相应标签页后再使用截图功能。",
                    "information"
                )
                return

            # 记录目标后，执行原有的截图逻辑
            self.is_capturing = True
            self.start_screenshot()

        except Exception as e:
            self.is_capturing = False
            self.show_message("错误", f"启动截图功能时出错: {str(e)}", "critical")

    def capture_fullscreen_and_analyze(self):
        """捕获全屏并直接开始分析"""
        if self.is_capturing:
            print("捕获已在进行中，忽略此次触发。")
            return
        try:
            current_index = self.tab_widget.currentIndex()
            if current_index == 0:
                self.screenshot_target = "notes"
            elif current_index == 1:
                self.screenshot_target = "decision"
            else:
                self.show_message("功能提示", "全屏截图功能仅在「速记与整理台」和「抉择辅助」标签页中可用。", "information")
                return

            screen = QApplication.primaryScreen()
            full_pixmap = screen.grabWindow(0)

            if full_pixmap.isNull():
                print("全屏截图失败，获取的图像为空。")
                self.is_capturing = False
                return

            self.is_capturing = True
            self.on_screenshot_completed(full_pixmap, screen.geometry())

        except Exception as e:
            self.is_capturing = False
            self.show_message("错误", f"全屏截图时出错: {str(e)}", "critical")

    def start_screenshot(self):
        """开始截图 - 修复版本"""
        # 完全隐藏主窗口
        self.hide()
        self.setWindowState(Qt.WindowState.WindowMinimized)

        # 增加延迟时间确保窗口完全消失，包括渐隐动画
        QTimer.singleShot(500, self.capture_and_snip)

    def capture_and_snip(self):
        """捕获屏幕并启动选择工具"""
        try:
            # 执行屏幕捕获
            screen = QApplication.primaryScreen()
            pixmap = screen.grabWindow(0)

            # 检查pixmap是否有效
            if pixmap.isNull():
                self.setWindowState(Qt.WindowState.WindowNoState)
                self.show()  # 恢复主窗口

                # 使用内联反馈替代弹窗
                self.ocr_status_label.setText("❌ 截图失败")
                self.ocr_status_label.setStyleSheet("color: #F44336; margin-left: 10px; margin-top: 10px;")
                QTimer.singleShot(5000, lambda: self.ocr_status_label.setText(""))
                self.is_capturing = False
                return

            # 创建截图工具实例，传入捕获的图像
            self.snipping_widget = SnippingWidget(pixmap)

            # 连接信号
            self.snipping_widget.screenshot_completed.connect(self.on_screenshot_completed)
            self.snipping_widget.screenshot_cancelled.connect(self.on_screenshot_cancelled)

            # 显示截图窗口
            self.snipping_widget.show()
            self.snipping_widget.raise_()
            self.snipping_widget.activateWindow()

        except Exception as e:
            self.setWindowState(Qt.WindowState.WindowNoState)
            self.show()  # 恢复主窗口

            # 使用内联反馈替代弹窗
            self.ocr_status_label.setText("❌ 截图错误")
            self.ocr_status_label.setStyleSheet("color: #F44336; margin-left: 10px; margin-top: 10px;")
            QTimer.singleShot(5000, lambda: self.ocr_status_label.setText(""))
            self.is_capturing = False

    def on_screenshot_completed(self, pixmap: QPixmap, rect: QRect):
        """处理截图完成事件 - 智能分支版本"""
        self.is_capturing = False
        # 先恢复主窗口显示
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.show()
        self.raise_()
        self.activateWindow()

        print(f"截图完成: x={rect.x()}, y={rect.y()}, width={rect.width()}, height={rect.height()}")
        print(f"截图大小: {pixmap.width()} x {pixmap.height()} 像素")
        print(f"截图目标: {getattr(self, 'screenshot_target', 'unknown')}")

        try:
            # 设置等待光标
            self.setCursor(Qt.CursorShape.WaitCursor)

            # 保存截图到剪贴板
            clipboard = QApplication.clipboard()
            clipboard.setPixmap(pixmap)

            # 可选：保存到文件
            timestamp = QApplication.instance().applicationDisplayName() or "screenshot"
            filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

            # 创建screenshots文件夹
            screenshots_dir = "screenshots"
            if not os.path.exists(screenshots_dir):
                os.makedirs(screenshots_dir)

            filepath = os.path.join(screenshots_dir, filename)
            pixmap.save(filepath, "PNG")

            # 检查API配置
            multimodal_provider = self.api_config.get("multimodal_provider", "硅基流动")
            provider_key = self.get_provider_key(multimodal_provider)
            provider_config = self.api_config.get(provider_key, {})

            api_key = provider_config.get("multimodal_api_key", "")
            model = provider_config.get("multimodal_model", "")

            # 获取端点
            if provider_key == "custom":
                endpoint = provider_config.get("multimodal_endpoint", "")
            elif multimodal_provider == "硅基流动":
                endpoint = "https://api.siliconflow.cn/v1/chat/completions"
            elif multimodal_provider == "豆包":
                endpoint = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
            else:
                endpoint = ""

            if not api_key or not endpoint or not model:
                error_msg = f"多模态API配置不完整，请前往【API设置】标签页配置{multimodal_provider}的API Key、端点和模型名称"

                # 根据目标设置错误信息到对应位置
                if hasattr(self, 'screenshot_target'):
                    if self.screenshot_target == "notes":
                        self.ocr_result_text.setPlainText(error_msg)
                    elif self.screenshot_target == "decision":
                        self.game_analysis_text.setPlainText(error_msg)
                return

            # 停止之前的OCR任务（如果存在）
            if self.ocr_worker and self.ocr_worker.isRunning():
                self.ocr_worker.terminate()
                self.ocr_worker.wait()

            # 根据截图目标执行不同的分析任务
            if hasattr(self, 'screenshot_target'):
                if self.screenshot_target == "notes":
                    # 速记台：画面描述 + 对话内容提取
                    self.ocr_result_text.setPlainText("正在识别中...")
                    self.ocr_status_label.setText("🔍 正在识别中...")
                    self.ocr_status_label.setStyleSheet("color: #FF9800; margin-left: 10px; margin-top: 10px;")

                    # 创建并启动OCR工作线程（使用现有的系统Prompt）
                    self.ocr_worker = OCRWorker(pixmap, api_key, endpoint, model)
                    self.ocr_worker.ocr_completed.connect(self.on_ocr_completed)
                    self.ocr_worker.ocr_failed.connect(self.on_ocr_failed)
                    self.ocr_worker.start()

                elif self.screenshot_target == "decision":
                    # 抉择辅助：纯画面分析，不提取文字
                    self.game_analysis_text.setPlainText("正在分析游戏画面...")

                    # 构建抉择专用的Prompt
                    decision_prompt = self.build_decision_image_prompt()

                    # 创建决策分析专用的工作线程
                    self.decision_worker = DecisionAnalysisWorker(pixmap, api_key, endpoint, model, decision_prompt)
                    self.decision_worker.analysis_completed.connect(self.on_decision_analysis_completed)
                    self.decision_worker.analysis_failed.connect(self.on_decision_analysis_failed)
                    self.decision_worker.start()

            else:
                # 没有设置截图目标，默认使用速记台模式
                self.ocr_result_text.setPlainText("正在识别中...")
                self.ocr_status_label.setText("🔍 正在识别中...")
                self.ocr_status_label.setStyleSheet("color: #FF9800; margin-left: 10px; margin-top: 10px;")

                self.ocr_worker = OCRWorker(pixmap, api_key, endpoint, model)
                self.ocr_worker.ocr_completed.connect(self.on_ocr_completed)
                self.ocr_worker.ocr_failed.connect(self.on_ocr_failed)
                self.ocr_worker.start()

        except Exception as e:
            # 根据目标设置错误信息到对应位置
            if hasattr(self, 'screenshot_target'):
                if self.screenshot_target == "notes":
                    self.ocr_status_label.setText("❌ 截图错误")
                    self.ocr_status_label.setStyleSheet("color: #F44336; margin-left: 10px; margin-top: 10px;")
                    QTimer.singleShot(5000, lambda: self.ocr_status_label.setText(""))
                elif self.screenshot_target == "decision":
                    self.game_analysis_text.setPlainText(f"❌ 截图处理失败: {str(e)}")
            else:
                # 默认错误处理
                self.ocr_status_label.setText("❌ 截图错误")
                self.ocr_status_label.setStyleSheet("color: #F44336; margin-left: 10px; margin-top: 10px;")
                QTimer.singleShot(5000, lambda: self.ocr_status_label.setText(""))
        finally:
            # 恢复正常光标
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def on_ocr_completed(self, result: str):
        """OCR识别完成的回调"""
        # 将识别结果显示到文本框
        self.ocr_result_text.setPlainText(result)

        # 显示内联状态反馈
        self.ocr_status_label.setText(f"✅ 识别完成，共 {len(result)} 个字符")
        self.ocr_status_label.setStyleSheet("color: #4CAF50; margin-left: 10px; margin-top: 10px;")

        # 4秒后自动消失
        QTimer.singleShot(4000, lambda: self.ocr_status_label.setText(""))

    def on_ocr_failed(self, error_message: str):
        """OCR识别失败的回调"""
        # 显示错误信息到文本框
        self.ocr_result_text.setPlainText(f"识别失败: {error_message}")

        # 显示内联状态反馈
        self.ocr_status_label.setText("❌ 识别失败")
        self.ocr_status_label.setStyleSheet("color: #F44336; margin-left: 10px; margin-top: 10px;")

        # 5秒后自动消失
        QTimer.singleShot(5000, lambda: self.ocr_status_label.setText(""))

    def on_screenshot_cancelled(self):
        """处理截图取消事件"""
        self.is_capturing = False
        # 恢复主窗口显示
        self.setWindowState(Qt.WindowState.WindowNoState)
        self.show()
        self.raise_()
        self.activateWindow()
        print("截图已取消")

    def on_screenshot_area_selected(self, rect: QRect):
        """旧版本兼容方法 - 将被移除"""
        # 保留空方法以避免错误
        pass

    # ====== 语音功能 ======
    def toggle_voice_function(self):
        """切换语音功能开关"""
        is_checked = self.voice_toggle_button.isChecked()
        success = self.voice_manager.toggle_service(is_checked)

        # 如果启用失败，重置按钮状态
        if not success and is_checked:
            self.voice_toggle_button.setChecked(False)

    def keyPressEvent(self, event):
        """键盘按下事件 - 委托给语音管理器处理"""
        # 如果管理器处理了该事件，则直接返回，否则交由父类处理
        if not self.voice_manager.handle_key_press(event):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """键盘释放事件 (简化版)"""
        # 在"按键切换"模式下，此方法不应有任何逻辑，
        # 仅需将事件传递给父类进行默认处理即可。
        super().keyReleaseEvent(event)

    def on_voice_status_updated(self, status_text: str, color_code: str):
        """语音状态更新处理器"""
        self.voice_status_label.setText(status_text)
        self.voice_status_label.setStyleSheet(f"color: {color_code}; margin-left: 8px; font-size: 12px;")

    def insert_text_to_focused_widget(self, text: str):
        """将文字插入到当前焦点的文本框中"""
        try:
            # 获取当前有焦点的控件
            focused_widget = QApplication.focusWidget()

            if focused_widget and hasattr(focused_widget, 'insertPlainText'):
                # 如果是QTextEdit类型
                focused_widget.insertPlainText(text)
            elif focused_widget and hasattr(focused_widget, 'insert'):
                # 如果是QLineEdit类型
                focused_widget.insert(text)
            else:
                # 默认插入到用户补充信息框
                if hasattr(self, 'user_context_text'):
                    self.user_context_text.insertPlainText(text)

        except Exception as e:
            print(f"插入文字时出错: {str(e)}")


def main():
    """主程序入口"""
    app = QApplication(sys.argv)

    # 设置应用程序图标
    app.setWindowIcon(QIcon("assets/icons/app_icon.ico"))

    # 设置应用程序基本信息
    app.setApplicationName("互动游戏AI狗头军师")
    app.setApplicationVersion("1.0.0")

    # 创建并显示主窗口
    main_window = MainWindow()
    main_window.show()

    # 启动事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
