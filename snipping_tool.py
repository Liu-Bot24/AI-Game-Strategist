#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
截图工具模块 (Snipping Tool Module) - 重构版本
只负责在已有图像上进行选择，不负责捕获屏幕
"""

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap


class SnippingWidget(QWidget):
    """截图选择窗口部件 - 重构版本"""

    # 自定义信号，当截图区域选择完成时发射
    screenshot_completed = pyqtSignal(QPixmap, QRect)  # 发射截图和区域信息
    screenshot_cancelled = pyqtSignal()  # 取消截图信号

    def __init__(self, screen_pixmap):
        """初始化截图工具，接受已捕获的屏幕图像"""
        super().__init__()
        self.screen_pixmap = screen_pixmap  # 保存传入的屏幕截图
        self.start_point = None
        self.end_point = None
        self.is_selecting = False

        self.init_ui()

    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口属性
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )

        # 设置窗口属性
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # 设置为全屏
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        self.setGeometry(screen_geometry)

        # 设置鼠标和键盘追踪
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 设置光标
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mousePressEvent(self, event):
        """鼠标按下事件"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        """鼠标移动事件"""
        if self.is_selecting and self.start_point:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        """鼠标松开事件"""
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.end_point = event.pos()
            self.finish_selection()

    def keyPressEvent(self, event):
        """键盘按下事件"""
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_snipping()
        super().keyPressEvent(event)

    def finish_selection(self):
        """完成选择，并根据DPI缩放比例修正坐标"""
        if self.start_point and self.end_point and self.screen_pixmap:
            # 1. 从鼠标事件获取的选框，是"逻辑像素"坐标
            logical_rect = QRect(self.start_point, self.end_point).normalized()

            # 2. 获取屏幕的缩放比例 (例如 1.0, 1.5, 2.0)
            # screen_pixmap 是通过 grabWindow 捕获的，它知道自己来源屏幕的DPI信息
            pixel_ratio = self.screen_pixmap.devicePixelRatio()
            if not pixel_ratio:  # 安全回退
                pixel_ratio = 1.0

            # 3. 将"逻辑"坐标乘以缩放比例，得到"物理"像素坐标
            physical_rect = QRect(
                int(logical_rect.x() * pixel_ratio),
                int(logical_rect.y() * pixel_ratio),
                int(logical_rect.width() * pixel_ratio),
                int(logical_rect.height() * pixel_ratio)
            )

            # 4. 裁剪时，使用修正后的"物理"坐标
            if logical_rect.width() > 5 and logical_rect.height() > 5:
                cropped_pixmap = self.screen_pixmap.copy(physical_rect)

                # 5. 通知新生成的截图，它的DPI比例，以便其他地方能正确显示它
                cropped_pixmap.setDevicePixelRatio(pixel_ratio)

                # 发射信号时，我们传递最终的截图和原始的"逻辑"坐标（用于信息显示）
                self.screenshot_completed.emit(cropped_pixmap, logical_rect)
            else:
                self.screenshot_cancelled.emit()
        else:
            self.screenshot_cancelled.emit()

        # 关闭窗口
        self.close()

    def cancel_snipping(self):
        """取消截图"""
        self.screenshot_cancelled.emit()
        self.close()

    def paintEvent(self, event):
        """绘制事件 - 修复了高DPI下的预览问题"""
        painter = QPainter(self)

        if not self.screen_pixmap:
            return

        # 1. 将完整的物理像素图绘制到逻辑像素的窗口上
        # PyQt 会自动处理这里的缩放
        painter.drawPixmap(self.rect(), self.screen_pixmap)

        # 2. 绘制半透明黑色遮罩，覆盖整个屏幕
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        # 如果正在选择，处理选择区域
        if self.is_selecting and self.start_point and self.end_point:
            # 3. 获取"逻辑像素"单位的选择框
            logical_rect = QRect(self.start_point, self.end_point).normalized()

            # 4. 获取DPI缩放比例
            pixel_ratio = self.screen_pixmap.devicePixelRatio()
            if not pixel_ratio:
                pixel_ratio = 1.0

            # 5. 计算出需要从源图 (物理像素) 中裁剪的区域
            physical_source_rect = QRect(
                int(logical_rect.x() * pixel_ratio),
                int(logical_rect.y() * pixel_ratio),
                int(logical_rect.width() * pixel_ratio),
                int(logical_rect.height() * pixel_ratio)
            )

            # 6. 将物理像素的源区域，绘制到逻辑像素的目标区域
            # 这会"擦除"掉选区内的黑色遮罩，并正确显示预览
            painter.drawPixmap(logical_rect, self.screen_pixmap, physical_source_rect)

            # 7. 绘制选择框边框 (使用逻辑坐标)
            pen = QPen(QColor(0, 120, 215), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(logical_rect)

            # 8. 绘制尺寸信息 (使用逻辑坐标)
            if logical_rect.width() > 30 and logical_rect.height() > 15:
                size_text = f"{logical_rect.width()} × {logical_rect.height()}"

                text_x = logical_rect.x() + 8
                text_y = logical_rect.y() - 25

                if text_y < 10:
                    text_y = logical_rect.y() + 20

                text_rect = painter.fontMetrics().boundingRect(size_text)
                bg_rect = QRect(text_x - 4, text_y - text_rect.height() + 2,
                               text_rect.width() + 8, text_rect.height() + 4)

                painter.fillRect(bg_rect, QColor(255, 255, 255, 220))
                painter.setPen(QColor(0, 0, 0))
                painter.drawText(text_x, text_y, size_text)

    def closeEvent(self, event):
        """窗口关闭事件"""
        self.is_selecting = False
        event.accept()