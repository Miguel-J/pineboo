import logging
from .projectconfig import ProjectConfig

logger = logging.getLogger("loader.conn_dialog")


def show_connection_dialog():
    """Show the connection dialog, and configure the project accordingly."""
    from .dlgconnect import DlgConnect

    connection_window = DlgConnect()
    connection_window.load()
    connection_window.show()
    ret = app.exec_()  # FIXME: App should be started before this function
    if connection_window.close():
        project_config = None
        if getattr(connection_window, "database", None):
            project_config = ProjectConfig(
                connection_window.database,
                connection_window.hostname,
                connection_window.portnumber,
                connection_window.driveralias,
                connection_window.username,
                connection_window.password)
                
            
        return project_config
