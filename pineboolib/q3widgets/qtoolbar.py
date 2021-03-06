"""Qtoolbar module."""
# -*- coding: utf-8 -*-
from PyQt5 import QtWidgets  # type: ignore


class QToolBar(QtWidgets.QToolBar):
    """QToolBar class."""

    _label: str

    def setLabel(self, l: str) -> None:
        """Set label."""
        self._label = l

    def getLabel(self) -> str:
        """Get label."""
        return self._label

    label = property(getLabel, setLabel)
