"""
Unit Test Package for QSA parser.
"""
import os.path


def fixture_path(*path: str) -> str:
    """
    Get fixture path for this test folder.
    """
    basedir = os.path.realpath(os.path.dirname(__file__))
    filepath = os.path.join(basedir, "fixtures", *path)
    return filepath


def fixture_read(*path: str) -> str:
    """
    Read fixture from this test folder.
    """
    with open(fixture_path(*path), "r", encoding="utf-8") as file:
        contents = file.read()
    return contents
