import math
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, 
    QFrame, QTableWidgetItem, QCheckBox, QSizePolicy, QLayout
)
from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, pyqtProperty, 
    QPointF, QRect, QRectF, pyqtSignal, QEvent, QTimer
)
from PyQt6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QPixmap, QIcon
)

from constants import AppColors

# ============================================================================
# SPINNER DE CHARGEMENT (CERCLE ROTATIF)
# ============================================================================
class StatusSpinner(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet(f"color: {AppColors.FOCUS_ORANGE}; font-weight: bold; font-size: 12pt; font-family: 'Segoe UI Symbol', 'Arial';")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chars = ["◐", "◓", "◑", "◒"]
        self._idx = 0
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._rotate)
        self.setText("") 

    def _rotate(self):
        self.setText(self.chars[self._idx])
        self._idx = (self._idx + 1) % len(self.chars)

    def start(self): self.timer.start()
    def stop(self): self.timer.stop(); self.setText("")

# ============================================================================
# TABLE ITEM (TRI NUMÉRIQUE)
# ============================================================================
class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            text_self = self.text().replace('€', '').replace(' ', '').replace(',', '.').strip()
            text_other = other.text().replace('€', '').replace(' ', '').replace(',', '.').strip()
            return float(text_self) < float(text_other)
        except ValueError: 
            return super().__lt__(other)

# ============================================================================
# TOGGLE SWITCH
# ============================================================================
class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None, width=40, height=22, active_color=None, inactive_color=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.active_color = active_color if active_color else AppColors.SWITCH_ON
        self.inactive_color = inactive_color if inactive_color else AppColors.SWITCH_OFF
        self._circle_position = 3
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setDuration(200)
        self.stateChanged.connect(self.start_transition)

    @pyqtProperty(float)
    def circle_position(self): return self._circle_position
    @circle_position.setter
    def circle_position(self, pos): self._circle_position = pos; self.update()

    def start_transition(self, state):
        self.animation.stop()
        if state: self.animation.setEndValue(self.width() - (self.height() - 3)) 
        else: self.animation.setEndValue(3)
        self.animation.start()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_color = QColor(self.active_color if self.isChecked() else self.inactive_color)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(track_color))
        p.drawRoundedRect(0, 0, self.width(), self.height(), self.height()//2, self.height()//2)
        p.setBrush(QBrush(QColor(AppColors.SWITCH_CIRCLE)))
        radius = self.height() - 6
        p.drawEllipse(int(self._circle_position), 3, radius, radius)
        p.end()

    def hitButton(self, pos): return self.contentsRect().contains(pos)

# ============================================================================
# BOUTONS PERSONNALISÉS
# ============================================================================
class ModernButton(QPushButton):
    rightClicked = pyqtSignal()
    def __init__(self, text, bg_color, command=None, height=40, radius=6, text_color="white"):
        super().__init__(text)
        self.setFixedHeight(height)
        if command: self.clicked.connect(command)
        hover_color = self.adjust_color(bg_color, -35) 
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: {text_color}; border-radius: {radius}px; font-weight: bold; font-size: 10pt; border: none; }}
            QPushButton:hover {{ background-color: {hover_color}; }}
            QPushButton:disabled {{ background-color: #bdc3c7; color: #7f8c8d; }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton: self.rightClicked.emit()
        super().mousePressEvent(event)

    def adjust_color(self, h, f):
        if not h.startswith("#"): return h
        r = int(h[1:3], 16) + f; g = int(h[3:5], 16) + f; b = int(h[5:7], 16) + f
        return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"

class RoundedLabelButton(QPushButton):
    def __init__(self, text, bg_color, text_color="black", command=None, height=26, radius=6, centered=False):
        super().__init__(text)
        self.setFixedHeight(height)
        if command: self.clicked.connect(command)
        align_style = "text-align: center; padding-left: 0px;" if centered else "text-align: left; padding-left: 10px;"
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {bg_color}; color: {text_color}; border-radius: {radius}px; font-family: "Segoe UI"; font-size: 9pt; {align_style} border: none; font-weight: normal; outline: none; }}
            QPushButton:hover, QPushButton:focus {{ border: none; outline: none; }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

# ============================================================================
# GROUPES PLIABLES (ACCORDÉON)
# ============================================================================
class FilterGroup(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self); self.layout.setContentsMargins(0, 0, 0, 0); self.layout.setSpacing(0)
        self.btn_header = QPushButton(); self.btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_header.setStyleSheet("QPushButton { background-color: transparent; border: none; padding: 2px; }")
        self.btn_header.clicked.connect(self.toggle)
        header_layout = QHBoxLayout(self.btn_header); header_layout.setContentsMargins(5, 5, 5, 5) 
        self.lbl_title = QLabel(title); self.lbl_title.setStyleSheet("color: #bdc3c7; font-weight: bold; font-size: 9pt; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_title, 1)
        self.lbl_arrow = QLabel("▼"); self.lbl_arrow.setAlignment(Qt.AlignmentFlag.AlignCenter); self.lbl_arrow.setStyleSheet("color: #bdc3c7; font-weight: bold; font-size: 8pt; border: none; background: transparent;")
        header_layout.addWidget(self.lbl_arrow)
        self.btn_header.installEventFilter(self)
        self.layout.addWidget(self.btn_header)
        self.content_area = QWidget(); self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(10, 2, 0, 2); self.content_layout.setSpacing(2)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.layout.addWidget(self.content_area)
        l = self.layout; l.addSpacing(4)
        self.sep = QFrame(); self.sep.setFixedHeight(1); self.sep.setStyleSheet(f"background:{AppColors.SEPARATOR}"); l.addWidget(self.sep)
        l.addSpacing(1)
        self.is_expanded = True

    def eventFilter(self, source, event):
        if source == self.btn_header:
            if event.type() == QEvent.Type.Enter:
                self.lbl_title.setStyleSheet("color: white; font-weight: bold; font-size: 9pt; border: none; background: transparent;")
                self.lbl_arrow.setStyleSheet("color: white; font-weight: bold; font-size: 8pt; border: none; background: transparent;")
            elif event.type() == QEvent.Type.Leave:
                self.lbl_title.setStyleSheet("color: #bdc3c7; font-weight: bold; font-size: 9pt; border: none; background: transparent;")
                self.lbl_arrow.setStyleSheet("color: #bdc3c7; font-weight: bold; font-size: 8pt; border: none; background: transparent;")
        return super().eventFilter(source, event)

    def toggle(self): self.set_expanded(not self.is_expanded)
    def set_expanded(self, expanded):
        self.is_expanded = expanded; self.content_area.setVisible(self.is_expanded)
        self.lbl_arrow.setText("▼" if self.is_expanded else "▶")

# ============================================================================
# ICONES & CHARTS
# ============================================================================
class IconManager:
    def __init__(self): self.cache = {}
    def get_icon(self, unicode_char, color_hex=None):
        key = f"{unicode_char}_{color_hex}"
        if key in self.cache: return self.cache[key]
        size = 32; pixmap = QPixmap(size, size); pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont("Segoe UI Emoji", 18); painter.setFont(font)
        if color_hex: painter.setPen(QColor(color_hex))
        else: painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, unicode_char); painter.end()
        icon = QIcon(pixmap); self.cache[key] = icon; return icon

class RingChart(QWidget):
    def __init__(self, parent=None, size=100):
        super().__init__(parent); self.setFixedSize(size, size); self.setMouseTracking(True)
        self.data = {}; self.colors = {}; self.total = 0; self.hovered_key = None; self.slices = []; self._anim_progress = 0.0
        self.animation = QPropertyAnimation(self, b"anim_progress"); self.animation.setDuration(1000); self.animation.setEasingCurve(QEasingCurve.Type.OutQuart) 
    @pyqtProperty(float)
    def anim_progress(self): return self._anim_progress
    @anim_progress.setter
    def anim_progress(self, value): self._anim_progress = value; self.update()
    def set_data(self, data_dict, color_map):
        if self.data == data_dict: return
        self.data = data_dict; self.colors = color_map; self.total = sum(data_dict.values())
        self.animation.stop(); self.animation.setStartValue(0.0); self.animation.setEndValue(1.0); self.animation.start()
    def mouseMoveEvent(self, event):
        center = QPointF(self.width() / 2, self.height() / 2); pos = event.position(); dx = pos.x() - center.x(); dy = pos.y() - center.y(); dist = math.sqrt(dx*dx + dy*dy)
        outer_radius = min(self.width(), self.height()) / 2 - 5; inner_radius = outer_radius * 0.6
        if dist < inner_radius or dist > outer_radius:
            if self.hovered_key is not None: self.hovered_key = None; self.update()
            return
        angle_rad = math.atan2(-dy, dx); angle_deg = math.degrees(angle_rad); 
        if angle_deg < 0: angle_deg += 360
        found = None; mouse_angle_qt = angle_deg 
        for key, start, span in self.slices:
            s_angle = start / 16.0; e_angle = (start + span) / 16.0; norm_s = s_angle % 360; norm_e = e_angle % 360; norm_m = mouse_angle_qt % 360
            if span < 0: 
                if norm_e < norm_s:
                    if norm_e <= norm_m <= norm_s: found = key
                else: 
                    if norm_m <= norm_s or norm_m >= norm_e: found = key
            if found: break
        if self.hovered_key != found: self.hovered_key = found; self.update()
    def leaveEvent(self, event): self.hovered_key = None; self.update()
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect_size = min(self.width(), self.height()); margin = 15 
        rect = QRectF(margin, margin, rect_size - 2*margin, rect_size - 2*margin)
        if self.total == 0:
            painter.setPen(QPen(QColor("#7f8c8d"), 4)); painter.drawArc(rect, 0, 360 * 16); painter.end(); return
        rot_offset = 45 * 16 * (1.0 - self._anim_progress); start_angle = 90 * 16 - rot_offset 
        self.slices = []; base_width = 8 * self._anim_progress 
        for key, val in self.data.items():
            if val == 0: continue
            full_span = - (val / self.total) * 360 * 16; animated_span = full_span * self._anim_progress
            color = QColor(self.colors.get(key, "#bdc3c7")); is_hover = (key == self.hovered_key)
            current_width = base_width + (6 if is_hover else 0)
            if is_hover: color = color.lighter(120)
            pen = QPen(color, max(0.1, current_width)); pen.setCapStyle(Qt.PenCapStyle.FlatCap); painter.setPen(pen)
            painter.drawArc(rect, int(start_angle), int(animated_span))
            final_start_theory = 90*16 + (start_angle - (90*16 - rot_offset))
            self.slices.append((key, final_start_theory, full_span)); start_angle += animated_span
        if self.hovered_key:
            val = self.data[self.hovered_key]; painter.setPen(Qt.GlobalColor.white)
            font_k = QFont("Segoe UI", 9); painter.setFont(font_k)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.hovered_key}\n")
            font_v = QFont("Segoe UI", 12, QFont.Weight.Bold); painter.setFont(font_v)
            painter.drawText(rect.translated(0, 15), Qt.AlignmentFlag.AlignCenter, f"{val}")
        else:
            painter.setPen(QColor("#bdc3c7")); painter.setFont(QFont("Segoe UI", 10)); painter.setOpacity(self._anim_progress)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"Total\n{self.total}"); painter.end()