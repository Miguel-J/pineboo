"""Numberedit module."""

# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QWidget  # type: ignore
from .qlineedit import QLineEdit
from .qlabel import QLabel
from .qhboxlayout import QHBoxLayout
from PyQt5.Qt import QDoubleValidator  # type: ignore
from typing import Any, SupportsFloat, SupportsInt, Union, cast


class NumberEdit(QWidget):
    """
    NumberEdit class.
    """

    def __init__(self) -> None:
        """Inicialize."""

        super(NumberEdit, self).__init__()

        self.line_edit = QLineEdit(self)
        self.label_line_edit = QLabel(self)
        self.label_line_edit.setMinimumWidth(150)
        lay = QHBoxLayout(self)
        lay.addWidget(self.label_line_edit)
        lay.addWidget(self.line_edit)
        lay.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lay)
        self.validator = QDoubleValidator()
        self.line_edit.setValidator(self.validator)

    def getValue(self) -> str:
        """Return actual value."""

        return self.line_edit.getText()

    def setValue(self, value: Any) -> None:
        """Set value."""

        if value in ["", None]:
            return

        self.line_edit.setText(value)

    def getDecimals(self) -> int:
        """Return decimals."""

        return cast(QDoubleValidator, self.line_edit.validator()).decimals()

    def setDecimals(self, decimals: Union[bytes, str, SupportsInt]) -> None:
        """Set decimals."""

        cast(QDoubleValidator, self.line_edit.validator()).setDecimals(int(decimals))

    def setMinimum(self, min: Union[bytes, str, SupportsFloat]) -> None:
        """Set minimum value."""

        if min in ["", None]:
            return

        cast(QDoubleValidator, self.line_edit.validator()).setBottom(float(min))

    def getMinimum(self) -> Union[int, float]:
        """Return minimum value."""

        return cast(QDoubleValidator, self.line_edit.validator()).bottom()

    def getMaximum(self) -> Union[int, float]:
        """Return maximum value."""

        return cast(QDoubleValidator, self.line_edit.validator()).top()

    def setMaximum(self, max: Union[bytes, str, SupportsFloat]) -> Any:
        """Set maximum value."""

        if max in ["", None]:
            return

        return cast(QDoubleValidator, self.line_edit.validator()).setTop(float(max))

    def getLabel(self) -> str:
        """Return dialog label."""

        return self.label_line_edit.get_text()

    def setLabel(self, label: str) -> None:
        """Set dialog label."""

        self.label_line_edit.setText(label)

    label = property(getLabel, setLabel)
    value = property(getValue, setValue)
    decimals = property(getDecimals, setDecimals)
    mimimum = property(getMinimum, setMinimum)
    maximum = property(getMaximum, setMaximum)
