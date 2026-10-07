"""Start SismoLab AVL: opens the Tkinter window.

Run `python main.py` from this folder (or double click iniciar.bat on Windows).
Only the Python standard library is needed: nothing to install.
"""

import sys


def check_python():
    # The project needs Python 3.8 or newer
    if sys.version_info < (3, 8):
        print("SismoLab necesita Python 3.8 o superior. Versión actual:", sys.version.split()[0])
        sys.exit(1)


def check_tkinter():
    # Tkinter comes with the python.org installer; some Linux systems need an extra package
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Falta Tkinter en esta instalación de Python.")
        print("Windows/macOS: reinstale Python desde python.org marcando 'tcl/tk and IDLE'.")
        print("Linux (Ubuntu/Debian): sudo apt install python3-tk")
        sys.exit(1)


def main():
    check_python()
    check_tkinter()
    from src.gui.app import start
    start()


if __name__ == "__main__":
    main()
