"""Card look for the job list: bold title, muted company line, coloured fit pill with the reason."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate

FIT_ROLE = Qt.ItemDataRole.UserRole + 1
CHIPS_ROLE = Qt.ItemDataRole.UserRole + 2
CARD_HEIGHT = 96

_WORK_MODEL = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "Vor Ort"}
_WORKING_TIME = {"fulltime": "Vollzeit", "parttime": "Teilzeit", "contract": "Befristet", "temporary": "Befristet",
                 "internship": "Praktikum", "permanent": "Unbefristet", "minijob": "Minijob"}
_SOURCES = {"bundesagentur": "Bundesagentur", "stepstone": "StepStone", "xing": "XING",
            "linkedin": "LinkedIn", "indeed": "Indeed"}


def job_chips(job) -> list[str]:
    """Short facts shown as chips on a card: work model, working time, source."""
    chips = []
    model = _WORK_MODEL.get((getattr(job, "remote_type", "") or "").lower())
    if model:
        chips.append(model)
    kind = (getattr(job, "employment_type", "") or "").strip()
    if kind and kind.lower() not in {"nan", "none", "null"}:
        first = kind.split(",")[0].strip()
        chips.append(_WORKING_TIME.get(first.lower().replace("-", "").replace(" ", ""), first)[:14])
    source = (getattr(job, "source", "") or "").strip()
    if source:
        chips.append(_SOURCES.get(source.lower(), source[:14]))
    return chips


def _colors():
    from desktop.design_system.tokens import tokens_for_theme

    app = QApplication.instance()
    theme = app.property("kk_palette_theme") if app is not None else None
    return tokens_for_theme("dark" if theme == "dark" else "light").colors


class JobCardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), CARD_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        colors = _colors()
        lines = (index.data(Qt.ItemDataRole.DisplayRole) or "").split("\n")
        title, meta, fit = (lines + ["", "", ""])[:3]
        fit_key = index.data(FIT_ROLE) or ""
        accent = {"sehr_passend": colors.success, "passend": colors.success, "teilweise_passend": colors.warning,
                  "nicht_passend": colors.error}.get(fit_key, colors.muted)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.fillPath(path, QColor(colors.primary).lighter(190) if selected and False else QColor(colors.surface))
        if selected or hovered:
            tint = QColor(colors.primary)
            tint.setAlpha(34 if selected else 16)
            painter.fillPath(path, tint)
        painter.setPen(QPen(QColor(colors.primary if selected else colors.border), 2 if selected else 1))
        painter.drawPath(path)
        bar = QPainterPath()
        bar.addRoundedRect(QRectF(rect.left(), rect.top() + 10, 4, rect.height() - 20), 2, 2)
        painter.fillPath(bar, QColor(accent))

        left, right = rect.left() + 16, rect.right() - 12
        width = int(right - left)
        base = option.font

        title_font = QFont(base)
        title_font.setBold(True)
        if base.pointSizeF() > 0:
            title_font.setPointSizeF(base.pointSizeF() + 1.5)
        else:  # the app sets pixel sizes; adding to -1 points gave a hair-thin title
            title_font.setPixelSize(max(12, base.pixelSize()) + 2)
        painter.setFont(title_font)
        painter.setPen(QColor(colors.text))
        painter.drawText(QRectF(left, rect.top() + 8, width, 24), Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(title_font).elidedText(title, Qt.TextElideMode.ElideRight, width))

        meta_font = QFont(base)
        chip_font = QFont(base)
        if base.pointSizeF() > 0:
            chip_font.setPointSizeF(max(7.0, base.pointSizeF() - 1.0))
        else:
            chip_font.setPixelSize(max(9, base.pixelSize() - 2))
        chip_metrics = QFontMetrics(chip_font)
        chips_width = 0
        chip_boxes = []
        x_right = right
        for text in reversed(index.data(CHIPS_ROLE) or []):
            chip_w = chip_metrics.horizontalAdvance(text) + 14
            x_right -= chip_w
            chip_boxes.append((text, QRectF(x_right, rect.top() + 35, chip_w, 20)))
            x_right -= 6
            chips_width += chip_w + 6
        painter.setFont(meta_font)
        painter.setPen(QColor(colors.muted))
        meta_width = max(60, width - chips_width - 8)
        painter.drawText(QRectF(left, rect.top() + 33, meta_width, 20), Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(meta_font).elidedText(meta, Qt.TextElideMode.ElideRight, int(meta_width)))
        painter.setFont(chip_font)
        for text, box in chip_boxes:
            chip_path = QPainterPath()
            chip_path.addRoundedRect(box, 10, 10)
            fill = QColor(colors.muted)
            fill.setAlpha(34)
            painter.fillPath(chip_path, fill)
            painter.setPen(QColor(colors.muted))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

        label, _, reason = fit.partition(" — ")
        pill_font = QFont(base)
        pill_font.setBold(True)
        if base.pointSizeF() > 0:
            pill_font.setPointSizeF(max(7.0, base.pointSizeF() - 0.5))
        else:
            pill_font.setPixelSize(max(10, base.pixelSize() - 1))
        metrics = QFontMetrics(pill_font)
        pill_w = metrics.horizontalAdvance(label) + 20
        pill = QRectF(left, rect.bottom() - 34, pill_w, 22)
        fill = QColor(accent)
        fill.setAlpha(40)
        pill_path = QPainterPath()
        pill_path.addRoundedRect(pill, 11, 11)
        painter.fillPath(pill_path, fill)
        painter.setFont(pill_font)
        painter.setPen(QColor(colors.text))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, label)

        painter.setFont(meta_font)
        painter.setPen(QColor(colors.muted))
        reason_left = pill.right() + 10
        painter.drawText(QRectF(reason_left, pill.top(), right - reason_left, pill.height()),
                         Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(meta_font).elidedText(reason, Qt.TextElideMode.ElideRight, int(right - reason_left)))
        painter.restore()
