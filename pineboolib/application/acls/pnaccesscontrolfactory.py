# -*- coding: utf-8 -*-
"""
PNAccessControlFactory Module.

Manage ACLs between different application objects.
"""
from PyQt5 import QtWidgets

from pineboolib.application.metadata import pntablemetadata
from . import pnaccesscontrol


from typing import Dict, Any, Optional, cast

import logging

LOGGER = logging.getLogger(__name__)


class PNAccessControlMainWindow(pnaccesscontrol.PNAccessControl):
    """PNAccessControlMainWindow Class."""

    def __init__(self) -> None:
        """Inicialize."""

        super(PNAccessControlMainWindow, self).__init__()

    def type(self) -> str:
        """Return target type."""

        return "mainwindow"

    def processObject(self, main_window: Optional[QtWidgets.QMainWindow]) -> None:
        """Process the object."""

        if main_window is None:
            return
        list1 = main_window.findChildren(QtWidgets.QAction)

        if self._perm != "":
            for action in list1:
                act = cast(QtWidgets.QAction, action)
                if act.objectName() in self._acos_perms.keys():
                    continue
                if self._perm in ["-w", "--"]:
                    act.setVisible(False)

        for a_name, perm in self._acos_perms.items():
            for child in list1:
                wid = cast(QtWidgets.QWidget, child)
                if wid.objectName() == a_name:
                    if perm in ["-w", "--"]:
                        wid.setVisible(False)

    def setFromObject(self, object: Any) -> None:
        """Not implemented jet."""
        LOGGER.warning("PNAccessControlMainWindow::setFromObject %s", "No implementado todavía.")


class PNAccessControlForm(pnaccesscontrol.PNAccessControl):
    """PNAccessControlForm Class."""

    def __init__(self) -> None:
        """Inicialize."""

        super().__init__()
        from PyQt5 import QtGui, QtWidgets

        self.pal = QtGui.QPalette()
        palette_ = QtWidgets.qApp.palette()  # type: ignore[misc] # noqa: F821
        background_color = palette_.color(QtGui.QPalette.Active, QtGui.QPalette.Background)
        self.pal.setColor(QtGui.QPalette.Foreground, background_color)
        self.pal.setColor(QtGui.QPalette.Text, background_color)
        self.pal.setColor(QtGui.QPalette.ButtonText, background_color)
        self.pal.setColor(QtGui.QPalette.Base, background_color)
        self.pal.setColor(QtGui.QPalette.Background, background_color)

    def type(self) -> str:
        """Return target type."""
        return "form"

    def processObject(self, widget: Optional[QtWidgets.QWidget]) -> None:
        """
        Process objects that are of the FLFormDB class.

        Only control the children of the object that are of the QWidget class, and only
        allows to make them not visible or not editable. Actually do them
        not visible means that they are not editable and modifying the palette to
        that the entire region of the component be shown in black. The permits
        which accepts are:

        - "-w" or "--" (no_read / write or no_read / no_write) -> not visible
        - "r-" (read / no_write) -> not editable

        This allows any component of an AbanQ form (FLFormDB,
        FLFormRecordDB and FLFormSearchDB) can be made not visible or not editable for convenience.
        """
        if widget is None:
            return

        if self._perm != "":
            for children in widget.findChildren(QtWidgets.QWidget):
                child = cast(QtWidgets.QWidget, children)
                if child.objectName() in self._acos_perms.keys():
                    continue

                if self._perm in ("-w", "--"):
                    child.setPalette(self.pal)
                    child.setDisabled(True)
                    child.hide()
                    continue

                elif self._perm == "r-":
                    child.setDisabled(True)

        for object_name in self._acos_perms.keys():
            child = cast(QtWidgets.QWidget, widget.findChild(QtWidgets.QWidget, object_name))
            if child:
                perm = self._acos_perms[object_name]
                if perm in ("-w", "--"):
                    child.setPalette(self.pal)
                    child.setDisabled(True)
                    child.hide()
                    continue

                if perm == "r-":
                    child.setDisabled(True)

            else:
                LOGGER.warning(
                    "PNAccessControlFactory: No se encuentra el control %s para procesar ACLS.",
                    object_name,
                )

    def setFromObject(self, object) -> None:
        """Not implemented jet."""
        LOGGER.warning("PNAccessControlForm::setFromObject %s No implementado todavía.", object)


class PNAccessControlTable(pnaccesscontrol.PNAccessControl):
    """PNAccessControlTable Class."""

    def __init__(self) -> None:
        """Inicialize."""

        super().__init__()
        self._acos_perms: Dict[str, str] = {}

    def type(self) -> str:
        """Return target type."""

        return "table"

    def processObject(self, table_metadata: "pntablemetadata.PNTableMetaData") -> None:
        """Process pntablemetadata.PNTableMetaData belonging to a table."""

        mask_perm = 0
        has_acos = True if self._acos_perms else False

        if self._perm:
            if self._perm[0] == "r":
                mask_perm += 2
            if self._perm[1] == "w":
                mask_perm += 1
        elif has_acos:
            mask_perm = 3
        else:
            return

        field_perm = ""
        mask_field_perm = 0

        fields_list = table_metadata.fieldList()

        for field in fields_list:
            mask_field_perm = mask_perm
            if has_acos and (field.name() in self._acos_perms.keys()):
                field_perm = self._acos_perms[field.name()]
                mask_field_perm = 0
                if field_perm[0] == "r":
                    mask_field_perm += 2

                if field_perm[1] == "w":
                    mask_field_perm += 1

            if mask_field_perm == 0:
                field.setVisible(False)
                field.setEditable(False)
            elif mask_field_perm == 1:
                field.setVisible(False)
                field.setEditable(True)
            elif mask_field_perm == 2:
                field.setVisible(True)
                field.setEditable(False)
            elif mask_field_perm == 3:
                field.setVisible(True)
                field.setEditable(True)

    def setFromObject(self, table_mtd: Optional["pntablemetadata.PNTableMetaData"]) -> None:
        """Apply permissions from a pntablemetadata.PNTableMetaData."""

        if table_mtd is None:
            return

        if self._acos_perms:
            self._acos_perms.clear()

        self._acos_perms = {}

        for field in table_mtd.fieldList():
            perm_read = "-"
            perm_write = "-"
            if field.visible():
                perm_read = "r"
            if field.editable():
                perm_write = "w"
            self._acos_perms[field.name()] = "%s%s" % (perm_read, perm_write)


class PNAccessControlFactory(object):
    """PNAccessControlFactory Class."""

    def create(self, type_: str) -> pnaccesscontrol.PNAccessControl:
        """Create a control instance according to the type that we pass."""

        if type_ is None:
            raise ValueError("type_ must be set")

        if type_ == "mainwindow":
            return PNAccessControlMainWindow()
        elif type_ == "form":
            return PNAccessControlForm()
        elif type_ == "table":
            return PNAccessControlTable()

        raise ValueError("type_ %r unknown" % type_)

    def type(self, obj: Any) -> str:
        """Return the type of instance target."""

        if obj is None:
            LOGGER.warning("NO OBJ")

        ret_ = ""

        if isinstance(obj, QtWidgets.QMainWindow):
            ret_ = "mainwindow"
        elif isinstance(obj, pntablemetadata.PNTableMetaData):
            ret_ = "table"
        elif isinstance(obj, QtWidgets.QDialog):
            ret_ = "form"

        return ret_
