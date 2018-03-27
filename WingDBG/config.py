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
"""WingDBG constants"""

import os
from Globals import package_home
from AccessControl.Permissions import view_management_screens, delete_objects
from AccessControl import ModuleSecurityInfo

security = ModuleSecurityInfo('WingDBG.config')

GLOBALS = globals()

security.declarePublic('PACKAGE_NAME', 'CONTROL_PANEL_ID', 'ICON_NAME')
PACKAGE_NAME = 'WingDBG'
CONTROL_PANEL_ID = 'WingDebugService'
ICON_NAME = CONTROL_PANEL_ID

PRODUCT_DIR = package_home(GLOBALS)
WWW_DIR = os.path.join(PRODUCT_DIR, 'www')
DOC_DIR = os.path.join(PRODUCT_DIR, 'documentation')

security.declarePublic('VIEW_PERMISSION', 'CHANGE_PERMISSION',
                       'USE_PERMISSION', 'DEL_PERMISSION')
VIEW_PERMISSION = view_management_screens
CHANGE_PERMISSION = 'Wing Debug Service: Change Settings'
USE_PERMISSION = 'Wing Debug Service: Control Debugger'
DEL_PERMISSION = delete_objects

# Remote IDE connection password mode constants
# Note that PW_ENC_TYPE_ROTOR is unused and retained only so
# stored state from old versions can be read
security.declarePublic('PW_MODE_PROFILE_DIR', 'PW_MODE_CUSTOM_DIR',
                       'PW_MODE_CUSTOM_PW', 'PW_ENC_TYPE_NONE',
                       'PW_ENC_TYPE_ROTOR')
PW_MODE_PROFILE_DIR, PW_MODE_CUSTOM_DIR, PW_MODE_CUSTOM_PW = range(3)
PW_ENC_TYPE_NONE, PW_ENC_TYPE_ROTOR = range(2)
