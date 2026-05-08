"""
画布预览控件 v2.3.0
支持 Ctrl+滚轮精细缩放、缩放工具栏（+/-/fit/百分比）、鼠标左键拖拽平移、
画布模式有效区域可视化（蒙版+虚线）、高缩放下像素网格线。
缩放吸附点：25%-50%-75%-100%-125%-150%-175%-200%-225%-250%-275%-300%-400%-800%-1600%-3200%。
透明背景使用棋盘格图案。
"""

from PySide6.QtWidgets import QWidget, QPushButton, QLabel, QHBoxLayout, QApplication
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import (
    QPixmap, QPainter, QPen, QBrush, QColor, QPaintEvent,
    QWheelEvent, QMouseEvent, QPainterPath, QFont, QImage,
)

from core.models.canvas_mode import get_canvas_mode


CHECKER_SIZE = 16
CHECKER_DARK = QColor(204, 204, 204)
CHECKER_LIGHT = QColor(255, 255, 255)
OVERLAY_COLOR = QColor(0, 0, 0, 60)
DASH_PEN = QPen(QColor(255, 255, 255, 180), 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
DASH_PEN.setDashPattern([6, 3])
GRID_PEN = QPen(QColor(0, 0, 0, 30), 1)
GRID_THRESHOLD = 6.0

ZOOM_SNAPS = [
    0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
    2.0, 2.25, 2.5, 2.75, 3.0, 4.0, 8.0, 16.0, 32.0,
]
ZOOM_MIN = ZOOM_SNAPS[0]
ZOOM_MAX = ZOOM_SNAPS[-1]
WHEEL_STEP = 0.05
SNAP_TOLERANCE = 0.03  # 3% 吸附容差


def _snap_scale(scale: float) -> float:
    """将 scale 吸附到最近的吸附点（误差 < SNAP_TOLERANCE 时）"""
    for s in ZOOM_SNAPS:
        ratio = abs(scale - s) / s
        if ratio <= SNAP_TOLERANCE:
            return s
    return scale


def _is_snapped(scale: float) -> bool:
    """当前 scale 是否已吸附到某点（用于振荡保护）"""
    for s in ZOOM_SNAPS:
        if abs(scale - s) / s <= SNAP_TOLERANCE:
            return True
    return False


class _ZoomToolbar(QWidget):
    """内嵌缩放工具栏: [-] [XXX%] [+] [fit]"""

    zoom_in_clicked = Signal()
    zoom_out_clicked = Signal()
    fit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ZoomToolbar")
        self.setStyleSheet("""
            #ZoomToolbar {
                background: rgba(20, 20, 20, 220);
                border-radius: 6px;
            }
            QPushButton {
                background: rgba(60, 60, 60, 180);
                color: white;
                border: 1px solid rgba(255,255,255,40);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 12px;
                min-width: 22px;
            }
            QPushButton:hover {
                background: rgba(90, 90, 90, 200);
            }
            QPushButton:pressed {
                background: rgba(120, 120, 120, 200);
            }
            QLabel {
                background: rgba(255, 255, 255, 200);
                color: #000000;
                font-size: 14px;
                font-family: "Microsoft YaHei UI";
                border-radius: 3px;
                padding: 1px 6px;
                min-width: 44px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self.btn_out = QPushButton("\u2212")
        self.btn_out.setToolTip("缩小 (Ctrl+滚轮)")
        self.btn_out.setCursor(Qt.PointingHandCursor)
        self.btn_out.clicked.connect(self.zoom_out_clicked)

        self.label_pct = QLabel("100%")
        self.label_pct.setAlignment(Qt.AlignCenter)

        self.btn_in = QPushButton("+")
        self.btn_in.setToolTip("放大 (Ctrl+滚轮)")
        self.btn_in.setCursor(Qt.PointingHandCursor)
        self.btn_in.clicked.connect(self.zoom_in_clicked)

        self.btn_fit = QPushButton("\u2293")
        self.btn_fit.setToolTip("适应窗口")
        self.btn_fit.setCursor(Qt.PointingHandCursor)
        self.btn_fit.clicked.connect(self.fit_clicked)

        layout.addWidget(self.btn_out)
        layout.addWidget(self.label_pct)
        layout.addWidget(self.btn_in)
        layout.addWidget(self.btn_fit)

        f = self.label_pct.font()
        f.setStyleStrategy(QFont.StyleStrategy.PreferDevice)
        self.label_pct.setFont(f)

    def set_zoom_pct(self, pct: int):
        self.label_pct.setText(f"{pct}%")


class CanvasPreview(QWidget):
    """像素画预览控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._source_image = None
        self._current_fitted = None
        self._canvas_mode: str = "standard"
        self._scale: float = 1.0
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._last_mouse_pos = QPoint()
        self._crop_mode: bool = False

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(
            self.sizePolicy().Policy.Expanding,
            self.sizePolicy().Policy.Expanding,
        )

        self._toolbar = _ZoomToolbar(self)
        self._toolbar.zoom_in_clicked.connect(self._zoom_in)
        self._toolbar.zoom_out_clicked.connect(self._zoom_out)
        self._toolbar.fit_clicked.connect(self.resetView)

    def setPixmap(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._source_image = None
        self._current_fitted = None
        self._update_zoom_label()
        self.update()

    def setCanvasMode(self, mode: str):
        if self._canvas_mode != mode:
            self._canvas_mode = mode
            self.update()

    def showAtFullSize(self, pixmap: QPixmap):
        self._pixmap = pixmap
        self._scale = 1.0
        self._offset = QPoint(0, 0)
        self._update_zoom_label()
        self.update()

    def setCropMode(self, enabled: bool):
        self._crop_mode = enabled
        self.update()

    def setSourceImage(self, image, canvas_mode: str):
        self._source_image = image
        self._canvas_mode = canvas_mode
        self._rebuild_pixmap(1.0)
        self._update_zoom_label()
        self.setCropMode(True)
        self.update()

    def getFittedImage(self):
        return self._current_fitted

    def _rebuild_pixmap(self, scale: float):
        if self._source_image is None:
            return
        mode = get_canvas_mode(self._canvas_mode)
        cw, ch = mode.active_w, mode.active_h
        target_w = max(1, int(cw * scale))
        target_h = max(1, int(ch * scale))

        iw, ih = self._source_image.size
        s = max(target_w / iw, target_h / ih)
        new_w = max(1, int(iw * s))
        new_h = max(1, int(ih * s))

        from PIL import Image as PILImage
        self._current_fitted = self._source_image.resize((new_w, new_h), PILImage.LANCZOS)
        buf = self._current_fitted.tobytes("raw", "RGBA")
        qi = QImage(buf, new_w, new_h, QImage.Format_RGBA8888)
        self._pixmap = QPixmap.fromImage(qi)
        self._scale = scale

    def getCropPixels(self) -> tuple[int, int, int, int]:
        if self._current_fitted is None or self._scale <= 0:
            return (0, 0, 0, 0)
        pw = self._current_fitted.width
        ph = self._current_fitted.height
        mode = get_canvas_mode(self._canvas_mode)
        cw, ch = mode.active_w, mode.active_h

        # 裁切结果 = 图像中央的 active_w × active_h 区域
        left = max(0, (pw - cw) // 2)
        top = max(0, (ph - ch) // 2)

        from core.utils.logger import get_logger as _log
        _lg = _log("CanvasPreview")
        _lg.info(f"[getCropPixels] fitted={pw}x{ph} active={cw}x{ch} "
                 f"scale={self._scale:.3f} offset=({self._offset.x()},{self._offset.y()}) "
                 f"result=({left},{top},{left+cw},{top+ch})")
        return (left, top, left + cw, top + ch)

    def resetView(self):
        self._rebuild_pixmap(1.0)
        self._offset = QPoint(0, 0)
        self._update_zoom_label()
        self.update()

    # ---------- zoom ----------
    def _zoom_in(self):
        """+ 按钮：跳到下一个大于当前值的吸附点"""
        for s in ZOOM_SNAPS:
            if s > self._scale + 0.001:
                self._set_scale_at_center(s)
                return

    def _zoom_out(self):
        """- 按钮：跳到上一个小于当前值的吸附点"""
        for s in reversed(ZOOM_SNAPS):
            if s < self._scale - 0.001:
                self._set_scale_at_center(s)
                return

    def _set_scale_at_center(self, new_scale: float):
        """以控件中心为锚点设置缩放"""
        self._zoom_to_anchor(self.width() / 2.0, self.height() / 2.0, new_scale)

    def _zoom_to_anchor(self, anchor_x: float, anchor_y: float, new_scale: float):
        if self._source_image is not None:
            self._rebuild_pixmap(new_scale)
            self._update_zoom_label()
            self.update()
            return

        if self._pixmap is None or self._pixmap.isNull():
            self._scale = new_scale
            self._update_zoom_label()
            self.update()
            return

        pw, ph = self._pixmap.width(), self._pixmap.height()
        old_scale = self._scale
        if old_scale <= 0:
            self._scale = new_scale
            self._update_zoom_label()
            self.update()
            return

        old_center_x = (self.width() - pw * old_scale) / 2.0
        old_center_y = (self.height() - ph * old_scale) / 2.0
        px = (anchor_x - old_center_x - self._offset.x()) / old_scale
        py = (anchor_y - old_center_y - self._offset.y()) / old_scale

        self._scale = new_scale
        new_center_x = (self.width() - pw * new_scale) / 2.0
        new_center_y = (self.height() - ph * new_scale) / 2.0
        self._offset.setX(int(anchor_x - new_center_x - px * new_scale))
        self._offset.setY(int(anchor_y - new_center_y - py * new_scale))

        self._update_zoom_label()
        self.update()

    def _update_zoom_label(self):
        pct = round(self._scale * 100)
        self._toolbar.set_zoom_pct(pct)

    # ---------- paint ----------
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        self._draw_checkerboard(painter, event.rect())

        if self._pixmap is None or self._pixmap.isNull():
            painter.end()
            return

        pm = self._pixmap
        pw, ph = pm.width(), pm.height()
        sw = int(pw * self._scale)
        sh = int(ph * self._scale)

        cx = (self.width() - sw) // 2 + self._offset.x()
        cy = (self.height() - sh) // 2 + self._offset.y()
        target_rect = QRect(cx, cy, sw, sh)

        painter.drawPixmap(target_rect, pm, QRect(0, 0, pw, ph))

        if self._scale >= GRID_THRESHOLD:
            self._draw_pixel_grid(painter, target_rect, pw, ph)

        mode = get_canvas_mode(self._canvas_mode)
        if self._crop_mode:
            self._draw_crop_frame(painter, mode)
        else:
            self._draw_canvas_overlay(painter, target_rect, pw, ph, mode)

        painter.end()

    # ---------- pixel grid ----------
    def _draw_pixel_grid(self, painter: QPainter, img_rect: QRect, pw: int, ph: int):
        painter.save()
        painter.setPen(GRID_PEN)

        x0, y0 = img_rect.x(), img_rect.y()
        scale = self._scale

        # 垂直线
        vis_left = max(0, int((-self._offset.x() - img_rect.width() / 2 + self.width() / 2) / scale) if scale > 0 else 0)
        vis_right = min(pw, vis_left + int(self.width() / scale) + 2)
        vis_left = max(0, vis_left - 1)
        for col in range(int(vis_left), int(vis_right) + 1):
            lx = int(x0 + col * scale)
            painter.drawLine(lx, y0, lx, y0 + int(ph * scale))

        # 水平线
        vis_top = max(0, int((-self._offset.y() - img_rect.height() / 2 + self.height() / 2) / scale) if scale > 0 else 0)
        vis_bottom = min(ph, vis_top + int(self.height() / scale) + 2)
        vis_top = max(0, vis_top - 1)
        for row in range(int(vis_top), int(vis_bottom) + 1):
            ly = int(y0 + row * scale)
            painter.drawLine(x0, ly, x0 + int(pw * scale), ly)

        painter.restore()

    # ---------- canvas overlay ----------
    def _draw_canvas_overlay(self, painter: QPainter, img_rect: QRect, pw: int, ph: int, mode):
        painter.save()
        sx = img_rect.width() / pw if pw > 0 else 1
        sy = img_rect.height() / ph if ph > 0 else 1

        ax = img_rect.x() + int(mode.active_x * sx)
        ay = img_rect.y() + int(mode.active_y * sy)
        aw = int(mode.active_w * sx)
        ah = int(mode.active_h * sy)

        full = QRect(img_rect.x(), img_rect.y(), img_rect.width(), img_rect.height())
        active = QRect(ax, ay, aw, ah)

        overlay_path = QPainterPath()
        overlay_path.addRect(full)
        overlay_path.addRect(active)
        overlay_path.setFillRule(Qt.WindingFill)
        painter.fillPath(overlay_path, QBrush(OVERLAY_COLOR))

        painter.setPen(DASH_PEN)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(active)
        painter.restore()

    # ---------- crop frame ----------
    def _draw_crop_frame(self, painter: QPainter, mode):
        painter.save()
        cw, ch = mode.active_w, mode.active_h
        wf = self.width() * 0.7 / cw if cw > 0 else 1
        hf = self.height() * 0.7 / ch if ch > 0 else 1
        frame_scale = min(wf, hf, 2.0)
        fw = int(cw * frame_scale)
        fh = int(ch * frame_scale)
        fx = (self.width() - fw) // 2
        fy = (self.height() - fh) // 2

        from core.utils.logger import get_logger as _log
        _lg = _log("CanvasPreview")
        _lg.info(f"[draw_crop_frame] widget={self.width()}x{self.height()} "
                 f"active={cw}x{ch} frame_scale={frame_scale:.3f} "
                 f"frame=({fx},{fy},{fw},{fh})")

        frame = QRect(fx, fy, fw, fh)
        widget_rect = QRect(0, 0, self.width(), self.height())

        overlay_path = QPainterPath()
        overlay_path.addRect(widget_rect)
        overlay_path.addRect(frame)
        overlay_path.setFillRule(Qt.WindingFill)
        painter.fillPath(overlay_path, QBrush(OVERLAY_COLOR))

        painter.setPen(DASH_PEN)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(frame)
        painter.restore()

    # ---------- checkerboard ----------
    def _draw_checkerboard(self, painter: QPainter, rect: QRect):
        painter.save()
        for y in range(rect.top() // CHECKER_SIZE * CHECKER_SIZE, rect.bottom(), CHECKER_SIZE):
            for x in range(rect.left() // CHECKER_SIZE * CHECKER_SIZE, rect.right(), CHECKER_SIZE):
                color = CHECKER_LIGHT if ((x // CHECKER_SIZE) + (y // CHECKER_SIZE)) % 2 == 0 else CHECKER_DARK
                painter.fillRect(QRect(x, y, CHECKER_SIZE, CHECKER_SIZE), color)
        painter.restore()

    # ---------- events ----------
    def wheelEvent(self, event: QWheelEvent):
        if not (QApplication.keyboardModifiers() & Qt.ControlModifier):
            event.ignore()
            return

        delta = event.angleDelta().y()
        new_scale = self._scale + WHEEL_STEP if delta > 0 else self._scale - WHEEL_STEP
        new_scale = max(ZOOM_MIN, min(new_scale, ZOOM_MAX))

        # 吸附：仅在未吸附状态或已离开吸附点后触发
        snapped = _snap_scale(new_scale)
        if abs(snapped - new_scale) / snapped <= SNAP_TOLERANCE and snapped != _snap_scale(self._scale):
            new_scale = snapped

        mouse_pos = event.position()
        self._zoom_to_anchor(mouse_pos.x(), mouse_pos.y(), new_scale)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_mouse_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.pos() - self._last_mouse_pos
            self._offset += delta
            self._last_mouse_pos = event.pos()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        tb = self._toolbar
        tb_w = tb.sizeHint().width()
        tb_h = tb.sizeHint().height()
        margin = 8
        tb.setGeometry(
            self.width() - tb_w - margin,
            self.height() - tb_h - margin,
            tb_w,
            tb_h,
        )
        tb.raise_()

    # ---------- helpers ----------
    def _fit_to_widget(self):
        if self._pixmap is None or self._pixmap.isNull():
            return
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw <= 0 or ph <= 0:
            return
        w_scale = (self.width() - 20) / pw
        h_scale = (self.height() - 20) / ph
        self._scale = min(w_scale, h_scale, 2.0)
        self._offset = QPoint(0, 0)
        self.setCursor(Qt.OpenHandCursor)
