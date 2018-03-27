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
"""WingDBG utility methods"""

import os
import sys
import string
import random

if sys.platform != 'win32':
    import pwd

from zLOG import ERROR, LOG

def findInternalWinghome(winghome):
    """Find the pathname of the internal winghome setting.

    On OS X, this may add components to the path that are normally hidden from 
    the user.  Returns None if winghome seem to be valid.

    """
    if not os.path.isdir(winghome):
        return None
    
    if os.path.isfile(os.path.join(winghome, 'bin', 'wingdb.py')) \
       or os.path.isfile(os.path.join(winghome, 'src', 'wingdb.py')):                   
        return winghome
    
    if sys.platform[:6] == 'darwin':
        for extra in ['Contents/Resources', 'WingIDE.app/Contents/Resources']:
            internal = os.path.join(winghome, extra)
            if os.path.isfile(os.path.join(internal, 'bin', 'wingdb.py')) \
               or os.path.isfile(os.path.join(internal, 'src', 'wingdb.py')):                   
                return internal
            
    return None

def getWingIDEDir(netserver=None):
    """Get the Wing profile directory for the current user.
    
    If the debugger core has not been loaded yet, this may not be precisely
    correct because of the absence of a GetUserName function on win32. 
    Returns None if the dir doesn't and can't exist -- this occurs on
    Unix when the user has no home dir.

    """
    if sys.platform == 'win32':
        if netserver is not None:
            return netserver.abstract._GetUserWingProfileDir()
        else:
            username = getUsername()
            if username is None:
                username = '$(USERNAME)'
            return os.path.join(r'c:\Documents and Settings', username, 
                                'Application Data', 'Wing IDE 6')
    else:
        # On posix; use the expand path methodology and detect when that fails
        # or opens up a security problem (home set to /)
        path = os.path.expanduser('~/.wingide6')
        if path in ('~/.wingide6', '/.wingide6'):
            return None
        return path
        
def getUsername(netserver=None):
    """Get the name of the user running the current process. 

    Returns None if name can't be determined.

    """
    
    try:
        # Windows
        if sys.platform == 'win32':
            # Try dbgtracer's GetUserName first
            if netserver is not None:
                try:
                    return netserver.dbgserver.dbgtracer.GetUserName()
                except OSError:
                    pass
                
            # Try to import win32api and get user name from there
            try:
                import win32api, pywintypes
                try:
                    return win32api.GetUserName()
                except pywintypes.error:
                    pass
            except ImportError:
                pass

            # Fallback to env
            return os.environ.get('USERNAME', None)
        
        # Posix systems
        else:
            # Get uid and lookup passwd entry
            uid = os.getuid()
            return pwd.getpwuid(uid)[0]

    except (IndexError, OSError):
        return None

def generatePRandomPW(pwlen=16, mix_case=1):
    """Generate a pseudo-random password.
    
    Generate a pseudo-random password of given length, optionally 
    with mixed case.  Warning: the randomness is not cryptographically 
    very strong.

    """
    
    if mix_case:
        chars = string.ascii_letters + string.digits
    else:
        chars = string.ascii_lowercase + string.digits
        
    pw = ''
    for i in range(0, pwlen):
        pw += random.choice(chars)
    return pw
