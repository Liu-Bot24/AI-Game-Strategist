#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音频处理模块
实现"按住说话"功能的音频录制和语音转文字
"""

import pyaudio
import wave
import io
import threading
from PyQt6.QtCore import QThread, pyqtSignal


class AudioRecorder:
    """
    简单的音频录制器，用于"按住说话"功能
    """

    def __init__(self):
        # 音频参数
        self.sample_rate = 16000      # 采样率 16kHz
        self.channels = 1             # 单声道
        self.chunk_size = 1024        # 每次读取的样本数
        self.format = pyaudio.paInt16 # 16位深度

        # 录制状态
        self.is_recording = False
        self.audio_frames = []
        self.pyaudio_instance = None
        self.stream = None

    def start_recording(self):
        """开始录制"""
        if self.is_recording:
            return False

        try:
            # 初始化PyAudio
            self.pyaudio_instance = pyaudio.PyAudio()

            # 打开音频流
            self.stream = self.pyaudio_instance.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )

            self.is_recording = True
            self.audio_frames = []
            return True

        except Exception as e:
            print(f"开始录制失败: {str(e)}")
            return False

    def stop_recording(self):
        """停止录制并返回音频数据"""
        if not self.is_recording:
            return None

        try:
            self.is_recording = False

            # 关闭音频流
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None

            # 将音频帧转换为WAV格式字节数据
            if self.audio_frames:
                return self._convert_to_wav(self.audio_frames)
            else:
                return None

        except Exception as e:
            print(f"停止录制失败: {str(e)}")
            return None

    def record_chunk(self):
        """录制一个音频块"""
        if not self.is_recording or not self.stream:
            return

        try:
            audio_data = self.stream.read(self.chunk_size, exception_on_overflow=False)
            self.audio_frames.append(audio_data)
        except Exception as e:
            print(f"录制音频块失败: {str(e)}")

    def _convert_to_wav(self, audio_frames):
        """将音频帧转换为WAV格式字节数据"""
        try:
            # 创建内存中的WAV文件
            wav_buffer = io.BytesIO()

            with wave.open(wav_buffer, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(pyaudio.get_sample_size(self.format))
                wav_file.setframerate(self.sample_rate)

                # 写入音频数据
                for frame in audio_frames:
                    wav_file.writeframes(frame)

            wav_buffer.seek(0)
            return wav_buffer.read()

        except Exception as e:
            print(f"转换WAV格式失败: {str(e)}")
            return None


class STTWorker(QThread):
    """
    语音转文字工作线程
    """

    # 信号定义
    stt_completed = pyqtSignal(str)  # 转换完成
    stt_failed = pyqtSignal(str)     # 转换失败

    def __init__(self, audio_data: bytes, api_key: str):
        super().__init__()
        self.audio_data = audio_data
        self.api_key = api_key

    def run(self):
        """执行语音转文字"""
        try:
            from api_service import get_text_from_audio

            # 调用语音识别API
            result = get_text_from_audio(self.api_key, self.audio_data)

            # 检查结果
            if result.startswith(("语音识别API调用失败", "网络连接错误", "语音识别API调用超时", "语音识别过程中出现错误")):
                self.stt_failed.emit(result)
            else:
                self.stt_completed.emit(result)

        except Exception as e:
            self.stt_failed.emit(f"语音转文字异常: {str(e)}")