"""
Project Module.
"""
import os
from optparse import Values
from pathlib import Path


from typing import List, Optional, Any, Dict, Callable, TYPE_CHECKING


# from pineboolib.fllegacy.flaccesscontrollists import FLAccessControlLists # FIXME: Not allowed yet
from PyQt5 import QtWidgets

from pineboolib.core.utils import logging, utils_base
from pineboolib.core.utils.struct import AreaStruct
from pineboolib.core import exceptions, settings, message_manager
from pineboolib.application.database import pnconnectionmanager
from pineboolib.application.utils import path, xpm
from pineboolib.application import module, file


if TYPE_CHECKING:
    from pineboolib.interfaces.dgi_schema import dgi_schema
    from pineboolib.application.database import pnconnection
    from pineboolib.core.utils.struct import ActionStruct  # noqa: F401

LOGGER = logging.getLogger(__name__)


class Project(object):
    """
    Singleton for the whole application.

    Can be accessed with pineboolib.project from anywhere.
    """

    _conn_manager: "pnconnectionmanager.PNConnectionManager"

    _app: Optional[QtWidgets.QApplication] = None
    # _conn: Optional["PNConnection"] = None  # Almacena la conexión principal a la base de datos
    debug_level = 100
    options: Values

    # _initModules = None
    main_form: Any = None  # FIXME: How is this used? Which type?
    main_window: Any = None
    acl_ = None
    dgi: Optional["dgi_schema"] = None
    delete_cache: bool = False
    parse_project: bool = False
    path = None
    _splash = None
    sql_drivers_manager = None
    timer_ = None
    no_python_cache = False  # TODO: Fill this one instead
    _msg_mng = None
    alternative_folder: Optional[str]
    _session_func_: Optional[Callable]

    areas: Dict[str, AreaStruct]
    files: Dict[Any, Any]
    tables: Dict[Any, Any]
    actions: Dict[Any, "ActionStruct"]
    translator_: List[Any]
    modules: Dict[str, "module.Module"]
    pending_conversion_list: List[str]

    def __init__(self) -> None:
        """Constructor."""
        # self._conn = None
        self.dgi = None
        self.tree = None
        self.root = None
        self.alternative_folder = None
        self.apppath = ""
        self.tmpdir = settings.config.value("ebcomportamiento/temp_dir")
        self.parser = None
        # self.main_form_name: Optional[str] = None
        self.delete_cache = False
        self.parse_project = False
        self.translator_ = []  # FIXME: Add proper type
        self.actions = {}  # FIXME: Add proper type
        self.tables = {}  # FIXME: Add proper type
        self.files = {}  # FIXME: Add proper type
        self.areas = {}
        self.modules = {}
        self.options = Values()
        if self.tmpdir is None:
            self.tmpdir = utils_base.filedir("%s/Pineboo/tempdata" % Path.home())
            settings.config.set_value("ebcomportamiento/temp_dir", self.tmpdir)

        if not os.path.exists(self.tmpdir):
            Path(self.tmpdir).mkdir(parents=True, exist_ok=True)

        self._session_func_ = None
        self._conn_manager = pnconnectionmanager.PNConnectionManager()
        self.pending_conversion_list = []

    @property
    def app(self) -> QtWidgets.QApplication:
        """Retrieve current Qt Application or throw error."""
        if self._app is None:
            raise Exception("No application set")
        return self._app

    def set_app(self, app: QtWidgets.QApplication):
        """Set Qt Application."""
        self._app = app

    @property
    def conn_manager(self) -> "pnconnectionmanager.PNConnectionManager":
        """Retrieve current connection or throw."""
        if self._conn_manager is None:
            raise Exception("Project is not initialized")
        return self._conn_manager

    @property
    def DGI(self) -> "dgi_schema":
        """Retrieve current DGI or throw."""
        if self.dgi is None:
            raise Exception("Project is not initialized")
        return self.dgi

    def init_conn(self, connection: "pnconnection.PNConnection") -> None:
        """Initialize project with a connection."""
        # if self._conn is not None:
        #    del self._conn
        #    self._conn = None

        self._conn_manager.setMainConn(connection)
        self.apppath = utils_base.filedir("..")

        self.delete_cache = settings.config.value("ebcomportamiento/deleteCache", False)
        self.parse_project = settings.config.value("ebcomportamiento/parseProject", False)

    def init_dgi(self, dgi: "dgi_schema") -> None:
        """Load and associate the defined DGI onto this project."""
        # FIXME: Actually, DGI should be loaded here, or kind of.

        self.dgi = dgi

        self._msg_mng = message_manager.Manager(dgi)

        self.dgi.extraProjectInit()

    def load_modules(self) -> None:
        """Load all modules."""
        for module_name, mod_obj in self.modules.items():
            mod_obj.load()
            self.tables.update(mod_obj.tables)

    def setDebugLevel(self, level: int) -> None:
        """
        Set debug level for application.

        @param q Número con el nivel espeficicado
        ***DEPRECATED***
        """
        self.debug_level = level
        # self.dgi.pnqt3ui.Options.DEBUG_LEVEL = q

    # def acl(self) -> Optional[FLAccessControlLists]:
    #     """
    #     Retorna si hay o no acls cargados
    #     @return Objeto acl_
    #     """
    #     return self.acl_
    def acl(self):
        """Return loaded ACL."""
        raise exceptions.CodeDoesNotBelongHereException("ACL Does not belong to PROJECT. Go away.")

    def run(self) -> bool:
        """Run project. Connects to DB and loads data."""

        self.pending_conversion_list = []

        if self.actions:
            del self.actions

        if self.tables:
            del self.tables

        self.actions = {}
        self.tables = {}

        if self.dgi is None:
            raise Exception("DGI not loaded")

        if not self.conn_manager or "main_conn" not in self.conn_manager.connections_dict.keys():
            raise exceptions.NotConnectedError(
                "Cannot execute Pineboo Project without a connection in place"
            )

        conn = self.conn_manager.mainConn()
        db_name = conn.DBName()
        # TODO: Refactorizar esta función en otras más sencillas
        # Preparar temporal

        if self.delete_cache and os.path.exists(path._dir("cache/%s" % db_name)):

            self.message_manager().send("splash", "showMessage", ["Borrando caché ..."])
            LOGGER.debug(
                "DEVELOP: delete_cache Activado\nBorrando %s", path._dir("cache/%s" % db_name)
            )
            for root, dirs, files in os.walk(path._dir("cache/%s" % db_name), topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))

        else:
            keep_images = settings.config.value("ebcomportamiento/keep_general_cache", False)
            if keep_images is False:
                for file_name in os.listdir(self.tmpdir):
                    if file_name.find(".") > -1 and not file_name.endswith("sqlite3"):
                        file_path = os.path.join(self.tmpdir, file_name)
                        try:
                            os.remove(file_path)
                        except Exception:
                            LOGGER.warning(
                                "No se ha podido borrar %s al limpiar la cache", file_path
                            )
                            pass

        if not os.path.exists(path._dir("cache")):
            os.makedirs(path._dir("cache"))

        if not os.path.exists(path._dir("cache/%s" % db_name)):
            os.makedirs(path._dir("cache/%s" % db_name))

        # Conectar:

        # Se verifica que existen estas tablas
        for table in (
            "flareas",
            "flmodules",
            "flfiles",
            "flgroups",
            "fllarge",
            "flserial",
            "flusers",
            "flvar",
            "flmetadata",
            "flsettings",
            "flupdates",
            "flmetadata",
            "flseqs",
            "flsettings",
        ):
            if not self.conn_manager.manager().existsTable(table):
                self.conn_manager.manager().createSystemTable(table)

        cursor_ = self.conn_manager.dbAux().cursor()
        self.areas = {}
        cursor_.execute(""" SELECT idarea, descripcion FROM flareas WHERE 1 = 1""")
        for idarea, descripcion in list(cursor_):
            self.areas[idarea] = AreaStruct(idarea=idarea, descripcion=descripcion)

        self.areas["sys"] = AreaStruct(idarea="sys", descripcion="Area de Sistema")

        # Obtener módulos activos
        cursor_.execute(
            """ SELECT idarea, idmodulo, descripcion, icono FROM flmodules WHERE bloqueo = %s """
            % conn.driver().formatValue("bool", "True", False)
        )

        self.modules = {}

        for idarea, idmodulo, descripcion, icono in cursor_:
            icono = xpm.cache_xpm(icono)
            self.modules[idmodulo] = module.Module(idarea, idmodulo, descripcion, icono)

        file_object = open(
            utils_base.filedir(utils_base.get_base_dir(), "system_module", "sys.xpm"), "r"
        )
        icono = file_object.read()
        file_object.close()
        # icono = clearXPM(icono)

        self.modules["sys"] = module.Module("sys", "sys", "Administración", icono)

        cursor_.execute(
            """ SELECT idmodulo, nombre, sha FROM flfiles WHERE NOT sha = '' ORDER BY idmodulo, nombre """
        )

        file_1 = open(path._dir("project.txt"), "w")
        self.files = {}

        count = 0

        list_files: List[str] = []

        for idmodulo, nombre, sha in list(cursor_):
            if not self.dgi.accept_file(nombre):
                continue

            count += 1
            if idmodulo not in self.modules:
                continue  # I
            fileobj = file.File(idmodulo, nombre, sha, db_name=db_name)
            if nombre in self.files:
                LOGGER.warning("run: file %s already loaded, overwritting..." % nombre)
            self.files[nombre] = fileobj
            self.modules[idmodulo].add_project_file(fileobj)
            file_1.write(fileobj.filekey + "\n")

            fileobjdir = os.path.dirname(path._dir("cache", fileobj.filekey))
            file_name = path._dir("cache", fileobj.filekey)
            if not os.path.exists(fileobjdir):
                os.makedirs(fileobjdir)

            if os.path.exists(file_name):
                if file_name.endswith(".qs"):
                    folder_path = os.path.dirname(file_name)
                    static_flag = "%s/STATIC" % folder_path
                    file_name_py = "%s.py" % file_name[:-3]
                    if os.path.exists(static_flag):
                        os.remove(static_flag)
                        if os.path.exists(file_name):
                            os.remove(file_name)
                        if os.path.exists(file_name_py):
                            os.remove(file_name_py)

                    elif os.path.exists(file_name_py):
                        continue

                elif file_name.endswith(".mtd"):
                    if settings.config.value(
                        "ebcomportamiento/orm_enabled", False
                    ) and not settings.config.value("ebcomportamiento/orm_parser_disabled", False):
                        if os.path.exists("%s_model.py" % path._dir("cache", fileobj.filekey[:-4])):
                            continue
                else:
                    continue

            cur2 = self.conn_manager.useConn("dbAux").cursor()
            sql = (
                "SELECT contenido FROM flfiles WHERE idmodulo = %s AND nombre = %s AND sha = %s"
                % (
                    conn.driver().formatValue("string", idmodulo, False),
                    conn.driver().formatValue("string", nombre, False),
                    conn.driver().formatValue("string", sha, False),
                )
            )
            cur2.execute(sql)
            for (contenido,) in list(cur2):

                encode_ = "utf-8" if str(nombre).endswith((".kut", ".ts", ".py")) else "ISO-8859-15"

                folder = path._dir(
                    "cache",
                    "/".join(fileobj.filekey.split("/")[: len(fileobj.filekey.split("/")) - 1]),
                )
                if os.path.exists(folder) and not os.path.exists(
                    file_name
                ):  # Borra la carpeta si no existe el fichero destino
                    for root, dirs, files in os.walk(folder):
                        for file_item in files:
                            os.remove(os.path.join(root, file_item))

                if contenido and not os.path.exists(file_name):
                    self.message_manager().send(
                        "splash", "showMessage", ["Volcando a caché %s..." % nombre]
                    )
                    file_2 = open(file_name, "wb")
                    txt = contenido.encode(encode_, "replace")
                    file_2.write(txt)
                    file_2.close()

            if self.parse_project and nombre.endswith(".qs"):
                if os.path.exists(file_name):
                    list_files.append(file_name)

        file_1.close()
        self.message_manager().send("splash", "showMessage", ["Convirtiendo a Python ..."])

        if list_files:
            self.parse_script_list(list_files)

        # Cargar el núcleo común del proyecto

        for root, dirs, files in os.walk(
            utils_base.filedir(utils_base.get_base_dir(), "system_module")
        ):
            # list_files = []
            for nombre in files:
                if root.find("modulos") == -1:
                    fileobj = file.File("sys", nombre, basedir=root, db_name=db_name)
                    self.files[nombre] = fileobj
                    self.modules["sys"].add_project_file(fileobj)

                    # if self.parse_project and nombre.endswith(".qs"):
                    # self.parseScript(path._dir(root, nombre))
                    #    list_files.append(path._dir(root, nombre))

            # self.parse_script_lists(list_files)

        if settings.config.value(
            "ebcomportamiento/orm_enabled", False
        ) and not settings.config.value("ebcomportamiento/orm_load_disabled", False):
            self.message_manager().send("splash", "showMessage", ["Cargando objetos ..."])
            from pineboolib.application.parsers.mtdparser import pnormmodelsfactory

            pnormmodelsfactory.load_models()

        # FIXME: ACLs needed at this level?
        # self.acl_ = FLAccessControlLists()
        # self.acl_.init()

        return True

    def call(
        self,
        function: str,
        args: List[Any],
        object_context: Any = None,
        show_exceptions: bool = True,
    ) -> Optional[Any]:
        """
        Call to a QS project function.

        @param function. Nombre de la función a llamar.
        @param args. Array con los argumentos.
        @param object_context. Contexto en el que se ejecuta la función.
        @param show_exceptions. Boolean que especifica si se muestra los errores.
        @return Boolean con el resultado.
        """
        # FIXME: No deberíamos usar este método. En Python hay formas mejores
        # de hacer esto.
        LOGGER.trace(
            "JS.CALL: fn:%s args:%s ctx:%s", function, args, object_context, stack_info=True
        )

        # Tipicamente flfactalma.iface.beforeCommit_articulos()
        if function[-2:] == "()":
            function = function[:-2]

        array_fun = function.split(".")

        if not object_context:
            if not array_fun[0] in self.actions:
                if len(array_fun) > 1:
                    if show_exceptions:
                        LOGGER.error(
                            "No existe la acción %s en el módulo %s", array_fun[1], array_fun[0]
                        )
                else:
                    if show_exceptions:
                        LOGGER.error("No existe la acción %s", array_fun[0])
                return None

            fun_action = self.actions[array_fun[0]]
            if array_fun[1] == "iface" or len(array_fun) == 2:
                mW = fun_action.load()
                if len(array_fun) == 2:
                    object_context = None
                    if hasattr(mW.widget, array_fun[1]):
                        object_context = mW.widget
                    if hasattr(mW.iface, array_fun[1]):
                        object_context = mW.iface

                    if not object_context:
                        object_context = mW

                else:
                    object_context = mW.iface

            elif array_fun[1] == "widget":
                script = fun_action.load_script(array_fun[0], None)
                object_context = script.iface
            else:
                return False

            if not object_context:
                if show_exceptions:
                    LOGGER.error(
                        "No existe el script para la acción %s en el módulo %s",
                        array_fun[0],
                        array_fun[0],
                    )
                return None

        function_name_object = None
        if len(array_fun) == 1:  # Si no hay puntos en la llamada a functión
            function_name = array_fun[0]

        elif len(array_fun) > 2:  # si existe self.iface por ejemplo
            function_name = array_fun[2]
        elif len(array_fun) == 2:
            function_name = array_fun[1]  # si no exite self.iiface
        else:
            if len(array_fun) == 0:
                function_name_object = object_context

        if not function_name_object:
            function_name_object = getattr(object_context, function_name, None)

        if function_name_object is None:
            if show_exceptions:
                LOGGER.error("No existe la función %s en %s", function_name, array_fun[0])
            return True
            # FIXME: debería ser false, pero igual se usa por el motor para detectar propiedades

        try:
            return function_name_object(*args)
        except Exception:
            LOGGER.exception("JSCALL: Error executing function %s", stack_info=True)

        return None

    def parse_script(self, scriptname: str, txt_: str = "") -> None:
        """
        Convert QS script into Python and stores it in the same folder.

        @param scriptname, Nombre del script a convertir
        """
        from pineboolib.application.parsers.qsaparser import postparse

        # Intentar convertirlo a Python primero con flscriptparser2
        if not os.path.isfile(scriptname):
            raise IOError
        python_script_path = (scriptname + ".xml.py").replace(".qs.xml.py", ".qs.py")
        if not os.path.isfile(python_script_path) or self.no_python_cache:
            file_name_l = scriptname.split(os.sep)  # FIXME: is a bad idea to split by os.sep
            file_name = file_name_l[len(file_name_l) - 2]

            msg = "Convirtiendo a Python . . . %s.qs %s" % (file_name, txt_)
            LOGGER.info(msg)

            # clean_no_python = self.dgi.clean_no_python() # FIXME: No longer needed. Applied on the go.

            try:
                postparse.pythonify([scriptname], ["--strict"])
            except Exception:
                LOGGER.exception("El fichero %s no se ha podido convertir", scriptname)

    def parse_script_list(self, path_list: List[str]) -> None:
        """Convert QS scripts list into Python and stores it in the same folders."""

        from multiprocessing import Pool
        from pineboolib.application.parsers import qsaparser
        from pineboolib.application.parsers.qsaparser import pytnyzer, pyconvert

        if not path_list:
            return

        for file_path in path_list:
            if not os.path.isfile(file_path):
                raise IOError

        pytnyzer.STRICT_MODE = True

        itemlist = []
        for num, path_file in enumerate(path_list):
            dest_file_name = "%s.py" % path_file[:-3]
            if dest_file_name in self.pending_conversion_list:
                LOGGER.warning("The file %s is already being converted. Waiting", dest_file_name)
                while dest_file_name in self.pending_conversion_list:
                    # Esperamos a que el fichero se convierta.
                    QtWidgets.QApplication.processEvents()
            else:
                self.pending_conversion_list.append(dest_file_name)
                itemlist.append(
                    pyconvert.PythonifyItem(
                        src=path_file, dst=dest_file_name, n=num, len=len(path_list), known={}
                    )
                )

        # itemlist = [
        #    pyconvert.PythonifyItem(
        #        src=path_file, dst="%s.py" % path_file[:-3], n=n, len=len(path_list), known={}
        #    )
        #    for n, path_file in enumerate(path_list)
        # ]
        msg = "Convirtiendo a Python . . ."
        LOGGER.info(msg)

        threads_num = pyconvert.CPU_COUNT
        if len(itemlist) < threads_num:
            threads_num = len(itemlist)

        pycode_list: List[bool] = []

        if qsaparser.USE_THREADS:
            with Pool(threads_num) as thread:
                # TODO: Add proper signatures to Python files to avoid reparsing
                pycode_list = thread.map(pyconvert.pythonify_item, itemlist, chunksize=2)
        else:
            for item in itemlist:
                pycode_list.append(pyconvert.pythonify_item(item))

        for item in itemlist:
            self.pending_conversion_list.remove(item.dst_path)

        if not all(pycode_list):
            LOGGER.warning("Conversion failed for some files")

    def get_temp_dir(self) -> str:
        """
        Return temporary folder defined for pineboo.

        @return ruta a la carpeta temporal
        ***DEPRECATED***
        """
        # FIXME: anti-pattern in Python. Getters for plain variables are wrong.
        raise exceptions.CodeDoesNotBelongHereException("Use project.tmpdir instead, please.")
        # return self.tmpdir

    def load_version(self) -> str:
        """Initialize current version numbers."""
        self.version = "0.68.19"
        if settings.config.value("application/dbadmin_enabled", False):
            self.version = "DBAdmin v%s" % self.version
        else:
            self.version = "Quick v%s" % self.version

        return self.version

    def message_manager(self):
        """Return message manager for splash and progress."""
        return self._msg_mng

    def set_session_function(self, fun_: Callable) -> None:
        """Set session funcion."""

        self._session_func_ = fun_

    def session_id(self) -> str:
        """Return id if use pineboo like framework."""

        return str(self._session_func_()) if self._session_func_ is not None else ""
