"""Connection Module."""
import getpass
from optparse import Values
from typing import Optional

from pineboolib.application.database.pnconnection import PNConnection
from .projectconfig import ProjectConfig, PasswordMismatchError


DEFAULT_SQLITE_CONN = ProjectConfig(database="pineboo.sqlite3", type="SQLite3 (SQLITE3)")
IN_MEMORY_SQLITE_CONN = ProjectConfig(
    database=":memory:", type="SQLite3 (SQLITE3)", username="memory_user"
)


def config_dbconn(options: Values) -> Optional[ProjectConfig]:
    """Obtain a config connection from a file."""

    if options.project:  # FIXME: --project debería ser capaz de sobreescribir algunas opciones
        if not options.project.endswith(".xml"):
            options.project += ".xml"
        prj_name = options.project
        try:
            return ProjectConfig(load_xml=prj_name)
        except PasswordMismatchError:
            # If fails without password, ignore the exception so the stack is cleaned.
            # This avoids seeing two exceptions if password is wrong.
            pass
        password = getpass.getpass()
        return ProjectConfig(load_xml=prj_name, project_password=password)

    if options.connection:
        return ProjectConfig(connstring=options.connection)

    return None


def connect_to_db(config: ProjectConfig) -> "PNConnection":
    """Try connect a database with projectConfig data."""
    if config.database is None:
        raise ValueError("database not set")
    if config.type is None:
        raise ValueError("type not set")
    port = int(config.port) if config.port else None
    connection = PNConnection(
        config.database, config.host, port, config.username, config.password or "", config.type
    )
    return connection
