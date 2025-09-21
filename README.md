# 互动游戏AI狗头军师 (AI-Game-Strategist)

![主界面截图](assets/readme/main_interface.png)

一款面向“边玩边思考”的轻量工具：提供区域/全屏截图、语音转文字、简单的抉择辅助等能力，帮助你快速记录和整理游戏信息。

---

## 功能特性

- 区域截图与全屏截图：
  - Ctrl+1 区域截图（可在任意前台窗口或后台触发）
  - Ctrl+2 全屏截图并直接进入分析
- 语音转文字：Shift 键切换录音（基于 PyAudio）
- 角色档案与笔记整理：支持记录角色信息、粘贴识别结果
- 多模型/自定义 API：在“API 设置”页配置（兼容 OpenAI 风格接口）

提示：全局热键采用 Windows 原生 WM_HOTKEY，在后台线程创建隐藏消息窗口统一监听；窗口内快捷键仍作为兜底存在。

## 示例截图

![抉择辅助示例1](assets/readme/decision_support.png)

![抉择辅助示例2](assets/readme/decision_support2.png)

## 运行环境

- 系统：Windows 10/11
- Python：3.8+（推荐 3.10+）

安装依赖：
```
pip install PyQt6 requests pillow pyaudio
```

启动：
```
python main.py
```

## 快捷键

| 快捷键       | 功能               |
| ------------ | ------------------ |
| Ctrl + 1     | 区域截图           |
| Ctrl + 2     | 全屏截图并分析     |
| Shift（切换）| 语音录音 开/关     |

说明：
- Ctrl+1/Ctrl+2 全局热键可在任何程序前台触发；若系统占用或注册失败，窗口处于激活时仍可使用本地快捷键作为兜底。
- Shift 录音切换仅在“语音功能开启”时生效。

## 注意事项

- 请勿将包含密钥的 `config.json` 提交到公共仓库，可提供 `config.example.json` 示例。
- 截图文件默认保存到 `screenshots/` 目录，并同时复制到剪贴板。

## 目录结构

```
.
├─ main.py                 # 主程序入口
├─ snipping_tool.py        # 截图选择工具
├─ api_service.py          # API 请求封装
├─ audio_processing.py     # 录音/转写相关
├─ assets/                 # 资源（图标、README图片）
├─ screenshots/            # 截图输出目录
└─ characters/             # 角色档案（Markdown）
```

如果该项目对你有帮助，欢迎 Star 支持！
