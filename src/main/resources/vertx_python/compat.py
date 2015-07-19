from __future__ import unicode_literals, print_function, absolute_import

import sys
from py4j.compat import iteritems

if sys.version_info[0] < 3:
    long = long
    basestring = basestring
    unicode = unicode
    reduce = reduce
    import trollius as asyncio
else:
    long = int
    basestring = str
    unicode = str
    from functools import reduce
    import asyncio
Future = asyncio.Future
Task = asyncio.Task
