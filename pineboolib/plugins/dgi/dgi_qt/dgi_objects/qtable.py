# -*- coding: utf-8 -*-

from PyQt5 import QtWidgets, QtCore, Qt  # type: ignore
from pineboolib.core import decorators
from pineboolib.core.utils.utils_base import format_double


from PyQt5.QtWidgets import QAbstractItemView  # type: ignore
from pineboolib.plugins.dgi.dgi_qt.dgi_objects.qgroupbox import QGroupBox
from typing import Optional
from typing import Any, TypeVar

_T0 = TypeVar("_T0")

_T0 = TypeVar("_T0")


class QTable(QtWidgets.QTableWidget):

    lineaActual = None
    CurrentChanged = QtCore.pyqtSignal(int, int)
    doubleClicked = QtCore.pyqtSignal(int, int)
    clicked = QtCore.pyqtSignal(int, int)
    valueChanged = QtCore.pyqtSignal(int, int)
    read_only_cols = None
    read_only_rows = None
    cols_list = None
    resize_policy = None

    Default = 0
    Manual = 1
    AutoOne = 2
    AutoOneFit = 3
    sort_column_ = None

    def __init__(self, parent: Optional[QGroupBox] = None, name: None = None) -> None:
        super(QTable, self).__init__(parent)
        if not parent:
            self.setParent(self.parentWidget())

        if name:
            self.setObjectName(name)

        self.cols_list = []
        self.lineaActual = -1
        self.currentCellChanged.connect(self.currentChanged_)
        self.cellDoubleClicked.connect(self.doubleClicked_)
        self.cellClicked.connect(self.simpleClicked_)
        self.itemChanged.connect(self.valueChanged_)
        self.read_only_cols = []
        self.read_only_rows = []
        self.resize_policy = 0  # Default
        self.sort_column_ = None

    def currentChanged_(self, current_row, current_column, previous_row, previous_column) -> None:
        if current_row > -1 and current_column > -1:
            self.CurrentChanged.emit(current_row, current_column)
            pass

    def doubleClicked_(self, f, c) -> None:
        self.doubleClicked.emit(f, c)

    def simpleClicked_(self, f, c) -> None:
        self.clicked.emit(f, c)

    @decorators.NotImplementedWarn
    def setResizePolicy(self, pol):
        self.resize_policy = pol

    def __getattr__(self, name: str) -> Any:
        if name == "Multi":
            return self.MultiSelection
        elif name == "SpreadSheet":
            return 999
        else:
            print("FIXME:QTable:", name)
            return getattr(QtCore.Qt, name, None)

    def valueChanged_(self, item=None) -> None:

        if item and self.text(item.row(), item.column()) != "":
            self.valueChanged.emit(item.row(), item.column())

    def numRows(self) -> Any:
        return self.rowCount()

    def numCols(self) -> Any:
        return self.columnCount()

    def setCellAlignment(self, row, col, alig_) -> None:
        self.item(row, col).setTextAlignment(alig_)

    def setNumCols(self, n: int) -> None:
        self.setColumnCount(n)
        self.setColumnLabels(",", ",".join(self.cols_list))

    def setNumRows(self, n: int) -> None:
        self.setRowCount(n)

    def setReadOnly(self, b) -> None:
        if b:
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        else:
            self.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)

    def selectionMode(self) -> Any:
        return super(QTable, self).selectionMode()

    def setFocusStyle(self, m: str) -> None:
        if isinstance(m, int):
            return
        else:
            self.setStyleSheet(m)

    def setColumnLabels(self, separador: str, lista: str) -> None:
        array_ = lista.split(separador)
        self.cols_list = []
        for i in range(self.columnCount()):
            if len(array_) > i:
                self.cols_list.append(array_[i])
        self.setHorizontalHeaderLabels(self.cols_list)

    def setRowLabels(self, separator, lista) -> None:
        array_ = lista.split(separator)
        self.setVerticalHeaderLabels(array_)

    def clear(self) -> None:
        super().clear()
        for i in range(self.rowCount()):
            self.removeRow(i)
        self.setHorizontalHeaderLabels(self.cols_list)
        self.setRowCount(0)

    def setSelectionMode(self, mode: "QAbstractItemView.SelectionMode") -> None:
        if mode == 999:
            self.setAlternatingRowColors(True)
        else:
            super().setSelectionMode(mode)

    def setColumnStrechable(self, col, b) -> None:
        if b:
            self.horizontalHeader().setSectionResizeMode(col, Qt.QHeaderView.Stretch)
        else:
            self.horizontalHeader().setSectionResizeMode(col, Qt.QHeaderView.AdjustToContents)

    def setHeaderLabel(self, l) -> None:
        self.cols_list.append(l)
        self.setColumnLabels(",", ",".join(self.cols_list))

    def insertRows(self, numero, n: int = 1) -> None:
        for r in range(n):
            self.insertRow(numero)

    def text(self, row, col) -> Any:
        if row is None:
            return
        return self.item(row, col).text() if self.item(row, col) else None

    def setText(self, row, col, value) -> None:
        prev_item = self.item(row, col)
        if prev_item:
            bg_color = prev_item.background()

        right = True if isinstance(value, (int, float)) else False

        if right:
            value = value if isinstance(value, int) else format_double(value, len("%s" % value), 2)

        item = QtWidgets.QTableWidgetItem(str(value))

        if right:
            item.setTextAlignment(QtCore.Qt.AlignVCenter + QtCore.Qt.AlignRight)

        self.setItem(row, col, item)

        if prev_item:
            self.setCellBackgroundColor(row, col, bg_color)

        new_item = self.item(row, col)

        if new_item is not None:
            if row in self.read_only_rows or col in self.read_only_cols:
                new_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            else:
                new_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable)

    def setCellWidget(self, row, col, obj) -> None:
        super().setCellWidget(row, col, obj)

        widget = self.cellWidget(row, col)
        if widget is not None:
            if row in self.read_only_rows or col in self.read_only_cols:
                widget.setEnabled(False)

    def adjustColumn(self, k) -> None:
        self.horizontalHeader().setSectionResizeMode(k, QtWidgets.QHeaderView.ResizeToContents)

    def setRowReadOnly(self, row, b) -> None:
        if b:
            if row in self.read_only_rows:
                return
            else:
                self.read_only_rows.append(row)
        else:
            if row in self.read_only_rows:
                self.read_only_rows.remove(row)
            else:
                return  # Ya esta en False la row

        for col in range(self.columnCount()):
            item = self.item(row, col)
            if item:
                item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled) if b else item.setFlags(
                    QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable
                )

    def setColumnReadOnly(self, col, b) -> None:
        if b:
            if col in self.read_only_cols:
                return
            else:
                self.read_only_cols.append(col)
        else:
            if col in self.read_only_cols:
                self.read_only_cols.remove(col)
            else:
                return

        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item:
                item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled) if b else item.setFlags(
                    QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable
                )

    @decorators.NotImplementedWarn
    def setLeftMargin(self, n):
        pass

    def setCellBackgroundColor(self, row, col, color) -> None:
        item = self.item(row, col)

        if item is not None and color:
            item.setBackground(color)

    def getSorting(self) -> Any:
        return self.sort_column_

    def setSorting(self, col) -> None:
        if not super().isSortingEnabled():
            super().setSortingEnabled(True)
        super().sortByColumn(col, QtCore.Qt.AscendingOrder)
        self.sort_column_ = col

    sorting = property(getSorting, setSorting)

    def editCell(self, row, col) -> None:
        self.editItem(self.item(row, col))
