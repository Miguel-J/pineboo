import gc
import sys
import traceback
import logging

from pineboolib.core.utils import is_deployed
from pineboolib.core.settings import config, settings
from .dgi import load_dgi

from PyQt5 import QtCore

from optparse import Values

logger = logging.getLogger(__name__)


def startup():
    # FIXME: No hemos cargado pineboo aún. No se pueden usar métodos internos.
    # from pineboolib.application.utils.check_dependencies import check_dependencies
    # check_dependencies({"ply": "python3-ply", "PyQt5.QtCore": "python3-pyqt5", "Python": "Python"})

    MIN_PYTHON = (3, 6)
    if sys.version_info < MIN_PYTHON:
        sys.exit("Python %s.%s or later is required.\n" % MIN_PYTHON)

    from .options import parse_options

    options = parse_options()
    if options.enable_profiler:
        ret = exec_main_with_profiler(options)
    else:
        ret = exec_main(options)
    # setup()
    # exec_()
    gc.collect()
    print("Closing Pineboo...")
    if ret:
        sys.exit(ret)
    else:
        sys.exit(0)


def exec_main_with_profiler(options):
    import cProfile
    import pstats
    import io
    from pstats import SortKey

    pr = cProfile.Profile()
    pr.enable()
    ret = exec_main(options)
    pr.disable()
    s = io.StringIO()
    sortby = SortKey.TIME
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats(40)
    print(s.getvalue())
    return ret


def excepthook(type, value, tback):
    return traceback.print_exception(type, value, tback)


def setup_gui(app: QtCore.QCoreApplication, options: Values):
    from pineboolib.core.utils.utils_base import filedir
    from pineboolib.application.utils.mobilemode import is_mobile_mode
    from PyQt5 import QtGui

    noto_fonts = ["NotoSans-BoldItalic.ttf", "NotoSans-Bold.ttf", "NotoSans-Italic.ttf", "NotoSans-Regular.ttf"]
    for fontfile in noto_fonts:
        QtGui.QFontDatabase.addApplicationFont(filedir("../share/fonts/Noto_Sans", fontfile))

    from pineboolib.fllegacy.flsettings import FLSettings

    sett_ = FLSettings()

    styleA = sett_.readEntry("application/style", None)
    if styleA is None:
        styleA = "Fusion"

    app.setStyle(styleA)

    fontA = sett_.readEntry("application/font", None)
    if fontA is None:
        if is_mobile_mode():
            font = QtGui.QFont("Noto Sans", 14)
        else:
            font = QtGui.QFont("Noto Sans", 9)
        font.setBold(False)
        font.setItalic(False)
    else:
        # FIXME: FLSettings.readEntry does not return an array
        font = QtGui.QFont(fontA[0], int(fontA[1]), int(fontA[2]), fontA[3] == "true")

    app.setFont(font)


def exec_main(options: Values) -> None:
    """Exec main program.

    Handles optionlist and help.
    Also initializes all the objects
    """
    # PyQt 5.5 o superior aborta la ejecución si una excepción en un slot()
    # no es capturada dentro de la misma; el programa falla con SegFault.
    # Aunque esto no debería ocurrir, y se debería prevenir lo máximo posible
    # es bastante incómodo y genera problemas graves para detectar el problema.
    # Agregamos sys.excepthook para controlar esto y hacer que PyQt5 no nos
    # dé un segfault, aunque el resultado no sea siempre correcto:
    sys.excepthook = excepthook
    # -------------------

    # Corregir Control-C:
    import signal

    signal.signal(signal.SIGINT, signal.SIG_DFL)
    # -------------------

    # import pineboolib.pnapplication
    # from pineboolib.core.utils.utils_base import filedir
    # from pineboolib.pnsqldrivers import PNSqlDrivers

    # FIXME: This function should not initialize the program

    # TODO: Refactorizar función en otras más pequeñas
    import pineboolib

    project = pineboolib.project  # FIXME: next time, proper singleton
    project.load_version()
    project.setDebugLevel(options.debug_level)

    project.options = options
    if options.enable_gui:
        from PyQt5 import QtWidgets

        project.app = QtWidgets.QApplication(sys.argv)
        project.app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        setup_gui(project.app, options)
    else:
        project.app = QtCore.QCoreApplication(sys.argv)

    if options.trace_debug:
        from pineboolib.core.utils.utils_base import traceit

        sys.settrace(traceit)
    if options.trace_signals:
        from .utils import monkey_patch_connect

        monkey_patch_connect()

    if options.enable_dbadmin:
        config.set_value("application/dbadmin_enabled", True)

    if options.enable_quick:
        config.set_value("application/dbadmin_enabled", False)

    if is_deployed():
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)
        from pineboolib.core.utils.utils_base import download_files

        download_files()

    _DGI = load_dgi(options.dgi, options.dgi_parameter)

    if _DGI.useDesktop() and not options.enable_gui:
        raise Exception("Selected DGI <%s> is not compatible with <pineboo-core>. Use <pineboo> instead" % options.dgi)

    if not _DGI.useDesktop() and options.enable_gui:
        logger.info("Selected DGI <%s> does not need graphical interface. Use <pineboo-core> for better results" % options.dgi)

    if not _DGI.useMLDefault():
        # When a particular DGI doesn't want the standard init, we stop loading here
        # and let it take control of the remaining pieces.
        _DGI.alternativeMain(options)
        return

    from .connection import config_dbconn, connect_to_db, DEFAULT_SQLITE_CONN

    configdb = config_dbconn(options)

    project.init_dgi(_DGI)

    if not configdb and _DGI.useDesktop() and _DGI.localDesktop():
        if not _DGI.mobilePlatform():
            from .conn_dialog import show_connection_dialog

            configdb = show_connection_dialog(project.app)
        else:
            configdb = DEFAULT_SQLITE_CONN

    if not configdb:
        raise ValueError("No connection given. Nowhere to connect. Cannot start.")

    conn = connect_to_db(configdb)
    project.init_conn(connection=conn)

    settings.set_value("DBA/lastDB", conn.DBName())

    project.no_python_cache = options.no_python_cache

    if options.test:
        project.test()
        return

    if _DGI.useDesktop():
        # FIXME: What is happening here? Why dynamic load?
        import importlib  # FIXME: Delete dynamic import and move this code between Project and DGI plugins

        project.main_form = (
            importlib.import_module("pineboolib.plugins.mainform.%s.%s" % (project.main_form_name, project.main_form_name))
            if _DGI.localDesktop()
            else _DGI.mainForm()
        )
        project.main_window = project.main_form.mainWindow
        project.main_form.MainForm.setDebugLevel(options.debug_level)

    # Cargando spashscreen
    # Create and display the splash screen
    # if _DGI.localDesktop() and not options.action:
    #     splash = show_splashscreen(project)
    #     _DGI.processEvents()
    # else:
    #     splash = None
    splash = None

    project._splash = splash
    project.run()
    if project.conn.conn is False:
        logger.warning("No connection was provided. Aborting Pineboo load.")
    else:
        from .init_project import init_project

        init_project(_DGI, splash, options, project, project.main_form if _DGI.useDesktop() else None, project.app)