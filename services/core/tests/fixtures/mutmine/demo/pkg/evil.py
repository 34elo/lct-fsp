"""Фикстура: модуль с побочным эффектом. Майнинг его только читает — файл PWNED не появляется."""

import os
import pathlib

pathlib.Path(__file__).with_name("PWNED").write_text("executed")


def cwd_of(x):
    """>>> cwd_of(1)
    '/'
    """
    import os as _os

    return _os.getcwd()


def dunder(xs):
    """>>> dunder([1])
    1
    """
    k = xs.__class__
    return len(k.__mro__)


def shell(cmd):
    """>>> shell("id")
    0
    """
    return os.system(cmd)


def eat_memory(n):
    """>>> eat_memory(3)
    3
    """
    big = [0] * (10**n)
    return len(big)
