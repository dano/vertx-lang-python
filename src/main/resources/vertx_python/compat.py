from __future__ import unicode_literals, print_function, absolute_import

import sys
from py4j.compat import iteritems

if sys.version_info >= (3,3):
    import asyncio
elif sys.version_info >= (3,0):
    raise Exception("Must be running either Python 2.7.x or Python 3.3+ to use this module.")
else:
    import trollius as asyncio

if sys.version_info[0] < 3:
    long = long
    basestring = basestring
    unicode = unicode
else:
    long = int
    basestring = str
    unicode = str
