""" WingDBG product initialization """

import Globals
from config import *

# define icons; old style because we are not registering any addable types.
misc_ = {
    ICON_NAME: Globals.ImageFile('www/icon.gif', globals()),
}

def initialize(context): 
    """Initialize the WingDBG product."""
    import sys
    import WingDBG
    from ZODB.POSException import ConflictError
    from zLOG import WARNING, ERROR, INFO, LOG
    
    # Hack our way into the control panel
    cp = context._ProductContext__app.Control_Panel
    if WingDBG.WingDebugService.id not in cp.objectIds():
        wdbgs = WingDBG.WingDebugService()
        cp._setObject(wdbgs.id, wdbgs)
        LOG(PACKAGE_NAME, INFO, 
            'Installed Wing Debug Service in Control Panel')

    wds = cp._getOb(WingDBG.WingDebugService.id)
    if wds.auto_start:
        try:
            wds.startDebugger()
        except ConflictError:
            raise
        except:
            LOG(PACKAGE_NAME, ERROR, 'Could not start Wing IDE debugger',
                error=sys.exc_info())
            return

        if wds.connect_at_start:
            try:
                wds.connectIDE(wait=False)
            except ConflictError:
                raise
            except:
                LOG(PACKAGE_NAME, ERROR, 'Could not connect to IDE',
                    error=sys.exc_info())
                return
            
            if not wds.isConnected():
                LOG(PACKAGE_NAME, INFO, 'IDE connection pending')
            else:
                LOG(PACKAGE_NAME, INFO, 'Successfully connected to IDE')
