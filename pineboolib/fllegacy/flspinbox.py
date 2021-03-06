"""Flspinbox module."""
# -*- coding: utf-8 -*-

from pineboolib.q3widgets import qspinbox

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt5 import QtWidgets  # noqa: F401


class FLSpinBox(qspinbox.QSpinBox):
    """FLSpinBox class."""

    def __init__(self, parent: Optional["QtWidgets.QWidget"] = None) -> None:
        """Inicialize."""
        super().__init__(parent)
        # editor()setAlignment(Qt::AlignRight);

    def setMaxValue(self, v: int) -> None:
        """Set maximum value."""

        self.setMaximum(v)

    def getValue(self) -> int:
        """Return actual value."""

        return super().value()

    def setValue(self, val: int) -> None:
        """Set a value."""
        super().setValue(val)

    value: Any = property(getValue, setValue)  # type: ignore
    text: Any = value
