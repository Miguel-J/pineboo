"""Formdbwidget module."""
# # -*- coding: utf-8 -*-
from PyQt5 import QtWidgets, QtCore
from pineboolib import logging


from typing import Set, Tuple, Optional, Any, TYPE_CHECKING
import weakref
import sys

if TYPE_CHECKING:
    from pineboolib.application.database import pnsqlcursor  # type: ignore
    from pineboolib.application import xmlaction  # noqa: F401


class FormDBWidget(QtWidgets.QWidget):
    """FormDBWidget class."""

    closed = QtCore.pyqtSignal()
    cursor_: Optional["pnsqlcursor.PNSqlCursor"]
    form: Any
    iface: Optional[object]
    signal_test = QtCore.pyqtSignal(str, QtCore.QObject)

    logger = logging.getLogger("q3widgets.formdbwidget.FormDBWidget")

    def __init__(self, action: Optional["xmlaction.XMLAction"] = None):
        """Inicialize."""

        super().__init__()

        self._module = sys.modules[self.__module__]
        self._action = action
        self.iface = None
        self.cursor_ = None
        # self.parent_ = parent or QtWidgets.QWidget()

        # if parent and hasattr(parent, "parentWidget"):
        #    self.parent_ = parent.parentWidget()

        self.form = None
        # from pineboolib.fllegacy import flformdb

        # if isinstance(parent, flformdb.FLFormDB):
        #    self.form = parent

        self._formconnections: Set[Tuple] = set([])

        self._class_init()

    def module_connect(self, sender: Any, signal: str, receiver: Any, slot: str) -> None:
        """Connect two objects."""

        # print(" > > > connect:", sender, " signal ", str(signal))
        from pineboolib.application import connections

        signal_slot = connections.connect(sender, signal, receiver, slot, caller=self)
        if not signal_slot:
            return

        self._formconnections.add(signal_slot)

    def module_disconnect(self, sender: Any, signal: str, receiver: Any, slot: str) -> None:
        """Disconnect two objects."""

        # print(" > > > disconnect:", self)
        from pineboolib.application import connections

        signal_slot = connections.disconnect(sender, signal, receiver, slot, caller=self)
        if not signal_slot:
            return

        for sl in self._formconnections:
            # PyQt5-Stubs misses signal.signal
            if (
                sl[0].signal == getattr(signal_slot[0], "signal")
                and sl[1].__name__ == signal_slot[1].__name__
            ):
                self._formconnections.remove(sl)
                break

    def obj(self) -> Any:
        """Return self."""
        return self

    def parent(self) -> QtWidgets.QWidget:
        """Return parent widget."""

        return self.parentWidget()

    # def _class_init(self):
    #    """Constructor de la clase QS (p.ej. interna(context))"""
    #    pass

    # def init(self):
    #    """Evento init del motor. Llama a interna_init en el QS"""
    #    pass

    def closeEvent(self, event: QtCore.QEvent) -> None:
        """Close event."""

        if self._action is None:
            self._action = getattr(self.parent(), "_action")

        if self._action is not None:
            self.logger.debug("closeEvent para accion %r", self._action.name)
        self.closed.emit()
        event.accept()  # let the window close
        self.doCleanUp()

    def doCleanUp(self) -> None:
        """Cleanup gabange and connections."""

        self.clear_connections()
        iface = getattr(self, "iface", None)
        if iface is not None and self._action is not None:
            from pineboolib.core.garbage_collector import check_gc_referrers

            check_gc_referrers(
                "FormDBWidget.iface:" + iface.__class__.__name__,
                weakref.ref(self.iface),
                self._action.name,
            )

            delattr(self.iface, "ctx")

            del self._action.formrecord_widget

            self.iface = None
            self._action.formrecord_widget = None

    def clear_connections(self) -> None:
        """Clear al conecctions established on the module."""

        # Limpiar todas las conexiones hechas en el script
        for signal, slot in self._formconnections:
            try:
                signal.disconnect(slot)
                self.logger.debug("Señal desconectada al limpiar: %s %s" % (signal, slot))
            except Exception:
                # self.logger.exception("Error al limpiar una señal: %s %s" % (signal, slot))
                pass
        self._formconnections.clear()

    def child(self, child_name: str) -> QtWidgets.QWidget:
        """Return child from name."""

        try:
            ret = self.findChild(QtWidgets.QWidget, child_name, QtCore.Qt.FindChildrenRecursively)
            if ret is not None:
                if hasattr(ret, "_loaded"):
                    if ret._loaded is False:
                        ret.load()

            if ret is None and self.parent():
                ret = getattr(self.parent(), child_name, None)

            if ret is None:
                if child_name == super().objectName() and self.form is not None:
                    ret = self.form

            if ret is None and self.form is not None:
                ret = getattr(self.form, child_name)

            if ret is None:
                self.logger.warning("WARN: No se encontro el control %s", child_name)
                return QtWidgets.QWidget()
            return ret
        except Exception:
            self.logger.exception("child: Error trying to get child of <%s>", child_name)
            return QtWidgets.QWidget()

    def cursor(self) -> "pnsqlcursor.PNSqlCursor":
        """Return cursor associated."""

        # if self.cursor_:
        #    return self.cursor_

        cursor = None
        parent = self

        while cursor is None and parent:
            parent = parent.parentWidget()
            cursor = getattr(parent, "cursor_", None)
        if cursor:
            self.cursor_ = cursor
        else:
            if not self.cursor_:
                if self._action is None:
                    raise Exception("_action is empty!.")

                from pineboolib.application import project
                from pineboolib.application.database.pnsqlcursor import PNSqlCursor

                action = project.conn.manager().action(self._action.name)
                self.cursor_ = PNSqlCursor(action.name())

        if not self.cursor_:
            raise Exception("cursor is empty!.")

        return self.cursor_

    def __getattr__(self, name: str) -> QtWidgets.QWidget:
        """Guess if attribute can be found in other related objects."""
        ret_ = getattr(self.cursor_, name, None)
        if ret_ is None and self.parent():
            ret_ = (
                getattr(self.parent(), name, None) or getattr(self.parent().script, name, None)
                if hasattr(self.parent(), "script")
                else None
            )

        if ret_:
            return ret_

        if not TYPE_CHECKING:
            # FIXME: q3widgets should not interact with fllegacy
            from pineboolib.fllegacy.flapplication import aqApp

            ret_ = getattr(aqApp, name, None)
            if ret_:
                self.logger.info(
                    "FormDBWidget: Coearcing attribute %r from aqApp (should be avoided)" % name
                )
                return ret_

        raise AttributeError("FormDBWidget: Attribute does not exist: %r" % name)

    def __hasattr__(self, name: str) -> bool:
        """Guess if attribute can be found in other related objects."""
        ret_ = (
            hasattr(self.cursor_, name)
            or hasattr(self.parent(), name)
            or hasattr(self.parent().script, name)
        )
        return ret_

    def __iter__(self) -> Any:
        """Return iter."""

        self._iter_current = -1
        return self

    def __next__(self) -> Any:
        """Return next."""

        self._iter_current = 0 if self._iter_current == -1 else self._iter_current + 1

        list_ = [attr for attr in dir(self) if not attr[0] == "_"]
        if self._iter_current >= len(list_):
            raise StopIteration

        return list_[self._iter_current]