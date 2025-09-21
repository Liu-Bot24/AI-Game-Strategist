# 互动游戏AI狗头军师 (AI-Game-Strategist)

一款基于 PyQt6 的桌面助手，帮助玩家在游戏或直播过程中快速截图、整理笔记、记录角色档案，并通过自定义 API 进行 OCR / 多模态分析或语音转文字。适合“边玩边记录”“边分析边沟通”的使用场景。

![主界面截图](assets/readme/main_interface.png)

## 功能亮点

* **全局截图热键**：

  * Ctrl+1 区域截图，弹出遮罩框选即可复制并触发后续流程；
  * Ctrl+2 直接抓取主屏，无需切换窗口；
  * 通过隐藏消息窗口监听 WM\_HOTKEY，即使程序位于后台也能触发，窗口激活时仍保留普通快捷键作为兜底。
* **语音输入与转写**：Shift 键切换录音状态，基于 PyAudio，将语音发送到配置的语音识别 API。
* **角色档案与策略整理**：在“速记与整理台”中整合 OCR 文本、补充背景、生成结构化总结；角色档案页支持长期维护。
* **灵活 API 配置**：在“API 设置”页填写多模态 / 语音接口参数（兼容 OpenAI 风格），所有配置保存在本地 config.json。
* **一键打包 EXE**：内置 build\_exe.bat，可一键生成带图标与资源的 Windows 可执行文件。

## 示例截图

![抉择辅助示例1](assets/readme/decision_support.png)

![抉择辅助示例2](assets/readme/decision_support2.png)

![抉择辅助示例3](assets/readme/decision_support3.png)

## 环境要求

* 系统：Windows 10 / 11（全局热键依赖 Win32 API）
* Python：3.8 及以上（推荐 3.10+）

## 安装依赖

1. （可选）创建并激活虚拟环境：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. 安装项目所需库：

   ```powershell
   pip install -U pip
   pip install PyQt6 requests pillow pyaudio
   ```

## 从源码运行

```powershell
python main.py
```

首次运行会在 characters/、screenshots/ 下创建占位文件夹（使用 .gitkeep），右上角可开关语音功能并实时显示状态。

## 打包为 EXE

项目根目录提供 build\_exe.bat 脚本：

* **保留控制台日志（推荐，便于排错）**

  ```powershell
  .\build_exe.bat
  ```
* **隐藏控制台（纯 GUI）**

  ```powershell
  .\build_exe.bat gui
  ```

脚本会自动：

1. 自动寻找 Python（优先 py -3，失败回退 python）。
2. 安装/更新 PyInstaller、PyQt6、requests、pillow、pyaudio。
3. 清理旧的 build/、dist/、.spec 文件。
4. 执行 PyInstaller，并用 --add-data assets;assets 将图标与图片一并复制。

打包完成后，可执行文件位于 `dist\AI-Game-Strategist\AI-Game-Strategist.exe`，同级的 `assets` 文件夹保证图标正常显示。

> 若希望生成 --onefile 单文件，可自行修改脚本中的 PyInstaller 命令；记得同步调整 resource\_path() 以从 sys.\_MEIPASS 读取资源。

## 目录结构

```
.
├── main.py                # 主程序入口，负责 UI 与全局热键
├── snipping_tool.py       # 自定义截图遮罩窗口
├── api_service.py         # OCR / 多模态 / 语音 API 封装
├── audio_processing.py    # 录音与转写逻辑
├── assets/                # 图标与 README 插图
├── characters/            # 角色档案（仅提交 .gitkeep）
├── screenshots/           # 截图输出目录（仅提交 .gitkeep）
├── build_exe.bat          # 一键打包脚本（仓库中唯一保留的 .bat）
└── README.md              # 使用说明
```

## 快捷键一览

| 快捷键    | 功能说明                |
| ------ | ------------------- |
| Ctrl+1 | 区域截图（全局可用，窗口激活时也保留） |
| Ctrl+2 | 全屏截图并进入分析流程         |
| Shift  | 切换语音录制状态（需开启语音功能）   |

## 常见问题

* **双击 EXE 后直接关闭**：请在 PowerShell 中运行 `dist\AI-Game-Strategist\AI-Game-Strategist.exe`，查看输出的错误信息。
* **图标或资源丢失**：确认 `dist\AI-Game-Strategist\assets` 目录存在；打包脚本会自动复制。
* **语音功能无响应**：检查麦克风权限，确认 pyaudio 安装成功。
* **API 不生效**：在“API 设置”页补全必填字段并保存，config.json 已在 .gitignore 中忽略。

## 版本控制说明

* .gitignore 已忽略 build/、dist/、各种日志以及除 build\_exe.bat 外的所有 .bat 文件。
* 配置文件 config.json、个人笔记、运行时输出不会被提交。
* characters/、screenshots/ 仅提交 .gitkeep，实际资料保留在本地。

若后续扩展了新的 API 或工作流，欢迎同步更新 README.md 与 build\_exe.bat，保持打包流程简单可靠。祝使用愉快！
