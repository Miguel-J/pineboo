# -*- coding: utf-8 -*-
"""
Module for PNSqlCursor class.
"""

from PyQt5 import QtCore, QtWidgets

from pineboolib.core.utils import logging
from pineboolib.core import error_manager, decorators

from pineboolib.application.database import pnsqlquery
from pineboolib.application.utils import xpm
from pineboolib.application import types

from pineboolib import application

from pineboolib.interfaces import isqlcursor

from . import pnbuffer
from . import pncursortablemodel


import weakref
import traceback

from typing import Any, Optional, List, Union, cast, TYPE_CHECKING


from pineboolib.application.acls import pnboolflagstate

if TYPE_CHECKING:

    from pineboolib.application.metadata import pntablemetadata  # noqa: F401
    from pineboolib.application.metadata import pnrelationmetadata  # noqa: F401
    from pineboolib.application.metadata import pnaction  # noqa: F401
    from pineboolib.interfaces import iconnection  # noqa: F401


LOGGER = logging.getLogger(__name__)


class PNSqlCursor(isqlcursor.ISqlCursor):
    """
    Database Cursor class.
    """

    def __init__(
        self,
        name: Optional[str] = None,
        conn_or_autopopulate: Union[bool, str] = True,
        connection_name_or_db: Union[str, "iconnection.IConnection"] = "default",
        cursor_relation: Optional["isqlcursor.ISqlCursor"] = None,
        relation_mtd: Optional["pnrelationmetadata.PNRelationMetaData"] = None,
        parent=None,
    ) -> None:
        """Create a new cursor."""
        super().__init__(
            name, conn_or_autopopulate, connection_name_or_db, cursor_relation, relation_mtd, parent
        )
        self._name = ""
        self._valid = False
        if name is None:
            LOGGER.warning(
                "Se está iniciando un cursor Huerfano (%s). Posiblemente sea una declaración en un qsa parseado",
                self,
            )
            return

        if isinstance(conn_or_autopopulate, str):
            connection_name_or_db = conn_or_autopopulate
            autopopulate = True
        elif isinstance(conn_or_autopopulate, bool):
            autopopulate = conn_or_autopopulate

        act_ = application.PROJECT.conn_manager.manager().action(name)
        db_: "iconnection.IConnection" = (
            application.PROJECT.conn_manager.useConn(connection_name_or_db)
            if isinstance(connection_name_or_db, str)
            else connection_name_or_db
        )

        self.private_cursor = PNCursorPrivate(self, act_, db_)
        self.init(act_.name(), autopopulate, cursor_relation, relation_mtd)

    def init(
        self,
        name: str,
        autopopulate: bool,
        cursor_relation: Optional["isqlcursor.ISqlCursor"],
        relation_mtd: Optional["pnrelationmetadata.PNRelationMetaData"],
    ) -> None:
        """
        Initialize class.

        Common init code for constructors.
        """
        private_cursor = self.private_cursor

        if application.SHOW_CURSOR_EVENTS:
            LOGGER.warning(
                "CURSOR_EVENT: Se crea el cursor para la action %s", name, stack_info=True
            )

        if self.setAction(name):
            private_cursor._count_ref_cursor += 1
        else:
            return

        private_cursor.mode_access_ = PNSqlCursor.Browse

        if self.private_cursor.cursor_relation_:
            self.private_cursor.cursor_relation_.bufferChanged.disconnect(self.refresh)
            self.private_cursor.cursor_relation_.newBuffer.disconnect(self.refresh)
            self.private_cursor.cursor_relation_.newBuffer.disconnect(self.clearPersistentFilter)

        private_cursor.cursor_relation_ = cursor_relation
        private_cursor.relation_ = relation_mtd

        mtd = private_cursor.metadata_
        if not mtd:
            return

        private_cursor._is_query = mtd.isQuery()
        private_cursor._is_system_table = (
            self.db().connManager().manager().isSystemTable(mtd.name())
        )
        self.setName(mtd.name(), autopopulate)

        private_cursor.mode_access_ = self.Browse
        if cursor_relation and relation_mtd is not None:

            cursor_relation.bufferChanged.connect(self.refresh)
            cursor_relation.newBuffer.connect(self.refresh)
            cursor_relation.newBuffer.connect(self.clearPersistentFilter)

        else:
            self.seek(self.at())

        self._valid = True
        private_cursor.timer_ = QtCore.QTimer(self)
        private_cursor.timer_.timeout.connect(self.refreshDelayed)

    def conn(self) -> "iconnection.IConnection":
        """Get current connection for this cursor."""
        return self.db()

    def table(self) -> str:
        """Get current table or empty string."""
        return self._name or ""

    def setName(self, name: str, autop: bool) -> None:
        """Set cursor name."""
        self._name = name
        # FIXME: autopop probably means it should do a refresh upon construction.
        # autop = autopopulate para que??

    def metadata(self) -> "pntablemetadata.PNTableMetaData":
        """
        Retrieve PNTableMetaData for current table.

        @return PNTableMetaData object with metadata related to cursor table.
        """
        if self.private_cursor.metadata_ is None:
            raise Exception("metadata is empty!")

        return self.private_cursor.metadata_

    def currentRegister(self) -> int:
        """
        Get current row number selected by the cursor.

        @return Integer cotining record number.
        """
        return self.private_cursor._currentregister

    def modeAccess(self) -> int:
        """
        Get current access mode for cursor.

        @return PNSqlCursor::Mode constant defining mode access prepared
        """
        return self.private_cursor.mode_access_

    def mainFilter(self) -> str:
        """
        Retrieve main filter for cursor.

        @return String containing the WHERE clause part that will be appended on select.
        """
        ret = (
            self.private_cursor._model.where_filters["main-filter"]
            if "main-filter" in self.private_cursor._model.where_filters.keys()
            else None
        )
        return ret or ""

    def action(self) -> Optional["pnaction.PNAction"]:
        """
        Get PNAction related to this cursor.

        @return PNAction object.
        """
        return self._action

    def actionName(self) -> str:
        """Get action name from pnaction.PNAction related to the cursor. Returns empty string if none is set."""
        return self._action.name() if self._action else ""

    def setAction(self, a: Union[str, "pnaction.PNAction"]) -> bool:
        """
        Set action to be related to this cursor.

        @param PNAction object
        @return True if success, otherwise False.
        """
        action = None
        if isinstance(a, str):
            action = self.db().connManager().manager().action(a.lower())
            # if action.table() == "":
            #    action.setTable(a)
        else:
            action = a

        if self._action is None:
            self._action = action
        else:

            if (
                self._action.table() == action.table()
            ):  # Esto es para evitar que se setee en un FLTableDB con metadata inválido un action sobre un cursor del parentWidget.

                LOGGER.debug(
                    "Se hace setAction sobre un cursor con la misma table %s\nAction anterior: %s\nAction nueva: %s",
                    action.table(),
                    self._action.name(),
                    action.name(),
                )
                self._action = action
                return True

            else:  # La action previa existe y no es la misma tabla
                self._action = action
                self.private_cursor.buffer_ = None
                self.private_cursor.metadata_ = None

        if self._action is None:
            raise Exception("Unexpected: Action is still None")

        if not self._action.table():
            return False

        if self.private_cursor.metadata_ is None:
            self.private_cursor.metadata_ = (
                self.db().connManager().manager().metadata(self._action.table())
            )

        if self.private_cursor.metadata_ is not None:
            self.private_cursor.doAcl()

        self.private_cursor._model = pncursortablemodel.PNCursorTableModel(self.conn(), self)
        # if not self.private_cursor._model:
        #    return False

        # if not self.private_cursor.buffer_:
        #    self.primeInsert()

        self._selection = QtCore.QItemSelectionModel(self.private_cursor._model)
        self.selection().currentRowChanged.connect(self.selection_currentRowChanged)
        # self._currentregister = self.selection().currentIndex().row()
        # self.private_cursor.metadata_ = self.db().manager().metadata(self._action.table())
        self.private_cursor._activated_check_integrity = True
        self.private_cursor._activated_commit_actions = True
        return True

    def setMainFilter(self, filter: str = "", do_refresh: bool = True) -> None:
        """
        Set main cursor filter.

        @param f String containing the filter in SQL WHERE format (excluding WHERE)
        @param doRefresh By default, refresh the cursor afterwards. Set to False to avoid this.
        """
        if self.private_cursor._model:
            self.private_cursor._model.where_filters["main-filter"] = filter
            if do_refresh:
                self.refresh()

    def setModeAccess(self, m: int) -> None:
        """
        Set cursor access mode.

        @param m PNSqlCursor::Mode constant which inidicates access mode.
        """
        self.private_cursor.mode_access_ = m

    def connectionName(self) -> str:
        """
        Get database connection alias name.

        @return String containing the connection name.
        """
        return self.db().connectionName()

    def setAtomicValueBuffer(self, field_name: str, function_name: str) -> None:
        """
        Set a buffer field value in atomic fashion and outside transaction.

        Invoca a la función, cuyo nombre se pasa como parámetro, del script del contexto del cursor
        (ver PNSqlCursor::ctxt_) para obtener el valor del campo. El valor es establecido en el campo de forma
        atómica, bloqueando la fila durante la actualización. Esta actualización se hace fuera de la transacción
        actual, dentro de una transacción propia, lo que implica que el nuevo valor del campo está inmediatamente
        disponible para las siguientes transacciones.

        @param field_name Nombre del campo
        @param function_name Nombre de la función a invocar del script
        """
        mtd = self.private_cursor.metadata_
        if not self.private_cursor.buffer_ or not field_name or not mtd:
            return

        field = mtd.field(field_name)

        if field is None:
            LOGGER.warning(
                "setAtomicValueBuffer(): No existe el campo %s:%s", self.table(), field_name
            )
            return

        db_aux = self.db().connManager().dbAux()
        if db_aux is None:
            return

        type = field.type()
        primary_key = mtd.primaryKey()
        value: Any

        if self.private_cursor.cursor_relation_ and self.modeAccess() == self.Browse:
            self.private_cursor.cursor_relation_.commit(False)

        if primary_key and self.db() is not db_aux:
            primary_key_value = self.private_cursor.buffer_.value(primary_key)
            db_aux.transaction()

            value = application.PROJECT.call(
                function_name,
                [field_name, self.private_cursor.buffer_.value(field_name)],
                self.context(),
            )

            qry = pnsqlquery.PNSqlQuery(None, db_aux)
            ret = qry.exec_(
                "UPDATE  %s SET %s = %s WHERE %s"
                % (
                    self.table(),
                    field_name,
                    self.db().connManager().manager().formatValue(type, value),
                    self.db()
                    .connManager()
                    .manager()
                    .formatAssignValue(mtd.field(primary_key), primary_key_value),
                )
            )
            if ret:
                db_aux.commit()
            else:
                db_aux.rollbackTransaction()
        else:
            LOGGER.warning(
                "No se puede actualizar el campo de forma atómica, porque no existe clave primaria"
            )

        self.private_cursor.buffer_.setValue(field_name, value)
        self.bufferChanged.emit(field_name)
        application.PROJECT.app.processEvents()  # type: ignore[misc] # noqa: F821

    def setValueBuffer(self, field_name: str, value: Any) -> None:
        """
        Set buffer value for a particular field.

        @param field_name field name
        @param value Value to be set to the buffer field.
        """
        mtd = self.private_cursor.metadata_

        if not field_name or mtd is None:
            LOGGER.warning("setValueBuffer(): No fieldName, or no metadata found")
            return

        if not self.private_cursor.buffer_:
            # LOGGER.warning("%s.setValueBuffer(%s): No buffer" % (self.table(), field_name))
            return

        field = mtd.field(field_name)
        if field is None:
            LOGGER.warning("setValueBuffer(): No existe el campo %s:%s", self.table(), field_name)
            return
        database = self.db()
        manager = database.connManager().manager()
        if manager is None:
            raise Exception("no manager")

        type_ = field.type()
        buff_field = self.private_cursor.buffer_.field(field_name)
        if buff_field and not buff_field.has_changed(value):
            return

        if value and type_ == "pixmap" and not self.private_cursor._is_system_table:
            value = database.normalizeValue(value)
            value = manager.storeLargeValue(self.private_cursor.metadata_, value) or value

        if (
            field.outTransaction()
            and database is not database.connManager().dbAux()
            and self.modeAccess() != self.Insert
        ):
            primary_key = mtd.primaryKey()

            if (
                self.private_cursor.cursor_relation_ is not None
                and self.modeAccess() != self.Browse
            ):
                self.private_cursor.cursor_relation_.commit(False)

            if primary_key:
                primary_key_value = self.private_cursor.buffer_.value(primary_key)
                qry = pnsqlquery.PNSqlQuery(None, "dbAux")
                qry.exec_(
                    "UPDATE %s SET %s = %s WHERE %s;"
                    % (
                        mtd.name(),
                        field_name,
                        manager.formatValue(type_, value),
                        manager.formatAssignValue(mtd.field(primary_key), primary_key_value),
                    )
                )
            else:
                LOGGER.warning(
                    "FLSqlCursor : No se puede actualizar el campo fuera de transaccion, porque no existe clave primaria"
                )

        else:
            self.private_cursor.buffer_.setValue(field_name, value)

        # LOGGER.trace("(%s)bufferChanged.emit(%s)" % (self.curName(),field_name))

        self.bufferChanged.emit(field_name)
        application.PROJECT.app.processEvents()  # type: ignore[misc] # noqa: F821

    def valueBuffer(self, field_name: str) -> Any:
        """
        Retrieve a value from a field buffer (self.private_cursor.buffer_).

        @param field_name field name
        """
        mtd = self.private_cursor.metadata_

        # if self.private_cursor.rawValues_:
        #    return self.valueBufferRaw(field_name)

        if not mtd:
            return None

        if (
            self.private_cursor._model.rows > 0 and not self.modeAccess() == self.Insert
        ) or not self.private_cursor.buffer_:
            if not self.private_cursor.buffer_:
                self.refreshBuffer()

            if self.private_cursor.buffer_ is None:
                return None

        field = mtd.field(field_name)
        if field is None:
            LOGGER.warning("valueBuffer(): No existe el campo %s:%s", self.table(), field_name)
            return None

        type_ = field.type()

        value = None
        if (
            field.outTransaction()
            and self.db() is not self.db().connManager().dbAux()
            and self.modeAccess() != self.Insert
        ):
            primary_key = mtd.primaryKey()

            # if self.private_cursor.buffer_ is None:
            #    return None
            if primary_key:

                primary_key_value = self.private_cursor.buffer_.value(primary_key)
                qry = pnsqlquery.PNSqlQuery(None, "dbAux")
                sql_query = "SELECT %s FROM %s WHERE %s" % (
                    field_name,
                    mtd.name(),
                    self.db()
                    .connManager()
                    .manager()
                    .formatAssignValue(mtd.field(primary_key), primary_key_value),
                )
                # q.exec_(self.db().dbAux(), sql_query)
                qry.exec_(sql_query)
                if qry.next():
                    value = qry.value(0)
            else:
                LOGGER.warning(
                    "No se puede obtener el campo fuera de transacción porque no existe clave primaria"
                )

        else:

            # if self.private_cursor.buffer_ is None:
            #    return None
            value = self.private_cursor.buffer_.value(field_name)

        if value is not None:
            if type_ in ("date"):

                value = types.Date(value)
            elif type_ == "pixmap":
                v_large = None
                if not self.private_cursor._is_system_table:

                    v_large = self.db().connManager().manager().fetchLargeValue(value)

                else:

                    v_large = xpm.cache_xpm(value)

                if v_large:
                    value = v_large
        else:
            if type_ in ("string", "stringlist", "date", "timestamp"):
                value = ""
            elif type_ in ("double", "int", "uint"):
                value = 0

            self.private_cursor.buffer_.setValue(field_name, value)

        return value

    def fetchLargeValue(self, value: str) -> Any:
        """Retrieve large value from database."""
        return self.db().connManager().manager().fetchLargeValue(value)

    def valueBufferCopy(self, field_name: str) -> Any:
        """
        Retrieve original value for a field before it was changed.

        @param field_name field name
        """
        if not self.bufferCopy() or not self.private_cursor.metadata_:
            return None

        field = self.private_cursor.metadata_.field(field_name)
        if field is None:
            LOGGER.warning(
                "FLSqlCursor::valueBufferCopy() : No existe el campo %s.%s",
                self.table(),
                field_name,
            )
            return None

        type_ = field.type()
        buffer_copy = self.bufferCopy()
        if buffer_copy is None:
            raise Exception("no bufferCopy")
        value: Any = None
        if buffer_copy.isNull(field_name):
            if type_ in ("double", "int", "uint"):
                value = 0
            elif type_ == "string":
                value = ""
        else:
            value = buffer_copy.value(field_name)

        if value is not None:
            if type_ in ("date"):

                value = types.Date(value)

            elif type_ == "pixmap":
                v_large = None
                if not self.private_cursor._is_system_table:
                    v_large = self.db().connManager().manager().fetchLargeValue(value)
                else:
                    v_large = xpm.cache_xpm(value)

                if v_large:
                    value = v_large
        else:
            if type_ in ("string", "stringlist", "date", "timestamp"):
                value = ""
            elif type_ in ("double", "int", "uint"):
                value = 0

        return value

    def setEdition(self, b: bool, m: Optional[str] = None) -> None:
        """
        Put cursor into "edition" mode.

        @param b TRUE or FALSE
        """
        # FIXME: What is "edition" ??
        if m is None:
            self.private_cursor.edition_ = b
            return

        state_changes = b != self.private_cursor.edition_

        if state_changes and not self.private_cursor.edition_states_:
            self.private_cursor.edition_states_ = pnboolflagstate.PNBoolFlagStateList()

        # if self.private_cursor.edition_states_ is None:
        #     return

        i = self.private_cursor.edition_states_.find(m)
        if not i and state_changes:
            i = pnboolflagstate.PNBoolFlagState()
            i.modifier_ = m
            i.prev_value_ = self.private_cursor.edition_
            self.private_cursor.edition_states_.append(i)
        elif i:
            if state_changes:
                self.private_cursor.edition_states_.pushOnTop(i)
                i.prev_value_ = self.private_cursor.edition_
            else:
                self.private_cursor.edition_states_.erase(i)

        if state_changes:
            self.private_cursor.edition_ = b

    def restoreEditionFlag(self, m: str) -> None:
        """Restore Edition flag to its previous value."""
        edition_state = self.private_cursor.edition_states_
        if edition_state:

            i = edition_state.find(m)

            if i and i == edition_state.current():
                self.private_cursor.edition_ = i.prev_value_

            if i:
                edition_state.erase(i)

    def setBrowse(self, b: bool, m: Optional[str] = None) -> None:
        """
        Put cursor into browse mode.

        @param b TRUE or FALSE
        """
        if not m:
            self.private_cursor.browse_ = b
            return

        state_changes = b != self.private_cursor.browse_

        if state_changes and not self.private_cursor.browse_states_:
            self.private_cursor.browse_states_ = pnboolflagstate.PNBoolFlagStateList()

        if not self.private_cursor.browse_states_:
            return

        i = self.private_cursor.browse_states_.find(m)
        if not i and state_changes:
            i = pnboolflagstate.PNBoolFlagState()
            i.modifier_ = m
            i.prev_value_ = self.private_cursor.browse_
            self.private_cursor.browse_states_.append(i)
        elif i:
            if state_changes:
                self.private_cursor.browse_states_.pushOnTop(i)
                i.prev_value_ = self.private_cursor.browse_
            else:
                self.private_cursor.browse_states_.erase(i)

        if state_changes:
            self.private_cursor.browse_ = b

    def restoreBrowseFlag(self, m: str) -> None:
        """Restores browse flag to its previous state."""
        browse_state = self.private_cursor.browse_states_
        if browse_state:
            i = browse_state.find(m)

            if i and i == browse_state.current():
                self.private_cursor.browse_ = i.prev_value_

            if i:
                browse_state.erase(i)

    # def meta_model(self) -> Callable:
    #    """
    #    Check if DGI requires models (SqlAlchemy?).
    #    """
    #    return self.meta_model if application.PROJECT.DGI.use_model() else None

    def setContext(self, c: Any = None) -> None:
        """
        Set cursor context for script execution.

        This can be for master or formRecord.

        See FLSqlCursor::ctxt_.

        @param c Execution Context
        """
        if c:
            self.private_cursor.ctxt_ = weakref.ref(c)

    def context(self) -> Any:
        """
        Retrieve current context of execution of scripts for this cursor.

        See FLSqlCursor::ctxt_.

        @return Execution context
        """
        if not self.private_cursor.ctxt_:
            LOGGER.debug("%s.context(). No hay contexto" % self.curName())
            return

        return self.private_cursor.ctxt_()

    def fieldDisabled(self, field_name: str) -> bool:
        """
        Check if a field is disabled.

        Un campo estará deshabilitado, porque esta clase le dará un valor automáticamente.
        Estos campos son los que están en una relación con otro cursor, por lo que
        su valor lo toman del campo foráneo con el que se relacionan.

        @param field_name Nombre del campo a comprobar
        @return TRUE si está deshabilitado y FALSE en caso contrario
        """
        if self.modeAccess() in (self.Insert, self.Edit):

            if (
                self.private_cursor.cursor_relation_ is not None
                and self.private_cursor.relation_ is not None
            ):
                if not self.private_cursor.cursor_relation_.metadata():
                    return False
                field = self.private_cursor.relation_.field()
                if field.lower() == field_name.lower():
                    return True
                else:
                    return False
            else:
                return False
        else:
            return False

    def inTransaction(self) -> bool:
        """
        Check if there is a transaction in progress.

        @return TRUE if there is one.
        """
        if self.db():
            if self.db()._transaction > 0:
                return True

        return False

    def transaction(self, lock: bool = False) -> bool:
        """
        Start a new transaction.

        Si ya hay una transacción en curso simula un nuevo nivel de anidamiento de
        transacción mediante un punto de salvaguarda.

        @param  lock Actualmente no se usa y no tiene ningún efecto. Se mantiene por compatibilidad hacia atrás
        @return TRUE si la operación tuvo exito
        """

        if application.SHOW_CURSOR_EVENTS:
            LOGGER.warning("CURSOR_EVENT: TRANSACTION %s", self.table(), stack_info=True)

        return self.db().doTransaction(self)

    def rollback(self) -> bool:
        """
        Undo operations from a transaction and cleans up.

        @return TRUE if success.
        """

        if application.SHOW_CURSOR_EVENTS:
            LOGGER.warning("CURSOR_EVENT: ROLLBACK %s", self.table(), stack_info=True)

        return self.db().doRollback(self)

    def commit(self, notify: bool = True) -> bool:
        """
        Finishes and commits transaction.

        @param notify If TRUE emits signal cursorUpdated and sets cursor on BROWSE,
              If FALSE skips and emits autoCommit signal.
        @return TRUE if success.
        """

        if application.SHOW_CURSOR_EVENTS:
            LOGGER.warning("CURSOR_EVENT: COMMIT %s", self.table(), stack_info=True)

        result = self.db().doCommit(self, notify)
        if result:
            self.commited.emit()

        return result

    def size(self) -> int:
        """Get number of records in the cursor."""
        model = self.model()
        return model.rows

    def openFormInMode(self, m: int, wait: bool = True, cont: bool = True) -> None:
        """
        Open form associated with the table in the specified mode.

        @param m Opening mode. (FLSqlCursor::Mode)
        @param wait Indica que se espera a que el formulario cierre para continuar
        @param cont Indica que se abra el formulario de edición de registros con el botón de
        aceptar y continuar
        """
        if not self.private_cursor.metadata_:
            return

        if (not self.isValid() or self.size() <= 0) and not m == self.Insert:
            if not self.size():
                self.private_cursor.msgBoxWarning(self.tr("No hay ningún registro seleccionado"))
                # QtWidgets.QMessageBox.warning(
                #    QApplication.focusWidget(),
                #    self.tr("Aviso"),
                #    self.tr("No hay ningún registro seleccionado"),
                # )
                return
            self.first()

        if m == self.Del:
            res = QtWidgets.QMessageBox.warning(
                QtWidgets.QApplication.focusWidget(),
                self.tr("Aviso"),
                self.tr("El registro activo será borrado. ¿ Está seguro ?"),
                QtWidgets.QMessageBox.Ok,
                QtWidgets.QMessageBox.No,
            )
            if res == QtWidgets.QMessageBox.No:
                return

            self.transaction()
            self.private_cursor.mode_access_ = self.Del
            if not self.refreshBuffer():
                self.commit()
            else:
                if not self.commitBuffer():
                    self.rollback()
                else:
                    self.commit()

            return

        self.private_cursor.mode_access_ = m

        if self.private_cursor.buffer_:
            self.private_cursor.buffer_.clearValues()

        # if not self.private_cursor._action:
        # self.private_cursor.action_ = self.db().manager().action(self.table())

        if not self._action:
            LOGGER.warning(
                "Para poder abrir un registro de edición se necesita una acción asociada al cursor, "
                "o una acción definida con el mismo nombre que la tabla de la que procede el cursor."
            )
            return

        if not self._action.formRecord():
            QtWidgets.QMessageBox.warning(
                QtWidgets.QApplication.focusWidget(),
                self.tr("Aviso"),
                self.tr(
                    "No hay definido ningún formulario para manejar\nregistros de esta tabla : %s"
                    % self.curName()
                ),
            )
            return

        if self.refreshBuffer():  # Hace doTransaction antes de abrir formulario y crear savepoint
            if m != self.Insert:
                self.updateBufferCopy()

            application.PROJECT.actions[self._action.name()].openDefaultFormRecord(self, wait)

            # if m != self.Insert and self.refreshBuffer():
            #     self.updateBufferCopy()

    def isNull(self, field_name: str) -> bool:
        """Get if a field is null."""
        if not self.private_cursor.buffer_:
            raise Exception("No buffer set")
        return self.private_cursor.buffer_.isNull(field_name)

    def isCopyNull(self, field_name: str) -> bool:
        """Get if a field was null before changing."""
        if not self.private_cursor._buffer_copy:
            raise Exception("No buffer_copy set")
        return self.private_cursor._buffer_copy.isNull(field_name)

    def updateBufferCopy(self) -> None:
        """
        Copy contents of FLSqlCursor::buffer_ into FLSqlCursor::_buffer_copy.

        This copy allows later to check if the buffer was changed using
        FLSqlCursor::isModifiedBuffer().
        """
        if not self.private_cursor.buffer_:
            return None

        if self.private_cursor._buffer_copy:
            del self.private_cursor._buffer_copy

        self.private_cursor._buffer_copy = pnbuffer.PNBuffer(self)
        # bufferCopy = self.bufferCopy()
        if not self.private_cursor._buffer_copy:
            raise Exception("No buffercopy")

        for field in self.private_cursor.buffer_.fieldsList():
            self.private_cursor._buffer_copy.setValue(
                field.name, self.private_cursor.buffer_.value(field.name), False
            )

    def isModifiedBuffer(self) -> bool:
        """
        Check if current buffer contents are different from the original copy.

        See FLSqlCursor::_buffer_copy .

        @return True if different. False if equal.
        """

        if self.private_cursor.buffer_ is None:
            return False

        if self.private_cursor.buffer_.modifiedFields():
            return True
        else:
            return False

    def setAskForCancelChanges(self, a: bool) -> None:
        """
        Set value for FLSqlCursor::_ask_for_cancel_changes .

        @param a If True, a popup will appear warning the user for unsaved changes on cancel.
        """
        self.private_cursor._ask_for_cancel_changes = a

    def setActivatedCheckIntegrity(self, a: bool) -> None:
        """
        Enable or disable integrity checks.

        @param a TRUE los activa y FALSE los desactiva
        """
        self.private_cursor._activated_check_integrity = a

    def activatedCheckIntegrity(self) -> bool:
        """Retrieve if integrity checks are enabled."""
        return self.private_cursor._activated_check_integrity

    def setActivatedCommitActions(self, a: bool) -> None:
        """
        Enable or disable before/after commit actions.

        @param a True to enable, False to disable.
        """
        self.private_cursor._activated_commit_actions = a

    def activatedCommitActions(self) -> bool:
        """
        Retrieve wether before/after commits are enabled.
        """
        return self.private_cursor._activated_commit_actions

    def msgCheckIntegrity(self) -> str:
        """
        Get message for integrity checks.

        The referential integrity is checked when trying to delete, the non-duplication of
        primary keys and if there are nulls in fields that do not allow it when inserted or edited.
        If any verification fails, it returns a message describing the fault.

        @return Error message
        """
        message = ""

        if self.private_cursor.buffer_ is None or self.private_cursor.metadata_ is None:
            message = "\nBuffer vacío o no hay metadatos"
            return message

        if self.private_cursor.mode_access_ in [self.Insert, self.Edit]:
            if not self.isModifiedBuffer() and self.private_cursor.mode_access_ == self.Edit:
                return message
            field_list = self.private_cursor.metadata_.fieldList()
            checked_compound_key = False

            if not field_list:
                return message

            for field in field_list:
                field_name = field.name()
                relation_m1 = field.relationM1()
                if not self.private_cursor.buffer_.isGenerated(field_name):
                    continue

                value = None
                if not self.private_cursor.buffer_.isNull(field_name):
                    value = self.private_cursor.buffer_.value(field_name)

                assoc_field_metadata = field.associatedField()
                if assoc_field_metadata and value is not None:
                    if not relation_m1:
                        message = (
                            message
                            + "\n"
                            + "FLSqlCursor : Error en metadatos, el campo %s tiene un campo asociado pero no existe "
                            "relación muchos a uno:%s" % (self.table(), field_name)
                        )
                        continue

                    if not relation_m1.checkIn():
                        continue
                    table_metadata = (
                        self.db().connManager().manager().metadata(relation_m1.foreignTable())
                    )
                    if not table_metadata:
                        continue
                    field_metadata_name = assoc_field_metadata.name()
                    assoc_value = None
                    if not self.private_cursor.buffer_.isNull(field_metadata_name):
                        assoc_value = self.private_cursor.buffer_.value(field_metadata_name)
                        # if not ss:
                        #     ss = None
                    if assoc_value:
                        filter = "%s AND %s" % (
                            self.db()
                            .connManager()
                            .manager()
                            .formatAssignValue(
                                field.associatedFieldFilterTo(),
                                assoc_field_metadata,
                                assoc_value,
                                True,
                            ),
                            self.db()
                            .connManager()
                            .manager()
                            .formatAssignValue(relation_m1.foreignField(), field, value, True),
                        )
                        qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                        qry.setTablesList(table_metadata.name())
                        qry.setSelect(field.associatedFieldFilterTo())
                        qry.setFrom(table_metadata.name())
                        qry.setWhere(filter)
                        qry.setForwardOnly(True)
                        qry.exec_()
                        if not qry.next():
                            message += "\n%s:%s : %s no pertenece a %s" % (
                                self.table(),
                                field.alias(),
                                value,
                                assoc_value,
                            )
                        else:
                            self.private_cursor.buffer_.setValue(field_metadata_name, qry.value(0))

                    else:
                        message += "\n%s:%s : %s no se puede asociar aun valor NULO" % (
                            self.table(),
                            field.alias(),
                            value,
                        )
                    if not table_metadata.inCache():
                        del table_metadata

                if self.private_cursor.mode_access_ == self.Edit:
                    if self.private_cursor.buffer_ and self.private_cursor._buffer_copy:
                        if self.private_cursor.buffer_.value(
                            field_name
                        ) == self.private_cursor._buffer_copy.value(field_name):
                            continue

                if (
                    self.private_cursor.buffer_.isNull(field_name)
                    and not field.allowNull()
                    and not field.type() in ("serial")
                ):
                    message += "\n%s:%s : No puede ser nulo" % (self.table(), field.alias())

                if field.isUnique():
                    primary_key = self.private_cursor.metadata_.primaryKey()
                    if not self.private_cursor.buffer_.isNull(primary_key) and value is not None:
                        value_primary_key = self.private_cursor.buffer_.value(primary_key)
                        field_mtd = self.private_cursor.metadata_.field(primary_key)
                        if field_mtd is None:
                            raise Exception("pk field is not found!")
                        qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                        qry.setTablesList(self.table())
                        qry.setSelect(field_name)
                        qry.setFrom(self.table())
                        qry.setWhere(
                            "%s AND %s <> %s"
                            % (
                                self.db()
                                .connManager()
                                .manager()
                                .formatAssignValue(field, value, True),
                                self.private_cursor.metadata_.primaryKey(
                                    self.private_cursor._is_query
                                ),
                                self.db()
                                .connManager()
                                .manager()
                                .formatValue(field_mtd.type(), value_primary_key),
                            )
                        )
                        qry.setForwardOnly(True)
                        qry.exec_()
                        if qry.next():
                            message += (
                                "\n%s:%s : Requiere valores únicos, y ya hay otro registro con el valor %s en este campo"
                                % (self.table(), field.alias(), value)
                            )

                if (
                    field.isPrimaryKey()
                    and self.private_cursor.mode_access_ == self.Insert
                    and value is not None
                ):
                    qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                    qry.setTablesList(self.table())
                    qry.setSelect(field_name)
                    qry.setFrom(self.table())
                    qry.setWhere(
                        self.db().connManager().manager().formatAssignValue(field, value, True)
                    )
                    qry.setForwardOnly(True)
                    qry.exec_()
                    if qry.next():
                        message += (
                            "\n%s:%s : Es clave primaria y requiere valores únicos, y ya hay otro registro con el valor %s en este campo"
                            % (self.table(), field.alias(), value)
                        )

                if relation_m1 and value:
                    if relation_m1.checkIn() and not relation_m1.foreignTable() == self.table():
                        # r = field.relationM1()
                        table_metadata = (
                            self.db().connManager().manager().metadata(relation_m1.foreignTable())
                        )
                        if not table_metadata:
                            continue
                        qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                        qry.setTablesList(table_metadata.name())
                        qry.setSelect(relation_m1.foreignField())
                        qry.setFrom(table_metadata.name())
                        qry.setWhere(
                            self.db()
                            .connManager()
                            .manager()
                            .formatAssignValue(relation_m1.foreignField(), field, value, True)
                        )
                        qry.setForwardOnly(True)
                        LOGGER.debug(
                            "SQL linea = %s conn name = %s", qry.sql(), self.connectionName()
                        )
                        qry.exec_()
                        if not qry.next():
                            message += "\n%s:%s : El valor %s no existe en la tabla %s" % (
                                self.table(),
                                field.alias(),
                                value,
                                relation_m1.foreignTable(),
                            )
                        else:
                            self.private_cursor.buffer_.setValue(field_name, qry.value(0))

                        if not table_metadata.inCache():
                            del table_metadata

                field_list_compound_key = self.private_cursor.metadata_.fieldListOfCompoundKey(
                    field_name
                )
                if (
                    field_list_compound_key
                    and not checked_compound_key
                    and self.private_cursor.mode_access_ == self.Insert
                ):
                    if field_list_compound_key:
                        filter_compound_key: str = ""
                        field_1: str = ""
                        values_fields: str = ""
                        for field_compound_key in field_list_compound_key:
                            value_compound_key = self.private_cursor.buffer_.value(
                                field_compound_key.name()
                            )
                            if filter_compound_key:
                                filter_compound_key += " AND "

                            filter_compound_key += "%s" % self.db().connManager().manager().formatAssignValue(
                                field_compound_key, value_compound_key, True
                            )

                            if field_1:
                                field_1 += "+"

                            field_1 += "%s" % field_compound_key.alias()

                            if values_fields:
                                values_fields += "+"

                            values_fields = "%s" % str(value_compound_key)

                        qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                        qry.setTablesList(self.table())
                        qry.setSelect(field_name)
                        qry.setFrom(self.table())
                        if filter_compound_key:
                            qry.setWhere(filter_compound_key)
                        qry.setForwardOnly(True)
                        qry.exec_()

                        if qry.next():
                            message += (
                                "\n%s : Requiere valor único, y ya hay otro registro con el valor %s en la tabla %s"
                                % (field_1, values_fields, self.table())
                            )
                        checked_compound_key = True

        elif self.private_cursor.mode_access_ == self.Del:
            field_list = self.private_cursor.metadata_.fieldList()
            # field_name = None
            value = None

            for field in field_list:
                # field_name = field.name()
                if not self.private_cursor.buffer_.isGenerated(field.name()):
                    continue

                value = None

                if not self.private_cursor.buffer_.isNull(field.name()):
                    value = self.private_cursor.buffer_.value(field.name())
                    # if s:
                    #    s = None

                if value is None:
                    continue

                relation_list = field.relationList()
                for relation in relation_list:
                    if not relation.checkIn():
                        continue
                    metadata = self.db().connManager().manager().metadata(relation.foreignTable())
                    if not metadata:
                        continue
                    field_metadata = metadata.field(relation.foreignField())
                    if field_metadata is not None:
                        if field_metadata.relationM1():
                            if field_metadata.relationM1().deleteCascade():
                                if not metadata.inCache():
                                    del metadata
                                continue
                            if not field_metadata.relationM1().checkIn():
                                if not metadata.inCache():
                                    del metadata
                                continue
                        else:
                            if not metadata.inCache():
                                del metadata
                            continue

                    else:
                        message += (
                            "\nFLSqlCursor : Error en metadatos, %s.%s no es válido.\nCampo relacionado con %s.%s."
                            % (metadata.name(), relation.foreignField(), self.table(), field.name())
                        )
                        if not metadata.inCache():
                            del metadata
                        continue

                    qry = pnsqlquery.PNSqlQuery(None, self.db().connectionName())
                    qry.setTablesList(metadata.name())
                    qry.setSelect(relation.foreignField())
                    qry.setFrom(metadata.name())
                    qry.setWhere(
                        self.db()
                        .connManager()
                        .manager()
                        .formatAssignValue(relation.foreignField(), field, value, True)
                    )
                    qry.setForwardOnly(True)
                    qry.exec_()
                    if qry.next():
                        message += "\n%s:%s : Con el valor %s hay registros en la tabla %s" % (
                            self.table(),
                            field.alias(),
                            value,
                            metadata.name(),
                        )
                    if not metadata.inCache():
                        del metadata

        return message

    def checkIntegrity(self, showError: bool = True) -> bool:
        """
        Perform integrity checks.

        The referential integrity is checked when trying to delete, the non-duplication of
        primary keys and if there are nulls in fields that do not allow it when inserted or edited.
        If any check fails it displays a dialog box with the type of fault found and the method
        returns FALSE.

        @param showError If TRUE shows the dialog box with the error that occurs when the pass integrity checks
        @return TRUE if the buffer could be delivered to the cursor, and FALSE if any verification failed of integrity
        """
        if not self.private_cursor.buffer_ or not self.private_cursor.metadata_:
            return False
        if not self.private_cursor._activated_check_integrity:
            return True
        msg = self.msgCheckIntegrity()
        if msg:
            if showError:
                if self.private_cursor.mode_access_ in (self.Insert, self.Edit):
                    self.private_cursor.msgBoxWarning(
                        "No se puede validad el registro actual:\n" + msg
                    )
                elif self.private_cursor.mode_access_ == self.Del:
                    self.private_cursor.msgBoxWarning("No se puede borrar registro:\n" + msg)

            return False

        return True

    def cursorRelation(self) -> Optional["isqlcursor.ISqlCursor"]:
        """
        Return the cursor relationed.

        @return PNSqlCursor relationed or None
        """
        return self.private_cursor.cursor_relation_

    def relation(self) -> Optional["pnrelationmetadata.PNRelationMetaData"]:
        """
        Return the relation metadata.

        @return PNRelationMetaData relationed or None.
        """
        return self.private_cursor.relation_

    def setUnLock(self, field_name: str, v: bool) -> None:
        """
        Unlock the current cursor record.

        @param field_name Field name.
        @param v Value for the unlock field.
        """

        if not self.private_cursor.metadata_ or not self.modeAccess() == self.Browse:
            return

        field_mtd = self.private_cursor.metadata_.field(field_name)
        if field_mtd is None:
            raise Exception("Field %s is empty!" % field_name)

        if not field_mtd.type() == "unlock":
            LOGGER.warning("setUnLock sólo permite modificar campos del tipo Unlock")
            return

        if not self.private_cursor.buffer_:
            self.primeUpdate()

        if not self.private_cursor.buffer_:
            raise Exception("Unexpected null buffer")

        self.setModeAccess(self.Edit)
        self.private_cursor.buffer_.setValue(field_name, v)
        self.update()
        self.refreshBuffer()

    def isLocked(self) -> bool:
        """
        To check if the current cursor record is locked.

        @return TRUE if blocked, FALSE otherwise.
        """
        if not self.private_cursor.metadata_:
            return False

        ret_ = False
        if self.private_cursor.mode_access_ is not self.Insert:
            row = self.currentRegister()

            for field in self.private_cursor.metadata_.fieldNamesUnlock():
                if row > -1:
                    if self.private_cursor._model.value(row, field) not in ("True", True, 1, "1"):
                        ret_ = True
                        break

        if not ret_ and self.private_cursor.cursor_relation_ is not None:
            ret_ = self.private_cursor.cursor_relation_.isLocked()

        return ret_

    def buffer(self) -> Optional[pnbuffer.PNBuffer]:
        """
        Return the content of the buffer.

        @return PNBuffer or None.
        """
        return self.private_cursor.buffer_

    def bufferCopy(self) -> Optional[pnbuffer.PNBuffer]:
        """
        Return the contents of the bufferCopy.

        @return PNBuffer or None.
        """
        return self.private_cursor._buffer_copy

    def bufferIsNull(self, pos_or_name: Union[int, str]) -> bool:
        """
        Return if the content of a field in the buffer is null.

        @param pos_or_name Name or pos of the field in the buffer.
        @return True or False
        """

        if self.private_cursor.buffer_ is not None:
            return self.private_cursor.buffer_.isNull(pos_or_name)

        return True

    def bufferSetNull(self, pos_or_name: Union[int, str]) -> None:
        """
        Set the content of a field in the buffer to be null.

        @param pos_or_name Name or pos of the field in the buffer.
        """

        if self.private_cursor.buffer_ is not None:
            self.private_cursor.buffer_.setNull(pos_or_name)

    def bufferCopyIsNull(self, pos_or_name: Union[int, str]) -> bool:
        """
        Return if the content of a field in the bufferCopy is null.

        @param pos_or_name Name or pos of the field in the bufferCopy
        """

        if self.private_cursor._buffer_copy is not None:
            return self.private_cursor._buffer_copy.isNull(pos_or_name)
        return True

    def bufferCopySetNull(self, pos_or_name: Union[int, str]) -> None:
        """
        Set the content of a field in the bufferCopy to be null.

        @param pos_or_name Name or pos of the field in the bufferCopy
        """

        if self.private_cursor._buffer_copy is not None:
            self.private_cursor._buffer_copy.setNull(pos_or_name)

    def atFrom(self) -> int:
        """
        Get the position of the current record, according to the primary key contained in the self.private_cursor.buffer_.

        The position of the current record within the cursor is calculated taking into account the
        Current filter (FLSqlCursor :: curFilter ()) and the field or sort fields of it (QSqlCursor :: sort ()).
        This method is useful, for example, to know at what position within the cursor
        A record has been inserted.

        @return Position of the record within the cursor, or 0 if it does not match.
        """

        if not self.buffer() or not self.private_cursor.metadata_:
            return 0
        # Faster version for this function::
        if self.isValid():
            pos = self.at()
        else:
            pos = 0
        return pos

    def atFromBinarySearch(self, field_name: str, value: Any, order_asc: bool = True) -> int:
        """
        Get the position within the cursor of the first record in the indicated field start with the requested value.

        It assumes that the records are ordered by that field, to perform a binary search.
        The position of the current record within the cursor is calculated taking into account the
        Current filter (FLSqlCursor :: curFilter ()) and the field or sort fields
        of it (QSqlCursor :: sort ()).
        This method is useful, for example, to know at what position within the cursor
        a record with a certain value is found in a field.

        @param field_name Name of the field in which to look for the value
        @param value Value to look for (using like 'v%')
        @param orderAsc TRUE (default) if the order is ascending, FALSE if it is descending
        @return Position of the record within the cursor, or 0 if it does not match.
        """

        ret = -1
        ini = 0
        fin = self.size() - 1

        if not self.private_cursor.metadata_:
            raise Exception("Metadata is not set")

        if field_name in self.private_cursor.metadata_.fieldNames():
            while ini <= fin:
                mid = int((ini + fin) / 2)
                mid_value = str(self.private_cursor._model.value(mid, field_name))
                if value == mid_value:
                    ret = mid
                    break

                comp = value < mid_value if order_asc else value > mid_value

                if not comp:
                    ini = mid + 1
                else:
                    fin = mid - 1
                ret = ini

        return ret

    # """
    # Redefinido por conveniencia
    # """

    # @decorators.NotImplementedWarn
    # def exec_(self, query: str) -> bool:
    # if query:
    #    LOGGER.debug("ejecutando consulta " + query)
    #    QSqlQuery.exec(self, query)

    #    return True

    def setNull(self, name: str) -> None:
        """Specify a field as Null."""

        self.setValueBuffer(name, None)

    def db(self) -> "iconnection.IConnection":
        """
        To get the database you work on.

        @return PNConnection used by the cursor.
        """

        if not self.private_cursor.db_:
            raise Exception("db_ is not defined!")

        return self.private_cursor.db_

    def curName(self) -> str:
        """
        To get the cursor name (usually the table name).

        @return cursor Name
        """
        return self.private_cursor.cursor_name_

    def filterAssoc(
        self, fieldName: str, tableMD: Optional["pntablemetadata.PNTableMetaData"] = None
    ) -> Optional[str]:
        """
        To get the default filter in associated fields.

        @param fieldName Name of the field that has associated fields. It must be the name of a field of this cursor.
        @param tableMD Metadata to use as a foreign table. If it is zero use the foreign table defined by the relation M1 of 'fieldName'.
        """
        fieldName = fieldName

        mtd = self.private_cursor.metadata_
        if not mtd:
            return None

        field = mtd.field(fieldName)
        if field is None:
            return None

        # ownTMD = False

        if not tableMD:
            # ownTMD = True
            rel_m1 = field.relationM1()
            if rel_m1 is None:
                raise Exception("relation is empty!")
            tableMD = self.db().connManager().manager().metadata(rel_m1.foreignTable())

        if not tableMD:
            return None

        assoc_field = field.associatedField()
        if assoc_field is None:
            # if ownTMD and not tableMD.inCache():
            # del tableMD
            return None

        field_by = field.associatedFieldFilterTo()

        if self.private_cursor.buffer_ is None:
            return None

        if not tableMD.field(field_by) or self.private_cursor.buffer_.isNull(assoc_field.name()):
            # if ownTMD and not tableMD.inCache():
            # del tableMD
            return None

        assoc_value = self.private_cursor.buffer_.value(assoc_field.name())
        if assoc_value:
            # if ownTMD and not tableMD.inCache():
            # del tableMD
            return (
                self.db()
                .connManager()
                .manager()
                .formatAssignValue(field_by, assoc_field, assoc_value, True)
            )

        # if ownTMD and not tableMD.inCache():
        # del rableMD

        return None

    @decorators.BetaImplementation
    def aqWasDeleted(self) -> bool:
        """
        Indicate if the cursor has been deleted.

        @return True or False.
        """
        return False

    @decorators.NotImplementedWarn
    def calculateField(self, name: str) -> bool:
        """
        Indicate if the field is calculated.

        @return True or False.
        """
        return True

    def model(self) -> "pncursortablemodel.PNCursorTableModel":
        """
        Return the tablemodel used by the cursor.

        @return PNCursorTableModel used.
        """
        return self.private_cursor._model

    def selection(self) -> Any:
        """
        Return the item pointed to in the tablemodel.

        @return selected Item.
        """
        return self._selection

    @decorators.pyqtSlot(QtCore.QModelIndex, QtCore.QModelIndex)
    @decorators.pyqtSlot(int, int)
    @decorators.pyqtSlot(int)
    def selection_currentRowChanged(self, current: Any, previous: Any = None) -> None:
        """
        Update the current record pointed to by the tablemodel.

        @param current. new item selected.
        @param previous. old item selected.
        """
        if self.currentRegister() == current.row():
            self.private_cursor.doAcl()
            return None

        self.private_cursor._currentregister = current.row()
        self.private_cursor._current_changed.emit(self.at())
        self.refreshBuffer()

        self.private_cursor.doAcl()
        if self._action:
            LOGGER.debug(
                "cursor:%s , row:%s:: %s", self._action.table(), self.currentRegister(), self
            )

    def selection_pk(self, value: str) -> bool:
        """
        Move the cursor position to the one that matches the primaryKey value.

        @param value. primaryKey value to search.
        @return True if seek the position else False.
        """

        # if value is None:
        #     return False

        if not self.private_cursor.buffer_:
            raise Exception("Buffer not set")

        for i in range(self.private_cursor._model.rowCount()):
            pk_value = self.private_cursor.buffer_.pK()
            if pk_value is None:
                raise ValueError("pk_value is empty!")

            if self.private_cursor._model.value(i, pk_value) == value:
                return self.move(i) if self.at() != i else True

        return False

    def at(self) -> int:
        """
        Return the current position to which the cursor points.

        @return Index position.
        """

        if not self.currentRegister():
            row = 0
        else:
            row = self.currentRegister()

        if row < 0:
            return -1

        if row >= self.size():
            return -2
        # LOGGER.debug("%s.Row %s ----> %s" % (self.curName(), row, self))
        return row

    def isValid(self) -> bool:
        """
        Specify whether the position to which the cursor points is valid.

        @return True if ok else False.
        """

        if self.at() >= 0 and self._valid:
            return True
        else:
            return False

    @decorators.pyqtSlot()
    @decorators.pyqtSlot(str)
    def refresh(self, field_name: Optional[str] = None) -> None:
        """
        Refresh the cursor content.

        If no related cursor has been indicated, get the complete cursor, according to the query
        default. If it has been indicated that it depends on another cursor with which it relates,
        The content of the cursor will depend on the value of the field that determines the relationship.
        If the name of a field is indicated, it is considered that the buffer has only changed in that
        field and thus avoid repetitions in the soda.

        @param field_name Name of the buffer field that has changed
        """
        if not self.private_cursor.metadata_:
            return

        if (
            self.private_cursor.cursor_relation_ is not None
            and self.private_cursor.relation_ is not None
        ):
            self.clearPersistentFilter()
            if not self.private_cursor.cursor_relation_.metadata():
                return
            if (
                self.private_cursor.cursor_relation_.metadata().primaryKey() == field_name
                and self.private_cursor.cursor_relation_.modeAccess() == self.Insert
            ):
                return

            if not field_name or self.private_cursor.relation_.foreignField() == field_name:
                if self.private_cursor.buffer_:
                    self.private_cursor.buffer_.clear_buffer()
                self.refreshDelayed()
                return
        else:
            self.private_cursor._model.refresh()  # Hay que hacer refresh previo pq si no no recoge valores de un commitBuffer paralelo
            # self.select()
            pos = self.atFrom()
            if pos > self.size():
                pos = self.size() - 1

            if not self.seek(pos, False, True):

                if self.private_cursor.buffer_:
                    self.private_cursor.buffer_.clear_buffer()
                self.newBuffer.emit()

    @decorators.pyqtSlot()
    def refreshDelayed(self, msec: int = 50) -> None:  # keep > 50ms
        """
        Update the recordset with a delay.

        Accept a lapse of time in milliseconds, activating the internal timer for
        to perform the final refresh upon completion of said lapse.

        @param msec Amount of lapsus time, in milliseconds.
        """
        # if self.buffer():
        #    return
        if not self.private_cursor.timer_:
            return

        obj = self.sender()

        if not obj or not obj.inherits("QTimer"):
            self.private_cursor.timer_.start(msec)
            return
        else:
            self.private_cursor.timer_.stop()

        # self.private_cursor.timer_.start(msec)
        # cFilter = self.filter()
        # self.setFilter(None)
        # if cFilter == self.filter() and self.isValid():
        #    return

        self.setFilter("")

        self.select()
        pos = self.atFrom()
        if not self.seek(pos, False, True):
            self.newBuffer.emit()

        cur_relation = self.private_cursor.cursor_relation_
        relation = self.private_cursor.relation_

        if cur_relation and relation and cur_relation.metadata():
            value = self.valueBuffer(relation.field())
            if value:
                foreign_value = cur_relation.valueBuffer(relation.foreignField())
                if foreign_value != value:
                    cur_relation.setValueBuffer(relation.foreignField(), value)

    def primeInsert(self) -> None:
        """
        Refill the buffer for the first time.
        """

        if not self.private_cursor.buffer_:
            self.private_cursor.buffer_ = pnbuffer.PNBuffer(self)

        self.private_cursor.buffer_.primeInsert()

    def primeUpdate(self) -> pnbuffer.PNBuffer:
        """
        Update the buffer.

        @return buffer refresh.
        """

        if self.private_cursor.buffer_ is None:
            self.private_cursor.buffer_ = pnbuffer.PNBuffer(self)
        # LOGGER.warning("Realizando primeUpdate en pos %s y estado %s , filtro %s", self.at(), self.modeAccess(), self.filter())
        self.private_cursor.buffer_.primeUpdate(self.at())
        return self.private_cursor.buffer_

    @decorators.pyqtSlot()
    def refreshBuffer(self) -> bool:
        """
        Refresh the buffer according to the established access mode.

        Bring cursor information to the buffer to edit or navigate, or prepare the buffer to
        insert or delete

        If there is a counter field, the "calculateCounter" function of the script of the
        context (see FLSqlCursor :: ctxt_) set for the cursor. This function is passed
        as an argument the name of the counter field and must return the value it must contain
        that field

        @return TRUE if the refreshment could be performed, FALSE otherwise
        """
        from pineboolib.application.safeqsa import SafeQSA

        if not self.private_cursor.metadata_:
            raise Exception("Not initialized")
        if not self._action:
            raise Exception("Not initialized")

        if (
            isinstance(self.sender(), QtCore.QTimer)
            and self.private_cursor.mode_access_ != self.Browse
        ):
            return False

        if self.private_cursor.mode_access_ != self.Insert:
            if not self.isValid():
                return False

        if self.private_cursor.mode_access_ == self.Insert:
            if not self.commitBufferCursorRelation():
                return False

            if not self.private_cursor.buffer_:
                self.private_cursor.buffer_ = pnbuffer.PNBuffer(self)

            self.setNotGenerateds()

            field_list = self.private_cursor.metadata_.fieldList()

            for field in field_list:
                field_name = field.name()

                if self.private_cursor.buffer_ is None:
                    raise Exception("buffer is empty!")

                self.private_cursor.buffer_.setNull(field_name)
                if not self.private_cursor.buffer_.isGenerated(field_name):
                    continue
                type_ = field.type()
                # fltype = FLFieldself.private_cursor.metadata_.flDecodeType(type_)
                # fltype = self.private_cursor.metadata_.field(field_name).flDecodeType(type_)
                default_value = field.defaultValue()
                if default_value is not None:
                    # default_value.cast(fltype)
                    self.private_cursor.buffer_.setValue(field_name, default_value)

                if type_ == "serial":
                    val = self.db().nextSerialVal(self.table(), field_name)
                    if val is None:
                        val = 0
                    self.private_cursor.buffer_.setValue(field_name, val)
                elif type_ == "timestamp":
                    if not field.allowNull():
                        val = self.db().getTimeStamp()
                        self.private_cursor.buffer_.setValue(field_name, val)
                if field.isCounter():
                    from pineboolib.application.database import utils

                    siguiente = None
                    if self._action.scriptFormRecord():
                        context_ = SafeQSA.formrecord(
                            "formRecord%s" % self._action.scriptFormRecord()[:-3]
                        ).iface
                        function_counter = getattr(context_, "calculateCounter", None)
                        if function_counter is None:
                            siguiente = utils.next_counter(field_name, self)
                        else:
                            siguiente = function_counter()
                    else:
                        siguiente = utils.next_counter(field_name, self)

                    if siguiente:
                        self.private_cursor.buffer_.setValue(field_name, siguiente)

            if (
                self.private_cursor.cursor_relation_ is not None
                and self.private_cursor.relation_ is not None
                and self.private_cursor.cursor_relation_.metadata()
            ):
                self.setValueBuffer(
                    self.private_cursor.relation_.field(),
                    self.private_cursor.cursor_relation_.valueBuffer(
                        self.private_cursor.relation_.foreignField()
                    ),
                )

            self.private_cursor.undoAcl()
            self.updateBufferCopy()
            self.newBuffer.emit()

        elif self.private_cursor.mode_access_ == self.Edit:
            if not self.commitBufferCursorRelation():
                return False

            self.primeUpdate()
            if self.isLocked() and not self.private_cursor._acos_cond_name:
                self.private_cursor.mode_access_ = self.Browse

            self.setNotGenerateds()
            self.updateBufferCopy()
            self.private_cursor.doAcl()
            self.newBuffer.emit()

        elif self.private_cursor.mode_access_ == self.Del:

            if self.isLocked():
                self.private_cursor.msgBoxWarning("Registro bloqueado, no se puede eliminar")
                self.private_cursor.mode_access_ = self.Browse
                return False

            self.primeUpdate()
            self.setNotGenerateds()
            self.updateBufferCopy()

        elif self.private_cursor.mode_access_ == self.Browse:
            self.primeUpdate()
            self.setNotGenerateds()
            self.newBuffer.emit()
            self.private_cursor.doAcl()

        else:
            LOGGER.error("refreshBuffer(). No hay definido modeAccess()")

        return True

    @decorators.pyqtSlot()
    def setEditMode(self) -> bool:
        """
        Change the cursor to Edit mode.

        @return True if the cursor is in Edit mode or was in Insert mode and has successfully switched to Edit mode
        """
        if self.private_cursor.mode_access_ == self.Insert:
            if not self.commitBuffer():
                return False
            self.refresh()
            self.setModeAccess(self.Edit)
        elif self.private_cursor.mode_access_ == self.Edit:
            return True

        return False

    @decorators.pyqtSlot()
    def seek(self, index: int, relative: Optional[bool] = False, emite: bool = False) -> bool:
        """
        Simply refreshes the buffer with the FLSqlCursor :: refreshBuffer () method.

        @param index. New position.
        @param relative. Not used.
        @param emite If TRUE emits the FLSqlCursor :: currentChanged () signal.

        @return True if ok or False.
        """
        result = self.move(index)

        if result and self.buffer():
            if emite:
                self.currentChanged.emit(self.at())

            result = self.refreshBuffer()

        return result

    @decorators.pyqtSlot()
    @decorators.pyqtSlot(bool)
    def next(self, emite: bool = True) -> bool:
        """
        Move the position to which the +1 position and execute refreshBuffer.

        @param emits If TRUE emits the FLSqlCursor :: currentChanged () signal
        """
        # if self.private_cursor.mode_access_ == self.Del:
        #    return False

        result = self.moveby(1)
        if result:
            if emite:
                self.private_cursor._current_changed.emit(self.at())

            result = self.refreshBuffer()

        return result

    def moveby(self, pos: int) -> bool:
        """
        Move the cursor to the specified position.

        @param i. index position to seek.
        @return True if ok else False.
        """

        if self.currentRegister():
            pos += self.currentRegister()

        return self.move(pos)

    @decorators.pyqtSlot()
    @decorators.pyqtSlot(bool)
    def prev(self, emite: bool = True) -> bool:
        """
        Move the position to which the -1 position and execute refreshBuffer.

        @param emits If TRUE emits the FLSqlCursor :: currentChanged () signal
        """
        # if self.private_cursor.mode_access_ == self.Del:
        #    return False

        result = self.moveby(-1)

        if result:
            if emite:
                self.private_cursor._current_changed.emit(self.at())

            result = self.refreshBuffer()

        return result

    def move(self, row: int = -1) -> bool:
        """
        Move the cursor across the table.

        @return True if ok else False.
        """
        # if row is None:
        #     row = -1
        model = self.private_cursor._model
        if not model:
            return False

        if row < 0:
            row = -1
        # while row >= model.rows and model.canFetchMoreRows:
        #    model.updateRows()

        # if row >= model.rows:
        #    row = model.rows
        if not model.seekRow(row):
            return False

        row = model._current_row_index
        if self.currentRegister() == row:
            return False

        top_left = model.index(row, 0)
        botton_right = model.index(row, model.cols - 1)
        new_selection = QtCore.QItemSelection(top_left, botton_right)
        if self._selection is None:
            raise Exception("Call setAction first.")
        self._selection.select(new_selection, QtCore.QItemSelectionModel.ClearAndSelect)
        # self.private_cursor._current_changed.emit(self.at())
        if row < self.size() and row >= 0:
            self.private_cursor._currentregister = row
            return True
        else:
            return False

    @decorators.pyqtSlot()
    @decorators.pyqtSlot(bool)
    def first(self, emite: bool = True) -> bool:
        """
        Move the position to which the first position and execute refreshBuffer.

        @param emits If TRUE emits the FLSqlCursor :: currentChanged () signal
        """
        # if self.private_cursor.mode_access_ == self.Del:
        #    return False
        if not self.currentRegister() == 0:
            result = self.move(0)
        else:
            result = True
        if result:
            if emite:
                self.private_cursor._current_changed.emit(self.at())

            result = self.refreshBuffer()

        return result

    @decorators.pyqtSlot()
    @decorators.pyqtSlot(bool)
    def last(self, emite: bool = True) -> bool:
        """
        Move the position to which the last position and execute refreshBuffer.

        @param emits If TRUE emits the FLSqlCursor :: currentChanged () signal
        """
        # if self.private_cursor.mode_access_ == self.Del:
        #    return False

        result = self.move(self.size() - 1)
        if result:
            if emite:
                self.private_cursor._current_changed.emit(self.at())

            result = self.refreshBuffer()

        return result

    @decorators.pyqtSlot()
    def __del__(self, invalidate: bool = True) -> None:
        """
        Check if it is deleted in cascade, if so, also delete related records in 1M cardinality.

        @param invalidate. Not used.
        """
        # LOGGER.trace("FLSqlCursor(%s). Eliminando cursor" % self.curName(), self)
        # delMtd = None
        # if self.private_cursor.metadata_:
        #     if not self.private_cursor.metadata_.inCache():
        #         delMtd = True

        message = None

        if not hasattr(self, "d"):
            return

        metadata = self.private_cursor.metadata_

        # FIXME: Pongo que tiene que haber mas de una trasaccion abierta
        if self.private_cursor._transactions_opened:
            LOGGER.warning(
                "FLSqlCursor(%s).Transacciones abiertas!! %s",
                self.curName(),
                self.private_cursor._transactions_opened,
            )
            table_name = self.curName()
            if metadata:
                table_name = metadata.name()

            message = (
                "Se han detectado transacciones no finalizadas en la última operación.\n"
                "Se van a cancelar las transacciones pendientes.\n"
                "Los últimos datos introducidos no han sido guardados, por favor\n"
                "revise sus últimas acciones y repita las operaciones que no\n"
                "se han guardado.\nSqlCursor::~SqlCursor: %s\n" % table_name
            )
            self.rollbackOpened(-1, message)

    #    # self.destroyed.emit()
    #    # self.private_cursor._count_ref_cursor = self.private_cursor._count_ref_cursor - 1     FIXME

    @decorators.pyqtSlot()
    def select(
        self, final_filter: str = "", sort: Optional[str] = None
    ) -> bool:  # sort = QtCore.QSqlIndex()
        """
        Execute the filter specified in the cursor and refresh the information of the affected records.

        @param _filter. Optional filter.
        @param sort. Optional sort order.

        @return True if ok or False.
        """
        # _filter = _filter if _filter is not None else self.filter()
        if not self.private_cursor.metadata_:
            return False

        # bFilter = self.baseFilter()
        # finalFilter = bFilter
        # if _filter:
        #    if bFilter:
        #        if _filter not in bFilter:
        #            finalFilter = "%s AND %s" % (bFilter, _filter)
        #        else:
        #            finalFilter = bFilter
        #
        #    else:
        #        finalFilter = _filter

        if (
            self.private_cursor.cursor_relation_
            and self.private_cursor.cursor_relation_.modeAccess() == self.Insert
            and not self.curFilter()
        ):
            final_filter = "1 = 0"

        if final_filter:
            self.setFilter(final_filter)

        if sort:
            self.private_cursor._model.setSortOrder(sort)

        self.private_cursor._model.refresh()
        self.private_cursor._currentregister = -1

        if self.private_cursor.cursor_relation_ and self.modeAccess() == self.Browse:
            self.private_cursor._currentregister = self.atFrom()

        self.refreshBuffer()
        # if self.modeAccess() == self.Browse:
        #    self.private_cursor._currentregister = -1
        self.newBuffer.emit()

        return True

    @decorators.pyqtSlot()
    def setSort(self, sort_order: str) -> None:
        """
        Specify the sort order in the tablemodel.

        @param str. new sort order.
        """
        self.private_cursor._model.setSortOrder(sort_order)

    @decorators.pyqtSlot()
    def baseFilter(self) -> str:
        """
        Return the base filter.

        @return base filter.
        """

        relation_filter = None
        final_filter = ""

        if (
            self.private_cursor.cursor_relation_
            and self.private_cursor.relation_
            and self.private_cursor.metadata_
            and self.private_cursor.cursor_relation_.metadata()
        ):
            relation_value = self.private_cursor.cursor_relation_.valueBuffer(
                self.private_cursor.relation_.foreignField()
            )
            field = self.private_cursor.metadata_.field(self.private_cursor.relation_.field())

            if field is not None and relation_value is not None:

                relation_filter = (
                    self.db().connManager().manager().formatAssignValue(field, relation_value, True)
                )
                filter_assoc = self.private_cursor.cursor_relation_.filterAssoc(
                    self.private_cursor.relation_.foreignField(), self.private_cursor.metadata_
                )
                if filter_assoc:
                    if not relation_filter:
                        relation_filter = filter_assoc
                    else:
                        relation_filter = "%s AND %s" % (relation_filter, filter_assoc)

        if self.mainFilter():
            final_filter = self.mainFilter()

        if relation_filter:
            if not final_filter:
                final_filter = relation_filter
            else:
                if relation_filter not in final_filter:
                    final_filter = "%s AND %s" % (final_filter, relation_filter)

        # if self.filter():
        #    if final_filter and self.filter() not in final_filter:
        #        final_filter = "%s AND %s" % (final_filter, self.filter())
        #    else:
        #        final_filter = self.filter()

        return final_filter

    @decorators.pyqtSlot()
    def curFilter(self) -> str:
        """
        Return the actual filter.

        @return actual filter.
        """

        filter = self.filter()
        base_filter = self.baseFilter()
        if filter:
            while filter.endswith(";"):
                filter = filter[0 : len(filter) - 1]

        if not base_filter:
            return filter
        else:
            if not filter or filter in base_filter:
                return base_filter
            else:
                if base_filter in filter:
                    return filter
                else:
                    return "%s AND %s" % (base_filter, filter)

    @decorators.pyqtSlot()
    def setFilter(self, _filter: str = "") -> None:
        """
        Specify the cursor filter.

        @param _filter. Text string with the filter to apply.
        """

        # self.private_cursor.filter_ = None

        final_filter = _filter
        base_filter = self.baseFilter()
        if base_filter:
            if not final_filter:
                final_filter = base_filter
            elif final_filter in base_filter:
                final_filter = base_filter
            elif base_filter not in final_filter:
                final_filter = base_filter + " AND " + final_filter

        if (
            final_filter
            and self.private_cursor._persistent_filter
            and self.private_cursor._persistent_filter not in final_filter
        ):
            final_filter = final_filter + " OR " + self.private_cursor._persistent_filter

        self.private_cursor._model.where_filters["filter"] = final_filter

    @decorators.pyqtSlot()
    def insertRecord(self, wait: bool = True) -> None:
        """
        Open the form record in insert mode.

        @param wait. wait to form record close.
        """

        LOGGER.trace("insertRecord %s", self._action and self._action.name())
        self.openFormInMode(self.Insert, wait)

    @decorators.pyqtSlot()
    def editRecord(self, wait: bool = True) -> None:
        """
        Open the form record in edit mode.

        @param wait. wait to form record close.
        """

        LOGGER.trace("editRecord %s", self.actionName())
        if self.private_cursor.needUpdate():
            if not self.private_cursor.metadata_:
                raise Exception("self.private_cursor.metadata_ is not defined!")

            primary_key = self.private_cursor.metadata_.primaryKey()
            primary_key_value = self.valueBuffer(primary_key)
            self.refresh()
            pos = self.atFromBinarySearch(primary_key, primary_key_value)
            if not pos == self.at():
                self.seek(pos, False, False)

        self.openFormInMode(self.Edit, wait)

    @decorators.pyqtSlot()
    def browseRecord(self, wait: bool = True) -> None:
        """
        Open the form record in browse mode.

        @param wait. wait to form record close.
        """

        LOGGER.trace("browseRecord %s", self.actionName())
        if self.private_cursor.needUpdate():
            if not self.private_cursor.metadata_:
                raise Exception("self.private_cursor.metadata_ is not defined!")
            primary_key = self.private_cursor.metadata_.primaryKey()
            primary_key_value = self.valueBuffer(primary_key)
            self.refresh()
            pos = self.atFromBinarySearch(primary_key, primary_key_value)
            if not pos == self.at():
                self.seek(pos, False, False)
        self.openFormInMode(self.Browse, wait)

    @decorators.pyqtSlot()
    def deleteRecord(self, wait: bool = True) -> None:
        """
        Open the form record in insert mode.Ask for confirmation to delete the record.

        @param wait. wait to record delete to continue.
        """

        LOGGER.trace("deleteRecord %s", self.actionName())
        self.openFormInMode(self.Del, wait)
        # self.private_cursor._action.openDefaultFormRecord(self)

    def copyRecord(self) -> None:
        """
        Perform the action of inserting a new record, and copy the value of the record fields current.
        """

        if not self.private_cursor.metadata_ or not self.private_cursor.buffer_:
            return

        if not self.isValid() or self.size() <= 0:
            self.private_cursor.msgBoxWarning(self.tr("No hay ningún registro seleccionado"))
            return

        field_list = self.private_cursor.metadata_.fieldList()
        if not field_list:
            return

        # ifdef AQ_MD5_CHECK
        if self.private_cursor.needUpdate():
            primary_key = self.private_cursor.metadata_.primaryKey()
            pk_value = self.valueBuffer(primary_key)
            self.refresh()
            pos = self.atFromBinarySearch(primary_key, str(pk_value))
            if pos != self.at():
                self.seek(pos, False, True)
        # endif

        buffer_aux = self.private_cursor.buffer_
        self.insertRecord()

        for item in field_list:

            if (
                self.private_cursor.buffer_.isNull(item.name())
                and not item.isPrimaryKey()
                and not self.private_cursor.metadata_.fieldListOfCompoundKey(item.name())
                and not item.calculated()
            ):
                self.private_cursor.buffer_.setValue(item.name(), buffer_aux.value(item.name()))

            del buffer_aux
            self.newBuffer.emit()

    @decorators.pyqtSlot()
    def chooseRecord(self, wait: bool = True) -> None:
        """
        Perform the action associated with choosing a cursor record.

        By default the form of record edition, calling the PNSqlCursor :: editRecord () method, if the PNSqlCursor :: edition flag
        indicates TRUE, if it indicates FALSE this method does nothing
        """

        from pineboolib.core.settings import config

        if not config.value("ebcomportamiento/FLTableDoubleClick", False):
            if self.private_cursor.edition_:
                self.editRecord(wait)
            else:
                if self.private_cursor.browse_:
                    self.browseRecord(wait)
        else:
            if self.private_cursor.browse_:
                self.browseRecord(wait)

        self.recordChoosed.emit()

    def setForwardOnly(self, value: bool) -> None:
        """
        Avoid refreshing the associated model.
        """

        if not self.private_cursor._model:
            return

        self.private_cursor._model.disable_refresh(value)

    @decorators.pyqtSlot()
    def commitBuffer(self, emite: bool = True, check_locks: bool = False) -> bool:
        """
        Send the contents of the buffer to the cursor, or perform the appropriate action for the cursor.

        All changes made to the buffer become effective at the cursor when invoking this method.
        The way to make these changes is determined by the access mode established for
        the cursor, see FLSqlCursor :: Mode, if the mode is edit or insert update with the new values ​​of
        the fields of the record, if the mode is delete deletes the record, and if the mode is navigation it does nothing.
        First of all it also checks referential integrity by invoking the FLSqlCursor :: checkIntegrity () method.

        If a calculated field exists, the "calculateField" function of the script of the
        context (see FLSqlCursor :: ctxt_) set for the cursor. This function is passed
        as an argument the name of the calculated field and must return the value it must contain
        that field, e.g. if the field is the total of an invoice and of type calculated the function
        "calculateField" must return the sum of lines of invoices plus / minus taxes and
        discounts

        @param issues True to emit cursorUpdated signal
        @param check_locks True to check block risks for this table and the current record
        @return TRUE if the buffer could be delivered to the cursor, and FALSE if the delivery failed
        """

        if not self.private_cursor.buffer_ or not self.private_cursor.metadata_:
            return False

        if (
            self.db().interactiveGUI()
            and self.db().canDetectLocks()
            and (check_locks or self.private_cursor.metadata_.detectLocks())
        ):
            self.checkRisksLocks()
            if self.private_cursor._in_risks_locks:
                ret = QtWidgets.QMessageBox.warning(
                    QtWidgets.QApplication.activeWindow(),
                    "Bloqueo inminente",
                    "Los registros que va a modificar están bloqueados actualmente.\n"
                    "Si continua hay riesgo de que su conexión quede congelada hasta finalizar el bloqueo.\n"
                    "\n¿ Desa continuar aunque exista riesgo de bloqueo ?",
                    QtWidgets.QMessageBox.Ok,
                    cast(
                        QtWidgets.QMessageBox.StandardButton,
                        QtWidgets.QMessageBox.No
                        | QtWidgets.QMessageBox.Default
                        | QtWidgets.QMessageBox.Escape,
                    ),
                )
                if ret == QtWidgets.QMessageBox.No:
                    return False

        if not self.checkIntegrity():
            return False

        field_name_check = None
        if self.modeAccess() in [self.Edit, self.Insert]:
            field_list = self.private_cursor.metadata_.fieldList()

            for field in field_list:
                if field.isCheck():
                    field_name_check = field.name()
                    self.private_cursor.buffer_.setGenerated(field, False)

                    if self.private_cursor._buffer_copy:
                        self.private_cursor._buffer_copy.setGenerated(field, False)
                    continue

                if not self.private_cursor.buffer_.isGenerated(field.name()):
                    continue

                if (
                    self.context()
                    and hasattr(self.context(), "calculateField")
                    and field.calculated()
                ):
                    value = application.PROJECT.call(
                        "calculateField", [field.name()], self.context(), False
                    )

                    if value not in (True, False, None):
                        self.setValueBuffer(field.name(), value)

        function_before = None
        function_after = None

        id_module = self.db().connManager().managerModules().idModuleOfFile("%s.mtd" % self.table())

        # FIXME: module_script is FLFormDB
        module_script = (
            application.PROJECT.actions[id_module].load()
            if id_module in application.PROJECT.actions.keys()
            else application.PROJECT.actions["sys"].load()
        )
        module_iface: Any = getattr(module_script, "iface", None)

        if not self.modeAccess() == PNSqlCursor.Browse and self.activatedCommitActions():

            function_before = "beforeCommit_%s" % (self.table())
            function_after = "afterCommit_%s" % (self.table())

            if function_before:
                field_name = getattr(module_iface, function_before, None)
                value = None
                if field_name is not None:
                    try:
                        value = field_name(self)
                    except Exception:
                        QtWidgets.QMessageBox.warning(
                            QtWidgets.QApplication.focusWidget(),
                            "Error",
                            error_manager.error_manager(
                                traceback.format_exc(limit=-6, chain=False)
                            ),
                        )
                    if value and not isinstance(value, bool) or value is False:
                        return False

        # primary_key = self.private_cursor.metadata_.primaryKey()
        updated = False
        # savePoint = None

        if self.modeAccess() == self.Insert:
            if self.private_cursor.cursor_relation_ and self.private_cursor.relation_:
                if self.private_cursor.cursor_relation_.metadata() and self.private_cursor.cursor_relation_.valueBuffer(
                    self.private_cursor.relation_.foreignField()
                ):
                    self.setValueBuffer(
                        self.private_cursor.relation_.field(),
                        self.private_cursor.cursor_relation_.valueBuffer(
                            self.private_cursor.relation_.foreignField()
                        ),
                    )
                    self.private_cursor.cursor_relation_.setAskForCancelChanges(True)

            pk_name = self.private_cursor.buffer_.pK()
            if pk_name is None:
                raise ValueError("primery key is not defined!")
            pk_value = self.private_cursor.buffer_.value(pk_name)

            if not (self.private_cursor._model.insert(self)):
                return False
            self.selection().currentRowChanged.disconnect(
                self.selection_currentRowChanged
            )  # Evita vaciado de buffer al hacer removeRows
            self.private_cursor._model.refresh()
            self.selection().currentRowChanged.connect(self.selection_currentRowChanged)
            pk_row = self.private_cursor._model.findPKRow((pk_value,))

            if pk_row is not None:
                self.move(pk_row)

            updated = True

        elif self.modeAccess() == self.Edit:
            database = self.db()
            if database is None:
                raise Exception("db is not defined!")

            # if not db.canSavePoint():
            #    if db.currentSavePoint_:
            #        db.currentSavePoint_.saveEdit(primary_key, self.bufferCopy(), self)

            # if function_after and self.private_cursor._activated_commit_actions:
            #    if not savePoint:
            #        from . import pnsqlsavepoint

            #        savePoint = pnsqlsavepoint.PNSqlSavePoint(None)
            #    savePoint.saveEdit(primary_key, self.bufferCopy(), self)

            if self.private_cursor.cursor_relation_ and self.private_cursor.relation_:
                if self.private_cursor.cursor_relation_.metadata():
                    self.private_cursor.cursor_relation_.setAskForCancelChanges(True)
            LOGGER.trace("commitBuffer -- Edit . 20 . ")
            if self.isModifiedBuffer():

                LOGGER.trace("commitBuffer -- Edit . 22 . ")
                if not self.update(False):
                    return False

                LOGGER.trace("commitBuffer -- Edit . 25 . ")

                updated = True
                self.setNotGenerateds()
            LOGGER.trace("commitBuffer -- Edit . 30 . ")

        elif self.modeAccess() == self.Del:

            if self.private_cursor.cursor_relation_ and self.private_cursor.relation_:
                if self.private_cursor.cursor_relation_.metadata():
                    self.private_cursor.cursor_relation_.setAskForCancelChanges(True)

            value = application.PROJECT.call(
                "recordDelBefore%s" % self.table(), [self], self.context(), False
            )
            if value and not isinstance(value, bool):
                return False

            if not self.private_cursor.buffer_:
                self.primeUpdate()

            field_list = self.private_cursor.metadata_.fieldList()

            for field in field_list:

                field_name = field.name()
                if not self.private_cursor.buffer_.isGenerated(field_name):
                    continue

                result = None
                if not self.private_cursor.buffer_.isNull(field_name):
                    result = self.private_cursor.buffer_.value(field_name)

                if result is None:
                    continue

                relation_list = field.relationList()
                if not relation_list:
                    continue
                else:
                    for relation in relation_list:
                        cursor = PNSqlCursor(relation.foreignTable())
                        foreign_mtd = cursor.private_cursor.metadata_
                        if foreign_mtd is None:
                            continue
                        foreign_field = foreign_mtd.field(relation.foreignField())
                        if foreign_field is None:
                            continue

                        relation_m1 = foreign_field.relationM1()

                        if relation_m1 and relation_m1.deleteCascade():
                            cursor.setForwardOnly(True)
                            cursor.select(
                                self.conn()
                                .connManager()
                                .manager()
                                .formatAssignValue(
                                    relation.foreignField(), foreign_field, result, True
                                )
                            )
                            while cursor.next():
                                cursor.setModeAccess(self.Del)
                                cursor.refreshBuffer()
                                if not cursor.commitBuffer(False):
                                    return False

            if not self.private_cursor._model.delete(self):
                raise Exception("Error deleting row!")

            application.PROJECT.call(
                "recordDelAfter%s" % self.table(), [self], self.context(), False
            )

            updated = True

        if updated and self.lastError():
            return False

        if not self.modeAccess() == self.Browse and self.activatedCommitActions():

            if function_after:
                field_name = getattr(module_script.iface, function_after, None)

                if field_name is not None:
                    value = None
                    try:
                        value = field_name(self)
                    except Exception:
                        QtWidgets.QMessageBox.warning(
                            QtWidgets.QApplication.focusWidget(),
                            "Error",
                            error_manager.error_manager(
                                traceback.format_exc(limit=-6, chain=False)
                            ),
                        )
                    if value and not isinstance(value, bool) or value is False:
                        return False

        if self.modeAccess() in (self.Del, self.Edit):
            self.setModeAccess(self.Browse)

        elif self.modeAccess() == self.Insert:
            self.setModeAccess(self.Edit)

        if updated:
            if field_name_check:
                self.private_cursor.buffer_.setGenerated(field_name_check, True)

                if self.private_cursor._buffer_copy:
                    self.private_cursor._buffer_copy.setGenerated(field_name_check, True)

            self.setFilter("")
            # self.clearMapCalcFields()

            if emite:
                self.cursorUpdated.emit()

        self.bufferCommited.emit()
        return True

    @decorators.pyqtSlot()
    def commitBufferCursorRelation(self) -> bool:
        """
        Send the contents of the cursor buffer related to that cursor.

        It makes all changes in the related cursor buffer effective by placing itself in the registry corresponding receiving changes.
        """

        result = True
        active_widget_enabled = False
        active_widget = None

        cursor_relation = self.private_cursor.cursor_relation_

        if cursor_relation is None or self.relation() is None:
            return result

        if application.PROJECT.DGI.localDesktop():

            active_widget = QtWidgets.QApplication.activeModalWidget()
            if not active_widget:
                active_widget = QtWidgets.QApplication.activePopupWidget()
            if not active_widget:
                active_widget = QtWidgets.QApplication.activeWindow()

            if active_widget:
                active_widget_enabled = active_widget.isEnabled()

        if self.private_cursor.mode_access_ == self.Insert:
            if cursor_relation.metadata() and cursor_relation.modeAccess() == self.Insert:
                if active_widget and active_widget_enabled:
                    active_widget.setEnabled(False)
                if not cursor_relation.commitBuffer():
                    self.private_cursor.mode_access_ = self.Browse
                    result = False
                else:
                    self.setFilter("")
                    cursor_relation.refresh()
                    cursor_relation.setModeAccess(self.Edit)
                    cursor_relation.refreshBuffer()

                if active_widget and active_widget_enabled:
                    active_widget.setEnabled(True)

        elif self.private_cursor.mode_access_ in [self.Browse, self.Edit]:
            if cursor_relation.metadata() and cursor_relation.modeAccess() == self.Insert:
                if active_widget and active_widget_enabled:
                    active_widget.setEnabled(False)

                if not cursor_relation.commitBuffer():
                    self.private_cursor.mode_access_ = self.Browse
                    result = False
                else:
                    cursor_relation.refresh()
                    cursor_relation.setModeAccess(self.Edit)
                    cursor_relation.refreshBuffer()

                if active_widget and active_widget_enabled:
                    active_widget.setEnabled(True)

        return result

    @decorators.pyqtSlot()
    def transactionLevel(self) -> int:
        """
        Transaction level.

        @return The current level of transaction nesting, 0 there is no transaction.
        """

        if self.db():
            return self.db().transactionLevel()
        else:
            return 0

    @decorators.pyqtSlot()
    def transactionsOpened(self) -> List[str]:
        """
        Transactions opened by this cursor.

        @return The list with the levels of transactions that this cursor has initiated and remain open
        """
        lista = []
        for item in self.private_cursor._transactions_opened:
            lista.append(str(item))

        return lista

    @decorators.pyqtSlot()
    @decorators.BetaImplementation
    def rollbackOpened(self, count: int = -1, message: str = "") -> None:
        """
        Undo transactions opened by this cursor.

        @param count Number of transactions to be undone, -1 all.
        @param msg Text string that is displayed in a dialog box before undoing transactions. If it is empty it shows nothing.
        """

        count = len(self.private_cursor._transactions_opened) if count < 0 else count
        if count > 0 and message != "":
            table_name: str = self.table() if self.private_cursor.metadata_ else self.curName()
            message = "%sSqlCursor::rollbackOpened: %s %s" % (message, count, table_name)
            self.private_cursor.msgBoxWarning(message, False)
        elif count > 0:
            LOGGER.trace("rollbackOpened: %s %s", count, self.curName())

        i = 0
        while i < count:
            LOGGER.trace("Deshaciendo transacción abierta", self.transactionLevel())
            self.rollback()
            i = i + 1

    @decorators.pyqtSlot()
    def commitOpened(self, count: int = -1, message: str = None) -> None:
        """
        Complete transactions opened by this cursor.

        @param count Number of transactions to finish, -1 all.
        @param msg A text string that is displayed in a dialog box before completing transactions. If it is empty it shows nothing.
        """
        count = len(self.private_cursor._transactions_opened) if count < 0 else count
        table_name: str = self.table() if self.private_cursor.metadata_ else self.curName()

        if count and message:
            message = "%sSqlCursor::commitOpened: %s %s" % (message, str(count), table_name)
            self.private_cursor.msgBoxWarning(message, False)
            LOGGER.warning(message)
        elif count > 0:
            LOGGER.warning("SqlCursor::commitOpened: %d %s" % (count, self.curName()))

        i = 0
        while i < count:
            LOGGER.warning("Terminando transacción abierta %s", self.transactionLevel())
            self.commit()
            i = i + 1

    @decorators.pyqtSlot()
    @decorators.NotImplementedWarn
    def checkRisksLocks(self, terminate: bool = False) -> bool:
        """
        Enter a lockout risk loop for this table and the current record.

        The loop continues as long as there are locks, until this method is called again with 'terminate'
        activated or when the user cancels the operation.

        @param terminate True will end the check loop if it is active
        """

        return True

    @decorators.pyqtSlot()
    def setAcTable(self, acos) -> None:
        """
        Set the global access for the table, see FLSqlCursor :: setAcosCondition ().

        This will be the permission to apply to all default fields.

        @param ac Global permission; eg: "r-", "-w"
        """

        self.private_cursor._id_ac += 1
        self.private_cursor.id_ = "%s%s%s" % (
            self.private_cursor._id_ac,
            self.private_cursor._id_acos,
            self.private_cursor._id_cond,
        )
        self.private_cursor._ac_perm_table = acos

    @decorators.pyqtSlot()
    def setAcosTable(self, acos):
        """
        Set the access control list (ACOs) for the fields in the table, see FLSqlCursor :: setAcosCondition ().

        This list of texts should have in their order components the names of the fields,
        and in the odd order components the permission to apply to that field,
        eg: "name", "r-", "description", "-", "telephone", "rw", ...

        The permissions defined here overwrite the global.

        @param acos List of text strings with the names of fields and permissions.
        """

        self.private_cursor._id_acos += 1
        self.private_cursor.id_ = "%s%s%s" % (
            self.private_cursor._id_ac,
            self.private_cursor._id_acos,
            self.private_cursor._id_cond,
        )
        self.private_cursor._acos_table = acos

    @decorators.pyqtSlot()
    def setAcosCondition(self, condition_name: str, condition: int, condition_value: Any):
        """
        Set the condition that must be met to apply access control.

        For each record this condition is evaluated and if it is met, the rule applies
        of access control set with FLSqlCursor :: setAcTable and FLSqlCursor :: setAcosTable.

        setAcosCondition ("name", VALUE, "pepe"); // valueBuffer ("name") == "pepe"
        setAcosCondition ("name", REGEXP, "pe *"); // QRegExp ("pe *") .exactMatch (valueBuffer ("name") .toString ())
        setAcosCondition ("sys.checkAcos", FUNCTION, true); // call ("sys.checkAcos") == true



        @param condition Type of evaluation;
                    VALUE compares with a fixed value
                    REGEXP compares with a regular expression
                    FUNCTION compares with the value returned by a script function

        @param condition_name If it is empty, the condition is not evaluated and the rule is never applied.
                    For VALUE and REGEXP name of a field.
                    For FUNCTION name of a script function. The function is passed as
                    argument the cursor object.

        @param condition_value Value that makes the condition true
        """

        self.private_cursor._id_cond += 1
        self.private_cursor.id_ = "%s%s%s" % (
            self.private_cursor._id_ac,
            self.private_cursor._id_acos,
            self.private_cursor._id_cond,
        )
        self.private_cursor._acos_cond_name = condition_name
        self.private_cursor._acos_cond = condition
        self.private_cursor._acos_cond_value = condition_value

    @decorators.pyqtSlot()
    @decorators.NotImplementedWarn
    def concurrencyFields(self) -> List[str]:
        """
        Check if there is a collision of fields edited by two sessions simultaneously.

        @return List with the names of the colliding fields
        """

        return []

    @decorators.pyqtSlot()
    def changeConnection(self, conn_name: str) -> None:
        """
        Change the cursor to another database connection.

        @param conn_name. connection name.
        """

        cur_conn_name = self.connectionName()
        if cur_conn_name == conn_name:
            return

        new_database = application.PROJECT.conn_manager.database(conn_name)
        if cur_conn_name == new_database.connectionName():
            return

        if self.private_cursor._transactions_opened:
            metadata = self.private_cursor.metadata_
            table_name = None
            if metadata:
                table_name = metadata.name()
            else:
                table_name = self.curName()

            message = (
                "Se han detectado transacciones no finalizadas en la última operación.\n"
                "Se van a cancelar las transacciones pendientes.\n"
                "Los últimos datos introducidos no han sido guardados, por favor\n"
                "revise sus últimas acciones y repita las operaciones que no\n"
                "se han guardado.\n" + "SqlCursor::changeConnection: %s\n" % table_name
            )
            self.rollbackOpened(-1, message)

        buffer_backup = None
        if self.buffer():
            buffer_backup = self.buffer()
            self.private_cursor.buffer_ = None

        self.private_cursor.db_ = new_database
        self.init(self.private_cursor.cursor_name_, True, self.cursorRelation(), self.relation())

        if buffer_backup:
            self.private_cursor.buffer_ = buffer_backup

        self.connectionChanged.emit()

    @decorators.NotImplementedWarn
    def populateCursor(self) -> None:
        """
        If the cursor comes from a query, perform the process of adding the deficit from the fields to it.
        """
        return

    def setNotGenerateds(self) -> None:
        """
        Mark as no generated.

        When the cursor comes from a query, it performs the process that marks as
        not generated (the fields of the buffer are not taken into account in INSERT, EDIT, DEL)
        that do not belong to the main table.
        """

        if (
            self.private_cursor.metadata_
            and self.private_cursor._is_query
            and self.private_cursor.buffer_
        ):
            for field in self.private_cursor.metadata_.fieldList():
                self.private_cursor.buffer_.setGenerated(field, False)

    @decorators.NotImplementedWarn
    def setExtraFieldAttributes(self):
        """Deprecated."""

        return True

    # def clearMapCalcFields(self):
    #    self.private_cursor.mapCalcFields_ = []

    # @decorators.NotImplementedWarn
    # def valueBufferRaw(self, field_name: str) -> Any:
    #    """Deprecated."""

    #    return True

    def sort(self) -> str:
        """
        Choose the order of the main columns.

        @return sort order.
        """

        return self.private_cursor._model.getSortOrder()

    # @decorators.NotImplementedWarn
    # def list(self):
    #    return None

    def filter(self) -> str:
        """
        Return the cursor filter.

        @return current filter.
        """

        return (
            self.private_cursor._model.where_filters["filter"]
            if "filter" in self.private_cursor._model.where_filters
            else ""
        )

    def field(self, name: str) -> Optional["pnbuffer.FieldStruct"]:
        """
        Return a specified FieldStruct of the buffer.
        """

        if not self.private_cursor.buffer_:
            raise Exception("self.private_cursor.buffer_ is not defined!")
        return self.private_cursor.buffer_.field(name)

    def update(self, notify: bool = True) -> bool:
        """
        Update tableModel with the buffer.

        @param notify. emit bufferCommited signal after update if True else None.
        """

        LOGGER.trace("PNSqlCursor.update --- BEGIN:")
        update_successful = False
        if self.modeAccess() == PNSqlCursor.Edit:

            if not self.private_cursor.buffer_:
                raise Exception("Buffer is not set. Cannot update")
            # solo los campos modified
            lista = self.private_cursor.buffer_.modifiedFields()
            self.private_cursor.buffer_.setNoModifiedFields()
            # TODO: pKVaue debe ser el valueBufferCopy, es decir, el antiguo. Para
            # .. soportar updates de PKey, que, aunque inapropiados deberían funcionar.
            pk_name = self.private_cursor.buffer_.pK()
            if pk_name is None:
                raise Exception("PrimaryKey is not defined!")

            primary_key_value = self.private_cursor.buffer_.value(pk_name)

            dict_update = {
                fieldName: self.private_cursor.buffer_.value(fieldName) for fieldName in lista
            }
            try:
                update_successful = self.private_cursor._model.update(
                    primary_key_value, dict_update
                )
            except Exception:
                LOGGER.exception("PNSqlCursor.update:: Unhandled error on model updateRowDB:: ")
                update_successful = False
            # TODO: En el futuro, si no se puede conseguir un update, hay que
            # "tirar atrás" todo.
            if update_successful:
                row = self.private_cursor._model.findPKRow([primary_key_value])
                if row is not None:
                    if (
                        self.private_cursor._model.value(row, self.private_cursor._model.pK())
                        != primary_key_value
                    ):
                        raise AssertionError(
                            "Los indices del CursorTableModel devolvieron un registro erroneo: %r != %r"
                            % (
                                self.private_cursor._model.value(
                                    row, self.private_cursor._model.pK()
                                ),
                                primary_key_value,
                            )
                        )
                    self.private_cursor._model.setValuesDict(row, dict_update)

            else:
                # Método clásico
                LOGGER.warning(
                    "update :: WARN :: Los indices del CursorTableModel no funcionan o el PKey no existe."
                )
                row = 0
                while row < self.private_cursor._model.rowCount():
                    if (
                        self.private_cursor._model.value(row, self.private_cursor._model.pK())
                        == primary_key_value
                    ):
                        for field_name in lista:
                            self.private_cursor._model.setValue(
                                row, field_name, self.private_cursor.buffer_.value(field_name)
                            )

                        break

                    row = row + 1

            if notify:
                self.bufferCommited.emit()

        LOGGER.trace("PNSqlCursor.update --- END")
        return update_successful

    def lastError(self) -> str:
        """
        Return the last error reported by the database connection.

        @return last error reported.
        """

        return self.db().lastError()

    def __iter__(self) -> "PNSqlCursor":
        """
        Make the cursor iterable.
        """

        self._iter_current = None
        return self

    def __next__(self) -> str:
        """
        Make the cursor iterable.

        @return function name.
        """
        self._iter_current = 0 if self._iter_current is None else self._iter_current + 1

        list_ = [attr for attr in dir(self) if not attr[0] == "_"]
        if self._iter_current >= len(list_):
            raise StopIteration

        return list_[self._iter_current]

    def primaryKey(self) -> Optional[str]:
        """
        Return the primary cursor key.

        @return primary key field name.
        """

        if self.private_cursor.metadata_:
            return self.private_cursor.metadata_.primaryKey()
        else:
            return None

    def fieldType(self, field_name: str = None) -> Optional[int]:
        """
        Return the field type.

        @param field_name. Specify the field to return type.
        @return int identifier.
        """

        if field_name and self.private_cursor.metadata_:
            return self.private_cursor.metadata_.fieldType(field_name)
        else:
            return None

    """
    private slots:
    """

    """ Uso interno """
    # clearPersistentFilter = QtCore.pyqtSignal()

    # destroyed = QtCore.pyqtSignal()

    @decorators.pyqtSlot()
    def clearPersistentFilter(self):
        """
        Clear persistent filters.
        """

        self.private_cursor._persistent_filter = None


class PNCursorPrivate(isqlcursor.ICursorPrivate):
    """PNCursorPrivate class."""

    def __init__(
        self, cursor_: "PNSqlCursor", action_: "pnaction.PNAction", db_: "iconnection.IConnection"
    ) -> None:
        """
        Initialize the private part of the cursor.
        """

        super().__init__(cursor_, action_, db_)
        self.metadata_ = None
        self._count_ref_cursor = 0
        self._currentregister = -1
        self._acos_cond_name = None
        self.buffer_ = None
        self.edition_states_ = pnboolflagstate.PNBoolFlagStateList()
        self.browse_states_ = pnboolflagstate.PNBoolFlagStateList()
        self._activated_check_integrity = True
        self._activated_commit_actions = True
        self._ask_for_cancel_changes = True
        self._in_risks_locks = False
        self.populated_ = False
        self._transactions_opened = []
        self._id_ac = 0
        self._id_acos = 0
        self._id_cond = 0
        self.id_ = "000"
        self._acl_done = False
        self.edition_ = True
        self.browse_ = True
        self.cursor_ = cursor_
        self.cursor_relation_ = None
        self.relation_ = None
        # self.acl_table_ = None
        self.timer_ = None
        self.ctxt_ = None
        # self.rawValues_ = False
        self._persistent_filter = None
        self.db_ = db_
        self.cursor_name_ = action_.name()
        self._id_acl = ""
        # self.nameCursor = "%s_%s" % (
        #    act_.name(),
        #    QtCore.QDateTime.currentDateTime().toString("dd.MM.yyyyThh:mm:ss.zzz"),
        # )

    def __del__(self) -> None:
        """
        Delete instance values.
        """

        if self.metadata_:
            self.undoAcl()

            if self._id_acl in self.acl_table_.keys():
                del self.acl_table_[self._id_acl]
                # self.acl_table_ = None

        if self._buffer_copy:
            del self._buffer_copy
            self._buffer_copy = None

        if self.relation_:
            del self.relation_
            self.relation_ = None

        if self.edition_states_:
            del self.edition_states_
            self.edition_states_ = pnboolflagstate.PNBoolFlagStateList()
            # LOGGER.trace("AQBoolFlagState count %s", self.count_)

        if self.browse_states_:
            del self.browse_states_
            self.browse_states_ = pnboolflagstate.PNBoolFlagStateList()
            # LOGGER.trace("AQBoolFlagState count %s", self.count_)
        if self._transactions_opened:
            del self._transactions_opened
            self._transactions_opened = []

    def doAcl(self) -> None:
        """
        Create restrictions according to access control list.
        """
        from pineboolib.application.acls import pnaccesscontrolfactory

        if self.metadata_ is None:
            return

        if not self._id_acl:
            self._id_acl = "%s_%s" % (application.PROJECT.session_id(), self.metadata_.name())
        if self._id_acl not in self.acl_table_.keys():
            self.acl_table_[self._id_acl] = pnaccesscontrolfactory.PNAccessControlFactory().create(
                "table"
            )
            self.acl_table_[self._id_acl].setFromObject(self.metadata_)
            self._acos_backup_table[self._id_acl] = self.acl_table_[self._id_acl].getAcos()
            self._acos_permanent_backup_table[self._id_acl] = self.acl_table_[self._id_acl].perm()
            self.acl_table_[self._id_acl].clear()
        if self.cursor_ is None:
            raise Exception("Cursor not created yet")
        if self.mode_access_ == PNSqlCursor.Insert or (
            not self._last_at == -1 and self._last_at == self.cursor_.at()
        ):
            return

        if self._acos_cond_name is not None:
            condition_true = False

            if self._acos_cond == self.cursor_.Value:

                condition_true = (
                    self.cursor_.valueBuffer(self._acos_cond_name) == self._acos_cond_value
                )
            elif self._acos_cond == self.cursor_.RegExp:
                condition_true = QtCore.QRegExp(str(self._acos_cond_value)).exactMatch(
                    self.cursor_.valueBuffer(self._acos_cond_name)
                )
            elif self._acos_cond == self.cursor_.Function:
                condition_true = (
                    application.PROJECT.call(self._acos_cond_name, [self.cursor_])
                    == self._acos_cond_value
                )

            if condition_true:
                if self.acl_table_[self._id_acl].name() != self.id_:
                    self.acl_table_[self._id_acl].clear()
                    self.acl_table_[self._id_acl].setName(self.id_)
                    self.acl_table_[self._id_acl].setPerm(self._ac_perm_table)
                    self.acl_table_[self._id_acl].setAcos(self._acos_table)
                    self.acl_table_[self._id_acl].processObject(self.metadata_)
                    self._acl_done = True

                return

        elif self.cursor_.isLocked() or (
            self.cursor_relation_ and self.cursor_relation_.isLocked()
        ):

            if not self.acl_table_[self._id_acl].name() == self.id_:
                self.acl_table_[self._id_acl].clear()
                self.acl_table_[self._id_acl].setName(self.id_)
                self.acl_table_[self._id_acl].setPerm("r-")
                self.acl_table_[self._id_acl].processObject(self.metadata_)
                self._acl_done = True

            return

        self.undoAcl()

    def undoAcl(self) -> None:
        """
        Delete restrictions according to access control list.
        """
        if self.metadata_ is None or not self._id_acl:
            return

        if self._id_acl in self.acl_table_.keys():
            self._acl_done = False
            self.acl_table_[self._id_acl].clear()
            self.acl_table_[self._id_acl].setPerm(self._acos_permanent_backup_table[self._id_acl])
            self.acl_table_[self._id_acl].setAcos(self._acos_backup_table[self._id_acl])
            self.acl_table_[self._id_acl].processObject(self.metadata_)

    def needUpdate(self) -> bool:
        """
        Indicate if the cursor needs to be updated.

        @return True or False.
        """

        if self._is_query:
            return False

        need = self._model.need_update
        return need

    def msgBoxWarning(self, msg: str, throwException: bool = False) -> None:
        """
        Error message associated with the DGI.

        @param msg.Error message.
        @param throwException. No used.
        """

        application.PROJECT.message_manager().send("msgBoxWarning", None, [msg])
