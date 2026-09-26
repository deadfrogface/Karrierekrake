"""Wrapping flow layout for chips / tags (no horizontal clip)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """Left-to-right, top-to-bottom wrap — items keep their sizeHint width."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = 0,
        h_spacing: int = 8,
        v_spacing: int = 8,
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._hspace = int(h_spacing)
        self._vspace = int(v_spacing)
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        line_height = 0
        space_x = self._hspace
        space_y = self._vspace
        max_right = effective.right()
        avail = max(48, effective.width())

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisible():
                continue
            hint = item.sizeHint()
            # Cap ultra-long pills to the line width so text wraps instead of
            # forcing horizontal scroll. Never mutate widgets during height-for-width.
            w = min(max(hint.width(), 1), avail)
            h = max(hint.height(), 1)
            if hint.width() > avail:
                w = avail
                if widget is not None and widget.hasHeightForWidth():
                    h = max(h, int(widget.heightForWidth(avail)))
                if not test_only and widget is not None:
                    widget.setMaximumWidth(avail)
            elif not test_only and widget is not None:
                # Restore natural width after a previous narrow pass.
                widget.setMaximumWidth(16777215)
            next_x = x + w + space_x
            if line_height > 0 and x > effective.x() and next_x - space_x > max_right + 1:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + w + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x = next_x
            line_height = max(line_height, h)

        return y + line_height - rect.y() + bottom


class FlowHost(QWidget):
    """QWidget wrapper so parent layouts honor FlowLayout height-for-width."""

    def __init__(
        self, *, h_spacing: int = 8, v_spacing: int = 8, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._flow = FlowLayout(self, h_spacing=h_spacing, v_spacing=v_spacing)
        self.setLayout(self._flow)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def flow(self) -> FlowLayout:
        return self._flow

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._flow.heightForWidth(width)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, max(24, self.heightForWidth(200)))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, max(24, self._flow.minimumSize().height()))
