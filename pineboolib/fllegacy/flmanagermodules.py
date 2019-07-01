# -*- coding: utf-8 -*-
import os
import logging

import pineboolib
from pineboolib.core import decorators
from pineboolib.core.utils.utils_base import filedir
from pineboolib.application.utils.xpm import cacheXPM
from pineboolib.application.utils.convert_flaction import convert2FLAction
from pineboolib.fllegacy.flsqlquery import FLSqlQuery
from pineboolib.fllegacy.flaction import FLAction
from pineboolib.fllegacy.flsettings import FLSettings
from pineboolib.fllegacy.flmodulesstaticloader import FLStaticLoader, AQStaticBdInfo

"""
Gestor de módulos.

Esta clase permite realizar las funciones básicas de manejo de ficheros
de texto que forman parte de los módulos de aplicación, utilizando como
soporte de almacenamiento la base de datos y el sistema de cachés de texto
para optimizar las lecturas.
Gestiona la carga y descarga de módulos. Mantiene cual es el módulo activo.
El módulo activo se puede establecer en cualquier momento con
FLManagerModules::setActiveIdModule().

Los módulos se engloban en áreas (FACTURACION, FINANCIERA, PRODUCCION, etc..) y
cada módulo tiene varios ficheros de texto XML y scripts. Toda la estructura de
módulos se almacena en las tablas flareas, flmodulos, flserial y flfiles, sirviendo esta
clase como interfaz para el manejo de dicha estructura en el entorno de trabajo
de AbanQ.

@author InfoSiAL S.L.
"""

logger = logging.getLogger(__name__)


class FLInfoMod(object):
    idModulo = None
    idArea = None
    descripcion = None
    version = None
    icono = None
    areaDescripcion = None


class FLManagerModules(object):

    """
    Mantiene el identificador del area a la que pertenece el módulo activo.
    """

    activeIdArea_ = None

    """
    Mantiene el identificador del módulo activo.
    """
    activeIdModule_ = None

    """
    Mantiene la clave sha correspondiente a la version de los módulos cargados localmente
    """
    shaLocal_ = None

    """
    Diccionario de claves de ficheros, para optimizar lecturas
    """
    dictKeyFiles = {}

    """
    Lista de todos los identificadores de módulos cargados, para optimizar lecturas
    """
    listAllIdModules_ = []

    """
    Lista de todas los identificadores de areas cargadas, para optimizar lecturas
    """
    listIdAreas_ = []

    """
    Diccionario con información de los módulos
    """
    dictInfoMods = {}

    """
    Diccionario de identificadores de modulo de ficheros, para optimizar lecturas
    """
    dictModFiles = {}

    """
    Base de datos a utilizar por el manejador
    """
    conn_ = None

    """
    Uso interno.
    Informacion para la carga estatica desde el disco local
    """
    staticBdInfo_ = None

    root_dir_ = None
    scripts_dir_ = None
    tables_dir_ = None
    forms_dir_ = None
    reports_dir_ = None
    queries_dir_ = None
    trans_dir_ = None
    filesCached_ = {}
    """
    constructor
    """

    def __init__(self, db=None):
        super(FLManagerModules, self).__init__()
        if db:
            self.conn_ = db

            self.staticBdInfo_ = AQStaticBdInfo(self.conn_)

        self.filesCached_ = {}

    # """
    # Acciones de inicialización del sistema de módulos.
    # """
    # @decorators.NotImplementedWarn
    # def init(self):
    #    pass

    """
     Acciones de finalización del sistema de módulos.
    """

    def finish(self):
        if self.listAllIdModules_:
            del self.listAllIdModules_
            self.listAllIdModules_ = []

        if self.listIdAreas_:
            del self.listIdAreas_
            self.listIdAreas_ = []

        if self.dictInfoMods:
            del self.dictInfoMods
            self.dictInfoMods = {}

        if self.dictModFiles:
            del self.dictModFiles
            self.dictModFiles = {}

        if self.staticBdInfo_:
            del self.staticBdInfo_
            self.staticBdInfo_ = None

        if self.dictKeyFiles:
            self.writeState()
            del self.dictKeyFiles
            self.dictKeyFiles = {}

        del self

    """
    Obtiene el contenido de un fichero almacenado la base de datos.

    Este método busca el contenido del fichero solicitado en la
    base de datos, exactamente en la tabla flfiles, si no lo encuentra
    intenta obtenerlo del sistema de ficheros.

    @param n Nombre del fichero.
    @return QString con el contenido del fichero o vacía en caso de error.
    """

    def content(self, n):
        cursor = self.conn_.execute_query("SELECT contenido FROM flfiles WHERE nombre='%s' AND NOT sha = ''" % n)

        for contenido in cursor:
            return contenido[0]

        return None

    """
    Obtiene el contenido de un fichero de script, procesándolo para cambiar las conexiones que contenga,
    de forma que al acabar la ejecución de la función conectada se reanude el guión de pruebas.
    Tambien realiza procesos de formateo del código para optimizarlo.

    @param n Nombre del fichero.
    @return QString con el contenido del fichero o vacía en caso de error.
    """

    @decorators.NotImplementedWarn
    def byteCodeToStr(self, n):
        return None

    @decorators.NotImplementedWarn
    def contentCode(self, n):
        return None

    """
    Obtiene el contenido de un fichero almacenado en el sistema de ficheros.

    @param pN Ruta y nombre del fichero en el sistema de ficheros
    @return QString con el contenido del fichero o vacía en caso de error.
    """

    def contentFS(self, pN, utf8=False):
        encode_ = "UTF-8" if utf8 else "ISO-8859-15"

        try:
            return str(open(pN, "rb").read(), encode_)
        except Exception:
            return None

    """
    Obtiene el contenido de un fichero, utilizando la caché de memoria y disco.

    Este método primero busca el contenido del fichero solicitado en la
    caché interna, si no está lo obtiene con el método FLManagerModules::content().

    @param n Nombre del fichero.
    @return QString con el contenido del fichero o vacía en caso de error.
    """

    def contentCached(self, n, shaKey=None):

        not_sys_table = n[0:3] != "sys" and not self.conn_.manager().isSystemTable(n)
        if not_sys_table and self.staticBdInfo_ and self.staticBdInfo_.enabled_:
            str_ret = self.contentStatic(n)
            if str_ret:
                return str_ret

        if n in self.filesCached_.keys():
            return self.filesCached_[n]

        data = None
        modId = None
        name_ = n[: n.index(".")]
        ext_ = n[n.index(".") + 1 :]
        type_ = None
        if ext_ == "kut":
            type_ = "reports/"
        elif ext_ == "qs":
            type_ = "scritps/"
        elif ext_ == "mtd":
            type_ = "tables/"
        elif ext_ == "ui":
            type_ = "forms/"
        elif ext_ == "qry":
            type_ = "queries/"
        elif ext_ == "ts":
            type_ = "translations/"
        elif ext_ == "xml":
            type_ = ""

        if not shaKey and not self.conn_.manager().isSystemTable(name_):

            cursor = self.conn_.execute_query("SELECT sha FROM flfiles WHERE nombre='%s'" % n)

            for contenido in cursor:
                shaKey = contenido[0]

        if self.conn_.manager().isSystemTable(name_):
            modId = "sys"
        else:
            modId = self.conn_.managerModules().idModuleOfFile(n)

        from pineboolib import project

        if project._DGI.alternative_content_cached():
            data = project._DGI.content_cached(project.tmpdir, self.conn_.DBName(), modId, ext_, name_, shaKey)
            if data is not None:
                return data

        if data is None:
            """Ruta por defecto"""
            if os.path.exists("%s/cache/%s/%s/file.%s/%s" % (project.tmpdir, self.conn_.DBName(), modId, ext_, name_)):
                utf8_ = True if ext_ == "kut" else False
                data = self.contentFS(
                    "%s/cache/%s/%s/file.%s/%s/%s.%s" % (project.tmpdir, self.conn_.DBName(), modId, ext_, name_, shaKey, ext_), utf8_
                )

        if data is None:
            if os.path.exists(filedir("../share/pineboo/%s%s.%s" % (type_, name_, ext_))):
                data = self.contentFS(filedir("../share/pineboo/%s%s.%s" % (type_, name_, ext_)))
            else:
                data = self.content(n)

        if data:
            self.filesCached_[n] = data
        return data

    """
    Almacena el contenido de un fichero en un módulo dado.

    @param n Nombre del fichero.
    @param idM Identificador del módulo al que se asociará el fichero
    @param content Contenido del fichero.
    """

    @decorators.NotImplementedWarn
    def setContent(self, n, idM, content):
        pass

    """
    Crea un formulario a partir de su fichero de descripción.

    Utiliza el método FLManagerModules::contentCached() para obtener el texto XML que describe
    el formulario.

    @param n Nombre del fichero que contiene la descricpción del formulario.
    @return QWidget correspondiente al formulario construido.
    """

    def createUI(self, n, connector=None, parent=None, name=None):
        return pineboolib.project._DGI.createUI(n, connector, parent, name)

    """
    Crea el formulario maestro de una acción a partir de su fichero de descripción.

    Utiliza el método FLManagerModules::createUI() para obtener el formulario construido.

    @param a Objeto FLAction.
    @return QWidget correspondiente al formulario construido.
    """

    def createForm(self, a, connector=None, parent=None, name=None):
        from pineboolib import pncontrolsfactory

        if not isinstance(a, FLAction):
            a = convert2FLAction(a)

        return None if not a else pncontrolsfactory.FLFormDB(parent, a, load=True)

    """
    Esta función es igual a la anterior, sólo se diferencia en que carga
    la descripción de interfaz del formulario de edición de registros.
    @param a. Action
    @param connector. Conector usado
    @param parent_or_cursor. Cursor o parent del form
    @param name. Nombre del formRecord
    """

    def createFormRecord(self, a, connector=None, parent_or_cursor=None, name=None):
        logger.trace("createFormRecord: init")
        from pineboolib import pncontrolsfactory

        # Falta implementar conector y name
        if not isinstance(a, FLAction):
            logger.trace("createFormRecord: convert2FLAction")
            a = convert2FLAction(a)

        if not a:
            return None

        logger.trace("createFormRecord: load FormRecordDB")
        return pncontrolsfactory.FLFormRecordDB(parent_or_cursor, a, load=False)

    """
    Para establecer el módulo activo.

    Automáticamente también establece cual es el área correspondiente al módulo,
    ya que un módulo sólo puede pertenecer a una sola área.

    @param id Identificador del módulo
    """

    def setActiveIdModule(self, _id=None):
        if _id is None or not self.dictInfoMods:
            self.activeIdArea_ = None
            self.activeIdModule_ = None
            return

        if _id.upper() in self.dictInfoMods.keys():
            im = self.dictInfoMods[_id.upper()]
            self.activeIdArea_ = im.idArea
            self.activeIdModule_ = _id

    """
    Para obtener el area del módulo activo.

    @return Identificador del area
    """

    def activeIdArea(self):
        return self.activeIdArea_

    """
    Para obtener el módulo activo.

    @return Identificador del módulo
    """

    def activeIdModule(self):
        return self.activeIdModule_

    """
    Obtiene la lista de identificadores de area cargadas en el sistema.

    @return Lista de identificadores de areas
    """

    def listIdAreas(self):
        return self.listIdAreas_

    """
    Obtiene la lista de identificadores de módulos cargados en el sistema de una area dada.

    @param idA Identificador del área de la que se quiere obtener la lista módulos
    @return Lista de identificadores de módulos
    """

    def listIdModules(self, idA):
        list_ = []
        for mod in self.dictInfoMods.keys():
            if self.dictInfoMods[mod].idArea == idA:
                list_.append(self.dictInfoMods[mod].idModulo)

        return list_

    """
    Obtiene la lista de identificadores de todos los módulos cargados en el sistema.

    @return Lista de identificadores de módulos
    """

    def listAllIdModules(self):
        return self.listAllIdModules_

    """
    Obtiene la descripción de un área a partir de su identificador.

    @param idA Identificador del área.
    @return Texto de descripción del área, si lo encuentra o idA si no lo encuentra.
    """

    def idAreaToDescription(self, idA=None):

        if idA:
            for area in self.dictInfoMods.keys():
                if self.dictInfoMods[area].idArea.upper() == idA.upper():
                    return self.dictInfoMods[area].areaDescripcion
        else:
            idA = ""

        return idA

    """
    Obtiene la descripción de un módulo a partir de su identificador.

    @param idM Identificador del módulo.
    @return Texto de descripción del módulo, si lo encuentra o idM si no lo encuentra.
    """

    def idModuleToDescription(self, idM):
        if idM.upper() in self.dictInfoMods.keys():
            return self.dictInfoMods[idM.upper()].descripcion

        return idM

    """
    Para obtener el icono asociado a un módulo.

    @param idM Identificador del módulo del que obtener el icono
    @return QPixmap con el icono
    """

    def iconModule(self, idM):
        from pineboolib import pncontrolsfactory

        pix = None
        if idM.upper() in self.dictInfoMods.keys():
            icono = cacheXPM(self.dictInfoMods[idM.upper()].icono)
            pix = pncontrolsfactory.QPixmap(icono)

        return pix or pncontrolsfactory.QPixmap()

    """
    Para obtener la versión de un módulo.

    @param idM Identificador del módulo del que se quiere saber su versión
    @return Cadena con la versión
    """

    def versionModule(self, idM):
        if not self.dictInfoMods:
            return idM

        im = idM.upper()

        return im.version if im else idM

    """
    Para obtener la clave sha local.

    @return Clave sha de la versión de los módulos cargados localmente
    """

    def shaLocal(self):
        return self.shaLocal_

    """
    Para obtener la clave sha global.

    @return Clave sha de la versión de los módulos cargados globalmente
    """

    def shaGlobal(self):
        q = FLSqlQuery(None, self.conn_.dbAux())
        q.setForwardOnly(True)
        q.exec_("SELECT sha FROM flserial")
        if q.lastError is None:
            return "error"

        if q.next():
            return str(q.value(0))
        else:
            return ""

    """
    Establece el valor de la clave sha local con el del global.
    """

    def setShaLocalFromGlobal(self):
        self.shaLocal_ = self.shaGlobal()

    """
    Obtiene la clave sha asociada a un fichero almacenado.

    @param n Nombre del fichero
    @return Clave sh asociada al ficheros
    """

    def shaOfFile(self, n):
        if not n[:3] == "sys" and not self.conn_.manager().isSystemTable(n):
            formatVal = self.conn_.manager().formatAssignValue("nombre", "string", n, True)
            q = FLSqlQuery(None, self.conn_.dbAux())
            # q.setForwardOnly(True)
            q.exec_("SELECT sha FROM flfiles WHERE %s" % formatVal)
            if q.next():
                return str(q.value(0))

        return None

    """
    Carga en el diccionario de claves las claves sha1 de los ficheros
    """

    def loadKeyFiles(self):

        self.dictKeyFiles = {}
        self.dictModFiles = {}
        q = FLSqlQuery(None, self.conn_.dbAux())
        # q.setForwardOnly(True)
        q.exec_("SELECT nombre, sha, idmodulo FROM flfiles")
        name = None
        while q.next():
            name = str(q.value(0))
            self.dictKeyFiles[name] = str(q.value(1))
            self.dictModFiles[name.upper()] = str(q.value(2))

    """
    Carga la lista de todos los identificadores de módulos
    """

    def loadAllIdModules(self):

        self.listAllIdModules_ = []
        self.listAllIdModules_.append("sys")
        self.dictInfoMods = {}

        q = FLSqlQuery(None, self.conn_.dbAux())
        q.setTablesList("flmodules,flareas")
        q.setSelect("idmodulo,flmodules.idarea,flmodules.descripcion,version,icono,flareas.descripcion")
        q.setFrom("flmodules left join flareas on flmodules.idarea = flareas.idarea")
        q.setWhere("1 = 1")
        q.setForwardOnly(True)
        q.exec_()
        # q.exec_("SELECT idmodulo,flmodules.idarea,flmodules.descripcion,version,icono,flareas.descripcion "
        #        "FROM flmodules left join flareas on flmodules.idarea = flareas.idarea")

        sysModuleFound = False
        while q.next():
            infoMod = FLInfoMod()
            infoMod.idModulo = str(q.value(0))
            infoMod.idArea = str(q.value(1))
            infoMod.descripcion = str(q.value(2))
            infoMod.version = str(q.value(3))
            infoMod.icono = str(q.value(4))
            infoMod.areaDescripcion = str(q.value(5))
            self.dictInfoMods[infoMod.idModulo.upper()] = infoMod

            if not infoMod.idModulo == "sys":
                self.listAllIdModules_.append(infoMod.idModulo)
            else:
                sysModuleFound = True

        if not sysModuleFound:
            infoMod = FLInfoMod()
            infoMod.idModulo = "sys"
            infoMod.idArea = "sys"
            infoMod.descripcion = "Administracion"
            infoMod.version = "0.0"
            infoMod.icono = self.contentFS("%s/%s" % (filedir("../share/pineboo"), "/sys.xpm"))
            infoMod.areaDescripcion = "Sistema"
            self.dictInfoMods[infoMod.idModulo.upper()] = infoMod

    """
    Carga la lista de todos los identificadores de areas
    """

    def loadIdAreas(self):

        self.listIdAreas_ = []
        q = FLSqlQuery(None, self.conn_.dbAux())
        # q.setForwardOnly(True)
        q.exec_("SELECT idarea from flareas WHERE idarea <> 'sys'")
        while q.next():
            self.listIdAreas_.append(str(q.value(0)))

        if "sys" not in self.listIdAreas_:
            self.listIdAreas_.append("sys")

    """
    Comprueba las firmas para un modulo dado
    """

    @decorators.NotImplementedWarn
    def checkSignatures(self):
        pass

    """
    Para obtener el identificador del módulo al que pertenece un fichero dado.

    @param n Nombre del fichero incluida la extensión
    @return Identificador del módulo al que pertenece el fichero
    """

    def idModuleOfFile(self, n):
        if not isinstance(n, str):
            n = n.toString()

        from pineboolib import project

        if n.endswith(".mtd"):
            if n[: n.find(".mtd")] in project._DGI.sys_mtds() or n == "flfiles.mtd":
                return "sys"

        cursor = self.conn_.execute_query("SELECT idmodulo FROM flfiles WHERE nombre='%s'" % n)

        for idmodulo in cursor:
            return idmodulo[0]

    """
    Guarda el estado del sistema de módulos
    """

    def writeState(self):
        idDB = "%s%s%s%s%s" % (self.conn_.database(), self.conn_.host(), self.conn_.user(), self.conn_.driverName(), self.conn_.port())

        settings = FLSettings()
        settings.writeEntry("Modules/activeIdModule/%s" % idDB, self.activeIdModule_)
        settings.writeEntry("Modules/activeIdArea/%s" % idDB, self.activeIdArea_)
        settings.writeEntry("Modules/shaLocal/%s" % idDB, self.shaLocal_)

    """
    Lee el estado del sistema de módulos
    """

    def readState(self):
        idDB = "%s%s%s%s%s" % (self.conn_.database(), self.conn_.host(), self.conn_.user(), self.conn_.driverName(), self.conn_.port())

        settings = FLSettings()
        self.activeIdModule_ = settings.readEntry("Modules/activeIdModule/%s" % idDB, None)
        self.activeIdArea_ = settings.readEntry("Modules/activeIdArea/%s" % idDB, None)
        self.shaLocal_ = settings.readEntry("Modules/shaLocal/%s" % idDB, None)

        if self.activeIdModule_ is None or self.activeIdModule_ not in self.listAllIdModules():
            self.setActiveIdModule(None)

    """
    Uso interno.
    Obtiene el contenido de un fichero mediante la carga estatica desde el disco local

    @param n Nombre del fichero.
    @return QString con el contenido del fichero o vacía en caso de error.
    """

    def contentStatic(self, n):

        str_ret = FLStaticLoader.content(n, self.staticBdInfo_)
        if str_ret:
            from pineboolib.fllegacy.FLUtil import FLUtil

            util = FLUtil()
            sha = util.sha1(str_ret)
            if n in self.dictKeyFiles.keys():
                s = self.dictKeyFiles[n]

            if self.dictKeyFiles and s == sha:
                return None
            elif self.dictKeyFiles and n.find(".qs") > -1:
                self.dictKeyFiles[n] = sha

                if n.endswith(".mtd"):
                    from PyQt5.QtXml import QDomDocument

                    doc = QDomDocument(n)
                    if util.domDocumentSetContent(doc, str_ret):
                        mng = self.conn_.manager()
                        docElem = doc.documentElement()
                        mtd = mng.metadata(docElem, True)

                        if not mtd or mtd.isQuery():
                            return str_ret

                        if not mng.existTable(mtd.name()):
                            mng.createTable(mng)
                        elif self.conn_.canRegenTables():
                            self.conn_.regenTable(mtd.name(), mtd)

        return str_ret

    """
    Uso interno.
    Muestra cuadro de dialogo para configurar la carga estatica desde el disco local
    """

    def staticLoaderSetup(self):
        FLStaticLoader.setup(self.staticBdInfo_)
