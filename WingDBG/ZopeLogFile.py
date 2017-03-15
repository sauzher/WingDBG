##############################################################################
# Copyright (c) 2002-2005, Archaeopteryx Software, Inc.  All rights reserved.
#
# Written by Stephan R.A. Deibel (sdeibel@archaeopteryx.com),
# John Ehresman (jpe@archaeopteryx.com) and 
# Martijn Pieters (mj@zopatista.com)
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
##############################################################################
__doc__ = """File-like object which writes to Zope eventlog facility

All written information is collected until a newline is written after which the
collected line will be sent to the logging module.

"""

import logging

class ZopeLogFile:
    """File-like object that sends all data written to it to the Zope eventlog
    (which Zope will have handlers configured for).
    
    Data is collected and logged as summary lines whenever a newline is 
    encountered. On creation, set the subsystem under which the lines should be 
    logged. By default the INFO severity is used, unless a different severity
    is specified on creation of the class.
    
    """
    severity = logging.INFO
    subsystem = ''
    _data = ''
    
    def __init__(self, subsystem, severity=logging.INFO):
        self.subsystem = subsystem
        self.severity = severity
        
    def write(self, text):
        self._data += text
        while '\n' in self._data:
            line, self._data = self._data.split('\n', 1)
            logger = logging.getLogger(self.subsystem)
            logger.log(self.severity, line)
            
            