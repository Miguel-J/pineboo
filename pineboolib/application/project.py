import os
import logging
from typing import List, Optional, Union

from pineboolib.exceptions import CodeDoesNotBelongHereException
from pineboolib.utils_base import filedir, Struct, cacheXPM, _dir

from .structs import DBServer, DBAuth

# from pineboolib.mtdparser.pnmtdparser import mtd_parse
# from pineboolib.fllegacy.flaccesscontrollists import FLAccessControlLists # FIXME: Not allowed yet
# from PyQt5 import QtCore  # FIXME: Not allowed yet
# from pineboolib.fllegacy.flsettings import FLSettings # FIXME: Not allowed yet
# from pineboolib.plugins.dgi.dgi_qt.dgi_qt import dgi_qt


class Project(object):
    """
    Esta es la clase principal del proyecto. Se puede acceder a esta con pineboolib.project desde cualquier parte del projecto
    """

    logger = logging.getLogger("main.Project")
    conn = None  # Almacena la conexión principal a la base de datos
    debugLevel = 100

    # _initModules = None
    main_window = None
    acl_ = None
    _DGI = None
    deleteCache = None
    path = None
    kugarPluging = None
    _splash = None
    sql_drivers_manager = None
    timer_ = None
    no_python_cache = False  # TODO: Fill this one instead
    """
    Constructor
    """

    def __init__(self, DGI: dgi_qt) -> None:
        self._DGI = DGI
        self.tree = None
        self.root = None
        self.dbserver = None
        self.dbauth = None
        self.dbname = None
        self.apppath = None
        self.tmpdir = None
        self.parser = None
        self.version = 0.8
        self.main_form_name = "eneboo"
        if self._DGI.mobilePlatform():
            self.main_form_name = "mobile"
        else:
            if FLSettings().readBoolEntry("ebcomportamiento/mdi_mode"):
                self.main_form_name = "eneboo_mdi"

        # pineboolib.project = self  # FIXME: not good.
        self.deleteCache = False
        self.parseProject = False
        self.translator_ = []
        self.actions = {}
        self.tables = {}
        self.files = {}
        self.apppath = filedir("..")
        self.tmpdir = FLSettings().readEntry("ebcomportamiento/kugar_temp_dir", filedir("../tempdata"))
        if not os.path.exists(self.tmpdir):
            os.mkdir(self.tmpdir)
        from pineboolib.plugins.kugar.pnkugarplugins import PNKugarPlugins

        self.kugarPlugin = PNKugarPlugins()

        if not self._DGI.localDesktop():
            self._DGI.extraProjectInit()

    """
    Especifica el nivel de debug de la aplicación
    @param q Número con el nimvel espeficicado
    """

    def setDebugLevel(self, q: int) -> None:
        Project.debugLevel = q
        # self._DGI.pnqt3ui.Options.DEBUG_LEVEL = q

    # def acl(self) -> Optional[FLAccessControlLists]:
    #     """
    #     Retorna si hay o no acls cargados
    #     @return Objeto acl_
    #     """
    #     return self.acl_
    def acl(self):
        raise CodeDoesNotBelongHereException("ACL Does not belong to PROJECT. Go away.")

    """
    Especifica los datos para luego conectarse a la BD.
    @param dbname. Nombre de la BD.
    @param host. Nombre del equipo anfitrión de la BD.
    @param port. Puerto a usar para conectarse a la BD.
    @param passwd. Contraseña de la BD.
    @param driveralias. Alias del pluging a usar en la conexión
    """

    def load_db(self, dbname, host, port, user, passwd, driveralias):
        self.dbserver = DBServer()
        self.dbserver.host = host
        self.dbserver.port = port
        self.dbserver.type = driveralias
        self.dbauth = DBAuth()
        self.dbauth.username = user
        self.dbauth.password = passwd
        self.dbname = dbname

        self.actions = {}
        self.tables = {}

    def load(self, file_name: str) -> bool:
        from xml.etree import ElementTree as ET
        import hashlib

        tree = ET.parse(file_name)
        root = tree.getroot()

        version = root.get("Version")
        if version is None:
            version = 1.0
        else:
            version = float(version)  # FIXME: Esto es muy mala idea. Tratar versiones como float causará problemas al comparar.

        for profile in root.findall("profile-data"):
            invalid_password = False
            if version == 1.0:
                if getattr(profile.find("password"), "text", None) is not None:
                    invalid_password = True
            else:
                profile_pwd = getattr(profile.find("password"), "text", None)
                user_pwd = hashlib.sha256("".encode()).hexdigest()
                if profile_pwd != user_pwd:
                    invalid_password = True

            if invalid_password:
                self.logger.warning("No se puede cargar un profile con contraseña por consola")
                return False

        self.dbname = root.find("database-name").text
        for db in root.findall("database-server"):
            self.dbserver = DBServer()
            self.dbserver.host = db.find("host").text
            self.dbserver.port = db.find("port").text
            self.dbserver.type = db.find("type").text
            if self.dbserver.type not in self.sql_drivers_manager.aliasList():
                self.logger.warning("Esta versión de pineboo no soporta el driver '%s'" % self.dbserver.type)
                self.database = None
                return False

        for credentials in root.findall("database-credentials"):
            self.dbauth = DBAuth()
            self.dbauth.username = credentials.find("username").text
            ps = credentials.find("password").text
            if ps:
                import base64

                self.dbauth.password = base64.b64decode(ps).decode()
            else:
                self.dbauth.password = ""

        return True

    def run(self) -> bool:
        """Arranca el proyecto. Conecta a la BD y carga los datos
        """

        if not self.conn:
            from pineboolib.pnconnection import PNConnection

            self.conn = PNConnection(
                self.dbname, self.dbserver.host, self.dbserver.port, self.dbauth.username, self.dbauth.password, self.dbserver.type
            )

        if self.conn.conn is False:
            return False

        from pineboolib.pnobjectsfactory import load_models
        from pineboolib.pncontrolsfactory import aqApp

        # TODO: Refactorizar esta función en otras más sencillas
        # Preparar temporal

        if self.deleteCache and os.path.exists(_dir("cache/%s" % self.conn.DBName())):
            if self._splash:
                self._splash.showMessage("Borrando caché ...", QtCore.Qt.AlignLeft, QtCore.Qt.white)
            self.logger.debug("DEVELOP: DeleteCache Activado\nBorrando %s", _dir("cache/%s" % self.conn.DBName()))
            for root, dirs, files in os.walk(_dir("cache/%s" % self.conn.DBName()), topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))

        if not os.path.exists(_dir("cache")):
            os.makedirs(_dir("cache"))

        if not os.path.exists(_dir("cache/%s" % self.conn.DBName())):
            os.makedirs(_dir("cache/%s" % self.conn.DBName()))

        if not self.deleteCache:
            keep_images = FLSettings().readBoolEntry("ebcomportamiento/keep_general_cache", False)
            if keep_images is False:
                for f in os.listdir(self.tmpdir):
                    if f.find(".") > -1:
                        pt_ = os.path.join(self.tmpdir, f)
                        os.remove(pt_)

        # Conectar:

        # Se verifica que existen estas tablas
        for table in ("flareas", "flmodules", "flfiles", "flgroups", "fllarge", "flserial", "flusers", "flvar", "flmetadata"):
            self.conn.manager().createSystemTable(table)

        util = FLUtil()
        util.writeSettingEntry(u"DBA/lastDB", self.conn.DBName())
        cursor_ = self.conn.cursor()
        self.areas = {}
        cursor_.execute(""" SELECT idarea, descripcion FROM flareas WHERE 1 = 1""")
        for idarea, descripcion in cursor_:
            self.areas[idarea] = Struct(idarea=idarea, descripcion=descripcion)

        self.areas["sys"] = Struct(idarea="sys", descripcion="Area de Sistema")

        # Obtener módulos activos
        cursor_.execute(
            """ SELECT idarea, idmodulo, descripcion, icono FROM flmodules WHERE bloqueo = %s """
            % self.conn.driver().formatValue("bool", "True", False)
        )
        self.modules = {}
        for idarea, idmodulo, descripcion, icono in cursor_:
            icono = cacheXPM(icono)
            self.modules[idmodulo] = Module(idarea, idmodulo, descripcion, icono)

        file_object = open(filedir("..", "share", "pineboo", "sys.xpm"), "r")
        icono = file_object.read()
        file_object.close()
        # icono = clearXPM(icono)

        self.modules["sys"] = Module("sys", "sys", "Administración", icono)

        cursor_.execute(""" SELECT idmodulo, nombre, sha FROM flfiles WHERE NOT sha = '' ORDER BY idmodulo, nombre """)

        size_ = cursor_.rowcount

        f1 = open(_dir("project.txt"), "w")
        self.files = {}
        if self._DGI.useDesktop() and self._DGI.localDesktop():
            tiempo_ini = time.time()
        if not os.path.exists(_dir("cache")):
            raise AssertionError
        p = 0
        pos_qs = 1
        for idmodulo, nombre, sha in cursor_:
            if not self._DGI.accept_file(nombre):
                continue

            p = p + 1
            if idmodulo not in self.modules:
                continue  # I
            fileobj = File(idmodulo, nombre, sha)
            if nombre in self.files:
                self.logger.warning("run: file %s already loaded, overwritting..." % nombre)
            self.files[nombre] = fileobj
            self.modules[idmodulo].add_project_file(fileobj)
            f1.write(fileobj.filekey + "\n")

            fileobjdir = os.path.dirname(_dir("cache", fileobj.filekey))
            file_name = _dir("cache", fileobj.filekey)
            if not os.path.exists(fileobjdir):
                os.makedirs(fileobjdir)

            if os.path.exists(file_name):
                if file_name.endswith(".qs"):
                    if os.path.exists("%s.py" % file_name):
                        continue

                elif file_name.endswith(".mtd"):
                    if os.path.exists("%s_model.py" % _dir("cache", fileobj.filekey[:-4])):
                        continue
                else:
                    continue

            cur2 = self.conn.cursor()
            sql = "SELECT contenido FROM flfiles WHERE idmodulo = %s AND nombre = %s AND sha = %s" % (
                self.conn.driver().formatValue("string", idmodulo, False),
                self.conn.driver().formatValue("string", nombre, False),
                self.conn.driver().formatValue("string", sha, False),
            )
            cur2.execute(sql)
            # qs_count = 0
            for (contenido,) in cur2:

                encode_ = "ISO-8859-15"
                if str(nombre).endswith(".kut") or str(nombre).endswith(".ts"):
                    encode_ = "utf-8"

                settings = FLSettings()

                folder = _dir("cache", "/".join(fileobj.filekey.split("/")[: len(fileobj.filekey.split("/")) - 1]))
                if os.path.exists(folder) and not file_name:  # Borra la carpeta si no existe el fichero destino
                    for root, dirs, files in os.walk(folder):
                        for f in files:
                            os.remove(os.path.join(root, f))

                if settings.readBoolEntry("application/isDebuggerMode", False):
                    if self._splash:
                        self._splash.showMessage("Volcando a caché %s..." % nombre, QtCore.Qt.AlignLeft, QtCore.Qt.white)

                if contenido and not os.path.exists(file_name):
                    f2 = open(file_name, "wb")
                    txt = contenido.encode(encode_, "replace")
                    f2.write(txt)
                    f2.close()

            if nombre.endswith(".mtd"):
                mtd_parse(fileobj)

            if self.parseProject and nombre.endswith(".qs") and settings.readBoolEntry("application/isDebuggerMode", False):
                # if self._splash:
                #    self._splash.showMessage("Convirtiendo %s ( %d/ ??) ..." %
                #                             (nombre, pos_qs), QtCore.Qt.AlignLeft, QtCore.Qt.white)
                if os.path.exists(file_name):

                    self.parseScript(file_name, "(%d de %d)" % (p, size_))

                pos_qs += 1

        if self._DGI.useDesktop() and self._DGI.localDesktop():
            tiempo_fin = time.time()
            self.logger.info("Descarga del proyecto completo a disco duro: %.3fs", (tiempo_fin - tiempo_ini))

        # Cargar el núcleo común del proyecto
        idmodulo = "sys"
        for root, dirs, files in os.walk(filedir("..", "share", "pineboo")):
            for nombre in files:
                if root.find("modulos") == -1:
                    fileobj = File(idmodulo, nombre, basedir=root)
                    self.files[nombre] = fileobj
                    self.modules[idmodulo].add_project_file(fileobj)
                    if self.parseProject and nombre.endswith(".qs"):
                        self.parseScript(_dir(root, nombre))

        if self._splash:
            self._splash.showMessage("Cargando objetos ...", QtCore.Qt.AlignLeft, QtCore.Qt.white)
            self._DGI.processEvents()

        load_models()

        if self._splash:
            self._splash.showMessage("Cargando traducciones ...", QtCore.Qt.AlignLeft, QtCore.Qt.white)
            self._DGI.processEvents()

        aqApp.loadTranslations()

        self.acl_ = FLAccessControlLists()
        self.acl_.init()

        return True

    """
    LLama a una función del projecto.
    @param function. Nombre de la función a llamar.
    @param aList. Array con los argumentos.
    @param objectContext. Contexto en el que se ejecuta la función.
    @param showException. Boolean que especifica si se muestra los errores.
    @return Boolean con el resultado.
    """

    def call(
        self, function: str, aList: List[Union[List[str], str, bool]], object_context: None = None, showException: bool = True
    ) -> Optional[bool]:
        # FIXME: No deberíamos usar este método. En Python hay formas mejores
        # de hacer esto.
        self.logger.trace("JS.CALL: fn:%s args:%s ctx:%s", function, aList, object_context, stack_info=True)

        if function is not None:
            # Tipicamente flfactalma.iface.beforeCommit_articulos()
            if function[-2:] == "()":
                function = function[:-2]

            aFunction = function.split(".")
        else:
            aFunction = []

        if not object_context:
            if not aFunction[0] in self.actions:
                if len(aFunction) > 1:
                    if showException:
                        self.logger.error("No existe la acción %s en el módulo %s", aFunction[1], aFunction[0])
                else:
                    if showException:
                        self.logger.error("No existe la acción %s", aFunction[0])
                return False

            funAction = self.actions[aFunction[0]]
            if aFunction[1] == "iface" or len(aFunction) == 2:
                mW = funAction.load()
                if len(aFunction) == 2:
                    object_context = None
                    if hasattr(mW.widget, aFunction[1]):
                        object_context = mW.widget
                    if hasattr(mW.iface, aFunction[1]):
                        object_context = mW.iface

                    if not object_context:
                        object_context = mW

                else:
                    object_context = mW.iface

            elif aFunction[1] == "widget":
                fR = None
                funAction.load_script(aFunction[0], fR)
                object_context = fR.iface
            else:
                return False

            if not object_context:
                if showException:
                    self.logger.error("No existe el script para la acción %s en el módulo %s", aFunction[0], aFunction[0])
                return False

        fn = None
        if len(aFunction) == 1:  # Si no hay puntos en la llamada a functión
            function_name = aFunction[0]

        elif len(aFunction) > 2:  # si existe self.iface por ejemplo
            function_name = aFunction[2]
        elif len(aFunction) == 2:
            function_name = aFunction[1]  # si no exite self.iiface
        else:
            if len(aFunction) == 0:
                fn = object_context

        if not fn:
            fn = getattr(object_context, function_name, None)

        if fn is None:
            if showException:
                self.logger.error("No existe la función %s en %s", function_name, aFunction[0])
            return True  # FIXME: Esto devuelve true? debería ser false, pero igual se usa por el motor para detectar propiedades

        try:
            return fn(*aList)
        except Exception:
            self.logger.exception("JSCALL: Error executing function %s", stack_info=True)

        return None

    """
    Convierte un script .qs a .py lo deja al lado
    @param scriptname, Nombre del script a convertir
    """

    def parseScript(self, scriptname: str, txt_: str = "") -> None:

        # Intentar convertirlo a Python primero con flscriptparser2
        if not os.path.isfile(scriptname):
            raise IOError
        python_script_path = (scriptname + ".xml.py").replace(".qs.xml.py", ".qs.py")
        if not os.path.isfile(python_script_path) or self.no_python_cache:
            settings = FLSettings()
            debug_postparse = False
            if settings.readBoolEntry("application/isDebuggerMode", False):
                util = FLUtil()
                file_name = scriptname.split("\\") if util.getOS() == "WIN32" else scriptname.split("/")

                file_name = file_name[len(file_name) - 2]

                msg = "Convirtiendo a Python . . . %s.qs %s" % (file_name, txt_)
                if settings.readBoolEntry("ebcomportamiento/SLConsola", False):
                    debug_postparse = True
                    self.logger.warning(msg)

                if self._splash:
                    self._splash.showMessage(msg, QtCore.Qt.AlignLeft, QtCore.Qt.white)

                else:
                    if settings.readBoolEntry("ebcomportamiento/SLInterface", False):
                        from pineboolib.pncontrolsfactory import aqApp

                        aqApp.popupWarn(msg)

            clean_no_python = self._DGI.clean_no_python()

            from pineboolib.flparser import postparse

            try:
                postparse.pythonify(scriptname, debug_postparse, clean_no_python)
            except Exception as e:
                self.logger.warning("El fichero %s no se ha podido convertir: %s", scriptname, e)

    """
    Lanza los test
    @param name, Nombre del test específico. Si no se especifica se lanzan todos los tests disponibles
    @return Texto con la valoración de los test aplicados
    """

    def test(self, name=None):
        from importlib import import_module

        dirlist = os.listdir(filedir("../pineboolib/plugins/test"))
        testDict = {}
        for f in dirlist:
            if not f[0:2] == "__":
                f = f[: f.find(".py")]
                mod_ = import_module("pineboolib.plugins.test.%s" % f)
                test_ = getattr(mod_, f)
                testDict[f] = test_

        maxValue = 0
        value = 0
        result = None
        resultValue = 0
        if name:
            try:
                t = testDict[name]()
                maxValue = t.maxValue()
                value = t.run()
            except Exception:
                result = False
        else:

            for test in testDict.keys():
                print("test", test)
                t = testDict[test]()
                maxValue = maxValue + t.maxValue
                v = t.run()
                print("result", test, v, "/", t.maxValue)
                value = value + v

        if result is None and maxValue > 0:
            resultValue = value

        result = "%s/%s" % (resultValue, maxValue)

        return result

    """
    Retorna la carpeta temporal predefinida de pineboo
    @return ruta a la carpeta temporal
    """

    def get_temp_dir(self) -> str:
        return self.tmpdir
