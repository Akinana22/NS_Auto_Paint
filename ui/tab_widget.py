"""
自定义标签页控件 v2.2.0
为后续拖拽分离/合并功能预留扩展接口
当前版本与 QTabWidget 行为完全一致
"""

from PySide6.QtWidgets import QTabWidget, QTabBar
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon


class DockableTabWidget(QTabWidget):
    """
    可扩展的标签页控件，目前为标准 QTabWidget 行为。
    预留信号和方法用于后续拖拽分离功能。
    """

    # 预留信号：标签页拖出请求
    tab_detached = Signal(object, str, QIcon)  # widget, title, icon

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)  # 允许用户手动调整标签顺序

        # 预留拖拽相关属性
        self._drag_start_pos = None
        self._dragged_index = -1

    def add_fixed_tab(self, widget, title, icon=None):
        """添加不可关闭的固定标签页"""
        index = self.addTab(widget, title)
        if icon:
            self.setTabIcon(index, icon)
        # 隐藏关闭按钮
        close_btn = self.tabBar().tabButton(index, QTabBar.RightSide)
        if close_btn:
            close_btn.hide()
        return index

    def add_closable_tab(self, widget, title, icon=None):
        """添加可关闭的标签页"""
        index = self.addTab(widget, title)
        if icon:
            self.setTabIcon(index, icon)
        self.setCurrentIndex(index)
        return index

    # 以下方法为拖拽分离功能预留（当前未激活）
    # 后续实现时可重写 mousePressEvent、mouseMoveEvent、mouseReleaseEvent
    # 并在适当时候发射 tab_detached 信号
