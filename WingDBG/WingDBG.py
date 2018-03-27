##############################################################################
# Copyright (c) 2002-2017, Archaeopteryx Software, Inc.  All rights reserved.
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
__doc__ = """Wing Debugger Service Module"""

__version__ = '6.0.9'


import os
import sys
import imp
import socket
import time

from urllib import quote_plus

import Globals
from App.version_txt import getZopeVersion
from OFS.SimpleItem import SimpleItem
from OFS.PropertyManager import PropertyManager
from AccessControl import ClassSecurityInfo
from Products.PageTemplates.PageTemplateFile import PageTemplateFile

import asyncore
from ZServer import zhttp_server, zhttp_handler

import DebugHttpServer
import ScriptDebugging
from ZopeLogFile import ZopeLogFile
from utils import *
from config import *

# Global singleton objects
gNetServer = None
gAsyncInterrupt = DebugHttpServer.CAsyncoreInterrupt()
gHttpServer = None # Active http server


class CannotStartDebugger(Exception):
    """ Simple exception class to encode the reason the debugger can't be
    loaded. """
    
    def __init__(self, reason):
        """ Set the reason attribute. """
        
        self.reason = reason
        sys.stderr.write(reason + '\n')
        
class IDEConnectionTimeOut(Exception):
    """Flag exception thrown on IDE conn timeout."""
    

def connectToIDECallback(status):
    """Callback to open IDE connection on debug server thread"""
    try:
        if gHttpServer.debugger is not None:
            # temporary try: except: wrapper to work around exception
            # detection in the debugger
            try:
                # Without the following line, the debugger-to-IDE 
                # auto-connect fails. It seems some C calls are needed 
                # for things to resolve; race condition somewhere? 
                # network channel throws a socket.error (107) if not.
                # Note that the old code (using _v_http_server) would
                # fail too if it weren't for more C calls (through
                # dict lookups) and persistence mechanisms.
                repr(gHttpServer)
                gHttpServer.debugger.ConnectToClient()
            except:
                # bare except, but with re-raise
                raise
    finally:
        status['completed'] = 1


class WingDebugService(SimpleItem, PropertyManager): 
    """ Wing debugger object. """
        
    meta_type = 'Wing Debug Service'
    id = CONTROL_PANEL_ID
    title = 'Wing Debug Service'
    icon = 'misc_/%s/%s' % (PACKAGE_NAME, ICON_NAME)
    version = __version__
    
    security = ClassSecurityInfo()
    
    # Configuration properties
    _properties = (
        # General configuration
        {'id': 'wing_home', 'type': 'string', 'mode': 'w'},
        {'id': 'log_file', 'type': 'string', 'mode': 'w'},
        # Where to find the IDE
        {'id': 'ide_host', 'type': 'string', 'mode': 'w'},
        {'id': 'ide_port', 'type': 'int', 'mode': 'w'},
        # Where to open the debugging HTTP server
        {'id': 'http_host', 'type': 'string', 'mode': 'w'},
        {'id': 'http_port', 'type': 'int', 'mode': 'w'},
        # Enable script support through monkey patches
        {'id': 'script_support', 'type': 'boolean', 'mode': 'w'},
        # Start and connection automation
        {'id': 'auto_start', 'type': 'boolean', 'mode': 'w'},
        {'id': 'connect_at_start', 'type': 'boolean', 'mode': 'w'},
        {'id': 'auto_reconnect_ide', 'type': 'boolean', 'mode': 'w'},
        # Remotely initiated IDE connections
        {'id': 'allow_attach', 'type': 'boolean', 'mode': 'w'},
        {'id': 'pw_mode', 'type': 'selection', 'mode': 'w', 
         'select_variable': 'pw_mode_options'},
        {'id': 'pw_dir', 'type': 'string', 'mode': 'w'},
        {'id': 'custom_encrypt_type', 'type': 'selection', 'mode': 'w', 
         'select_variable': 'custom_encrypt_type_options'},
        {'id': 'custom_connect_pw', 'type': 'string', 'mode': 'w'},
        {'id': 'attach_port', 'type': 'int', 'mode': 'w'},
        )

    # configuration
    wing_home = ''
    log_file = ''

    ide_host = 'localhost'
    ide_port = 50005
    http_host = 'localhost'
    http_port = 50080

    # advanced configuration
    script_support = 0
    auto_start = 0
    connect_at_start = 1
    auto_reconnect_ide = 0
    
    allow_attach = 0
    pw_mode = PW_MODE_CUSTOM_DIR
    pw_dir = ''
    custom_encrypt_type = PW_ENC_TYPE_NONE
    custom_connect_pw = ''
    attach_port = 50015

    # Only intended for PropertyManager UI at
    # /Control_Panel/WingDebugService/manage_propertiesForm
    pw_mode_options = (PW_MODE_PROFILE_DIR, PW_MODE_CUSTOM_DIR, 
                       PW_MODE_CUSTOM_PW)
    custom_encrypt_type_options = (PW_ENC_TYPE_NONE,)

    def __init__(self): 
        if sys.platform == 'win32':
            self.wing_home = r'c:\Program Files (x86)\Wing IDE 6'
        elif sys.platform.startswith('darwin'):
            self.wing_home = '/Applications/WingIDE.app'
        else:
            self.wing_home = '/usr/lib/wingide6'
        
        winghome_file = os.path.join(PRODUCT_DIR, '.winghome')
        if os.path.isfile(winghome_file):
            try:
                wing_home = open(winghome_file).readline().strip()
                if wing_home:
                    self.wing_home = wing_home
            except IOError:
                pass

        # Turn on script support by default for versions of Zope where 
        # our monkey patching is likely to work
        if getZopeVersion()[:2] >= (2, 7):
            self.script_support = 1
            
        # Set default remote attach password mode to profile dir mode if
        # a profile dir can be found. TODO: copy to __set_state__ as well?
        if self.getProfileDir():
            self.pw_mode = PW_MODE_PROFILE_DIR
            
    #
    # Utility queries
    #

    security.declareProtected(VIEW_PERMISSION, 'hasStarted')
    def hasStarted(self):
        """Return wether or not the debugger has started"""
        return gHttpServer is not None
    
    security.declareProtected(VIEW_PERMISSION, 'isConnected')
    def isConnected(self):
        """ Returns whether the debugger is connected to the IDE. """
        if not self.hasStarted():
            return 0
        else:
            debugger = gHttpServer.debugger
            return debugger is not None and not debugger.ChannelClosed()
        
    security.declareProtected(VIEW_PERMISSION, 'serverUrl')
    def serverUrl(self):
        """Return the URL of the debug server"""
        if not self.http_host:
            http_host = socket.gethostname()
        else:
            http_host = self.http_host
        return "http://%s:%d" % (http_host, self.http_port)
    
    security.declareProtected(VIEW_PERMISSION, 'wingHomeExists')
    def wingHomeExists(self):
        """Return true if wing_home is an existing directory"""
        return os.path.isdir(self.wing_home)

    security.declareProtected(VIEW_PERMISSION, 'wingHomeIsValid')
    def wingHomeIsValid(self):
        """Return true if wing_home is a valid Wing Home dir"""
        return not not findInternalWinghome(self.wing_home)

    security.declareProtected(VIEW_PERMISSION, 'getProfileDir')
    def getProfileDir(self):
        """Return directory name of the profile dir for the current user."""
        return getWingIDEDir(gNetServer)
    
    security.declareProtected(VIEW_PERMISSION, 'wingDebugPwIsValid')
    def wingDebugPwIsValid(self):
        """Return true if wingdebugpw can be found"""
        dir = self.getProfileDir()
        return dir and os.path.isfile(os.path.join(dir, 'wingdebugpw'))

    #
    # Debugger control
    #
    
    security.declareProtected(USE_PERMISSION, 'startDebugger')
    def startDebugger(self):
        """Start debug server"""
        # Install script debugging patch if requested
        if self.script_support:
            ScriptDebugging.patch()
        
        # Find http server so we can reuse the resolver, logger, module_name,
        # uri_base, & env_override
        MODULE = 'Zope'
        rs = None
        lg = None
        uri_base = ''
        env_override = {}
        for dispatcher in asyncore.socket_map.values():
            if isinstance(dispatcher, zhttp_server) \
               and not isinstance(dispatcher, DebugHttpServer.CDebugZHttpServer):
                lg = dispatcher.logger.logger
                rs = getattr(dispatcher.logger, 'resolver', None)
                for handler in dispatcher.handlers:
                    if isinstance(handler, zhttp_handler):
                        MODULE = handler.module_name
                        uri_base = handler.uri_base
                        if uri_base == '/':
                            uri_base = ''
                        env_override = handler.env_override
                break

        # Create debugger
        debugger = self.__create_debugger()

        # Set in global http server -- note not thread safe
        global gHttpServer
        gHttpServer = DebugHttpServer.CDebugZHttpServer(
            ip=self.http_host, port=int(self.http_port),
            resolver=rs, logger_object=lg, debugger=debugger,
            async_interrupt=gAsyncInterrupt)
        
        # Handler for a published module. zhttp_handler takes 3 arguments:
        # The name of the module to publish, and optionally the URI base
        # which is basically the SCRIPT_NAME, and optionally a dictionary
        # with CGI environment variables which override default
        # settings. The URI base setting is useful when you want to
        # publish more than one module with the same HTTP server. The CGI
        # environment setting is useful when you want to proxy requests
        # from another web server to ZServer, and would like the CGI
        # environment to reflect the CGI environment of the other web
        # server.    
        zh = zhttp_handler(MODULE, uri_base, env_override)
        gHttpServer.install_handler(zh)
        
    security.declareProtected(USE_PERMISSION, 'stopDebugger')
    def stopDebugger(self):
        """Stop debugging server"""
        if self.hasStarted():
            global gHttpServer
            gHttpServer.Shutdown()
            gHttpServer = None
            gAsyncInterrupt.interrupt()
            
            if self.script_support:
                ScriptDebugging.unpatch()
                
            self._unload_wingdb_modules()
        
    security.declareProtected(USE_PERMISSION, 'connectIDE')
    def connectIDE(self, wait=True):
        """Connect to the IDE"""
        # Schedule the connection
        if self.hasStarted():
            status = {'completed': 0}
            cb = lambda conn=connectToIDECallback, s=status: conn(s)
            gHttpServer.RunOnDebugThread(cb)
            
            # Wait up for connection
            if wait:
                start_time = time.time()
                while time.time() < start_time + 10 and not status['completed']:
                    time.sleep(0.05)
                if not status['completed']:
                    raise IDEConnectionTimeOut

    security.declarePrivate('_import_netserver')
    def _import_netserver(self):
        """ Import the wingdbstub module. """
        
        global gNetServer
        if gNetServer != None:
            return gNetServer
        
        internal_home = findInternalWinghome(self.wing_home)
        if internal_home is None:
            raise CannotStartDebugger('Cannot find wingdb.py in $(WINGHOME)/src or'
                                     ' $(WINGHOME)/bin')
        
        try:
            exec_dict = {}
            execfile(os.path.join(winghome, 'bin', '_patchsupport.py'), exec_dict)
            find_matching = exec_dict['FindMatching']
            dir_list = find_matching('bin', internal_home, user_settings=None)
        except Exception:
            dir_list = []

        dir_list.extend([os.path.join(internal_home, 'bin'), 
                         os.path.join(internal_home, 'src')])
        wingdb = None
        for path in dir_list:
            try:
                f, p, d = imp.find_module('wingdb', [path])
                wingdb = imp.load_module('wingdb', f, p, d)
                break
            except ImportError:
                if sys.modules.has_key('wingdb'):
                    del sys.modules['wingdb']
        if wingdb is None:
            raise CannotStartDebugger('Cannot find wingdb.py in $(WINGHOME)/src or'
                                     ' $(WINGHOME)/bin')

        try:
            gNetServer = wingdb.FindNetServerModule(internal_home)
        except ImportError:
            raise CannotStartDebugger('Error loading debugger.  Please make sure'
                                      ' the correct version of the debugger'
                                      ' runtime is installed')
        
        return gNetServer
    
    security.declarePrivate('_unload_wingdb_modules')
    def _unload_wingdb_modules(self):
        """Remove the Wing debugger modules
        
        This so we can load them from a different location if our winghome
        is changed.
        
        """
        # Prevent exceptions from being leaked, remove them explicitly
        tracer = gNetServer.dbgserver.dbgtracer
        tracer.set_always_stop_excepts(())
        tracer.set_never_stop_excepts(())
        
        # Stop tracing
        tracer.stop_trace()
        
        # Unload modules
        for name in ('wingdb', 'netserver'):
            if sys.modules.has_key(name):
                del sys.modules[name]

    security.declarePrivate('__create_debugger')
    def __create_debugger(self):
        """ Create debugger object to connect back to the given port. """
        
        netserver = self._import_netserver()
        
        # Check for any other active debugger
        if netserver.dbgserver.dbgtracer.get_tracing():
            raise CannotStartDebugger("Another debugger is already active."
                                     " Wing currently only supports one"
                                     " active debugger per Zope process")
        
        # Create log object
        log = self.log_file
        if log == '<zopelog>':
            log = ZopeLogFile('Wing Debug Service')
        err = netserver.abstract.CErrStream([log], 1)

        # Construct pw file path
        pw_path = []
        if self.pw_mode == PW_MODE_PROFILE_DIR:
            pwfile_dir = self.getProfileDir()
            if pwfile_dir is not None:
                pw_path.append(pwfile_dir)
                
        elif self.pw_mode == PW_MODE_CUSTOM_DIR and self.pw_dir:
            pw_path.append(os.path.expanduser(self.pw_dir))
            
        attach_port = -1
        if self.allow_attach:
            attach_port = self.attach_port
            
        # Create debugger and then set any custom security settings    
        debugger = netserver.CNetworkServer(self.ide_host, self.ide_port, 
                                            attach_port, err, 
                                            pwfile_path=pw_path)
        
        # Set encrytion options
        if self.pw_mode == PW_MODE_CUSTOM_PW:
            # Custom mode
            debugger.SetSecurityInfo(self.custom_connect_pw)
            
        # Raise exception if security info is invalid
        if self.allow_attach and not debugger.IsSecurityInfoValid():
            debugger.Stop()
            # Set default message and then try to do better
            msg = ('Cannot create debugger because no connection'
                   ' security information was found.  Please check'
                   ' the Connection Security options in the'
                   ' Advanced Settings page.')
            if pw_path: # Always either empty or length 1
               pathname = os.path.join(pw_path[0], 'wingdebugpw')
               if not os.access(pathname, os.R_OK):
                   msg = ('Cannot create debugger because "%s"'
                          ' cannot be read.\nPlease make sure the user %s'
                          ' can read the file or change the directory that'
                          ' wingdebugpw is read from via the Connection'
                          ' Security options in the Advanced Settings page.' 
                          % (pathname, getUsername(gNetServer) or '<unknown>'))
                         
            raise CannotStartDebugger(msg)
            
        debugger.SetUseSocketHooksOnImport(0)
        return debugger

    #
    # Zope Management Interface methods
    #
    
    manage_options = ({'label': 'Status', 'action': 'manage_main'},
                      {'label': 'Configure', 'action': 'manage_configureForm'},
                      {'label': 'Advanced settings', 
                       'action': 'manage_advancedForm'},
                      {'label': 'Remove', 'action': 'manage_removeForm'},
                      {'label': 'Documentation', 'action': 'manage_document'},
                      # Property Manager interface
                      # {'label': 'Propeties', 'action': 'manage_propertiesForm'},
                      ) 

    security.declareProtected(VIEW_PERMISSION, 'manage_main')
    manage_main = PageTemplateFile('status.pt', WWW_DIR,
                                   __name__='manage_debug')
    security.declareProtected(CHANGE_PERMISSION, 'manage_configureForm')
    manage_configureForm = PageTemplateFile('configure.pt', WWW_DIR,
                                            __name__='manage_configureForm')
    security.declareProtected(CHANGE_PERMISSION, 'manage_advancedForm')
    manage_advancedForm = PageTemplateFile('advanced.pt', WWW_DIR,
                                           __name__='manage_advancedForm')
    security.declareProtected(DEL_PERMISSION, 'manage_removeForm')
    manage_removeForm = PageTemplateFile('remove.pt', WWW_DIR,
                                         __name__='manage_removeForm')
    security.declareProtected(VIEW_PERMISSION, 'manage_document')
    manage_document = PageTemplateFile('documentation.pt', WWW_DIR,
                                       __name__='manage_document')
    security.declareProtected(VIEW_PERMISSION, 'manage_conn_trouble')
    manage_conn_trouble = PageTemplateFile('connection_trouble_help.pt', 
                                           WWW_DIR, 
                                           __name__='manage_conn_trouble')
              
    security.declareProtected(USE_PERMISSION, 'manage_start')
    def manage_start(self, REQUEST):
        """Method to start debugger.  Callable from management console."""
        try:
            self.startDebugger()
        except CannotStartDebugger, exc:
            REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                self.absolute_url(), 'manage_main', 
                'Could+not+start+Wing+IDE+debugger:+'
                '%s' % quote_plus(exc.reason)))
        
        # Next step: either connect or display status page
        if self.connect_at_start:
            return self.manage_connect(REQUEST)
        REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
            self.absolute_url(), 'manage_main', 'Debugger+started'))
        
    security.declareProtected(USE_PERMISSION, 'manage_stop')
    def manage_stop(self, REQUEST):
        """ stop debug """
        self.stopDebugger()    
        REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
            self.absolute_url(), 'manage_main', 'Debugger+stopped'))

    security.declareProtected(USE_PERMISSION, 'manage_connect')
    def manage_connect(self, REQUEST):
        """ Connect the debugger to the IDE. """

        # Return main page if already connected
        if self.isConnected():
            REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                self.absolute_url(), 'manage_main', 
                'Already+connected+to+IDE'))
            return                

        try:
            self.connectIDE()
        except IDEConnectionTimeOut:
            REQUEST.RESPONSE.redirect('%s/%s?connection_timeout=1&'
                                      'manage_tabs_message=%s' % (
                self.absolute_url(), 'manage_main', 'Connection+timed+out'))
            return
           
        # Goto main page if connected and print error page if not
        if self.isConnected():
            REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                self.absolute_url(), 'manage_main', 'Connected+to+IDE'))
            return

        REQUEST.RESPONSE.redirect('%s/%s' % (self.absolute_url(), 
                                             'manage_conn_trouble'))
            
    security.declareProtected(CHANGE_PERMISSION, 'manage_configure')
    def manage_configure(self, REQUEST, advanced=0, log_file_path=''):
        """Change configuration values
        
        This method is called from 
        """
        # Re-use the property manager; it'll take things from the REQUEST
        self.manage_changeProperties(REQUEST)

        # normalize log_file value (if set)
        if self.log_file == '<file>':
            self.log_file = log_file_path

        if not self.hasStarted():
            msg = quote_plus('Start the debugger for changes to take effect.')
        else:
            msg = quote_plus('Restart the debugger for the changes to take '
                             'effect.')

        tab = advanced and 'manage_advancedForm' or 'manage_configureForm'
        REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s+%s' % (
            self.absolute_url(), tab, 'Changes+saved.', msg))
        
    security.declareProtected(DEL_PERMISSION, 'manage_remove')
    def manage_remove(self, sure=0, REQUEST=None):
        """Remove the service from the Control_Panel"""
        if not sure:
            message = ("Please check the 'Are you sure?' box if you want to "
                       "remove the Wing Debug Service from the Control Panel.")
            if REQUEST is not None:
                REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                    self.absolute_url(), 'manage_removeForm', 
                    quote_plus(message)))
            return

        cp = self.aq_parent
        cp._delObject(self.id)
        if REQUEST is not None:
            REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                cp.absolute_url(), 'manage_main', 'Service+removed'))        
        
    security.declareProtected(VIEW_PERMISSION, 'manage_readDocumentation')
    def manage_readDocumentation(self):
        """Re-use HTML documentation inside management interface"""
        html = open(os.path.join(DOC_DIR, 'wingdbgdocs.html'), 'r').read()
        html = html[html.find('<body>') + 6:html.find('</body>')]
        return html

Globals.InitializeClass(WingDebugService)

#
# Migration Class
#

class WingDBG(SimpleItem):
    """Migration class
    
    Previous versions of WingDBG used to require the manual installation of 
    WingDBG debugger instances somewhere in the Zope object hierarchy. This
    class replaces these instances and offers a migration option.

    This class should not be normally used, it is only intended as a target
    for the unpickled old-style instances.
    
    """
    
    security = ClassSecurityInfo()
    
    meta_type = 'Wing Debugger migrator'
    title = 'Wing Debugger instance (to be migrated)'
    icon = 'misc_/%s/%s' % (PACKAGE_NAME, ICON_NAME)
    fields = ( # name, label, group
        ('wing_home', 'Wing Home', 0), 
        ('log_file', 'Log File', 0),
        ('ide_host', 'IDE Host', 0),
        ('ide_port', 'IDE Port', 0),
        ('http_host', 'HTTP Host', 0),
        ('http_port', 'HTTP Port', 0),
        ('script_support', 'Script Support', 1),
        ('connect_at_start', 'Auto connect', 1),
        ('allow_attach', 'Allow Remote IDE Attach', 1),
        ('pw_mode', 'Password Source', 1),
        ('pw_dir', 'Custom Password Directory', 1),
        ('custom_encrypt_type', 'Custom Encrypt Mode', 1),
        ('custom_connect_pw', 'Custom Connection Password', 1),
        ('attach_port', 'Attach Port', 1),
    )
    
    # Notice: old permissions 'Change Wing Debuggers' and 'View Wing Debuggers'
    # will be lost and cannot be migrated. The latter permission wasn't any
    # use anyway, but what the hey.
    
    manage_options = ({'label': 'Migrate', 'action': 'manage_main'},)
    
    security.declareProtected(VIEW_PERMISSION, 'manage_main')
    manage_main = PageTemplateFile('migrate.pt', WWW_DIR, 
                                   __name__='manage_main')

    security.declareProtected(CHANGE_PERMISSION, 'manage_migrate')
    def manage_migrate(self, fields=(), REQUEST=None):
        """Copy the indicated fields over to the CP service"""
        props = {}
        for field, label, group in self.fields:
            if field in fields:
                props[field] = self.getLocalValue(field)
                
        wdbg = self.Control_Panel._getOb(CONTROL_PANEL_ID)
        wdbg.manage_changeProperties(props)
        
        if REQUEST is not None:
            REQUEST.RESPONSE.redirect('%s/%s?manage_tabs_message=%s' % (
                self.absolute_url(), 'manage_main', 
                'Migration+succesful.+This+object+can+now+be+safely+removed'))
            
    security.declareProtected(VIEW_PERMISSION, 'getChangedFields')
    def getChangedFields(self):
        """Returns a dict of attribute names that may need to be migrated

        Keys are the attribute names, values a boolean flag indicating that 
        the local value is different from the service.
        
        """
        changed = {}
        
        for field, label, grp in self.fields:
            local = self.getLocalValue(field)
            service = self.getServiceValue(field)

            changed[field] = local != service
        
        return changed
    
    security.declareProtected(CHANGE_PERMISSION, 'getDisplayValue')
    def getDisplayValue(self, field, value):
        if field == 'pw_mode':
            return ('From User Settings Directory', 'From custom directory', 
                    'Custom password and scrambling mode')[value]
        if field == 'custom_encrypt_type':
            return ('Plaintext',)[value]
        return value
        
    security.declareProtected(CHANGE_PERMISSION, 'getLocalValue')
    def getLocalValue(self, field):
        value = getattr(self, field, None)
        return self._convertOldValue(field, value)
    
    security.declareProtected(CHANGE_PERMISSION, 'getServiceValue')
    def getServiceValue(self, field):
        wdbg = self.Control_Panel._getOb(CONTROL_PANEL_ID)
        value = wdbg.getProperty(field)
        return value

    security.declarePrivate('_convertOldValue')
    def _convertOldValue(self, field, value):
        # Migrate old-style property to new service style
        if field == 'log_file' and value == '<none>':
            # <none> used to signify no log file.
            value = ''

        elif field == 'script_support' and value is None:
            # Never defined locally, default to service value
            value = self.getServiceValue(field)
        
        elif field == 'allow_attach':
            # Field was defined as a attach_port of -1
            value = self.attach_port != -1
            
        elif field == 'pw_mode':
            # was defined as a text property
            orig = self.pw_option
            if orig == 'no_pwfile':
                # The default used to be 'no extra security'; but this was
                # an illegal option for when you wanted the attach port
                # enabled, so it was eliminated. Default to service value
                value = self.getServiceValue(field)
            elif orig == 'profile_dir':
                value = PW_MODE_PROFILE_DIR
            elif orig == 'custom_dir':
                value = PW_MODE_CUSTOM_DIR
            else:
                value = PW_MODE_CUSTOM_PW
                
        elif field == 'pw_dir':
            # Old field was named custom_pw_dir
            value = self.custom_pw_dir
            
        elif field == 'custom_encrypt_type':
            # Unsupported field
            value = PW_ENC_TYPE_NONE

        elif field == 'attach_port' and value == -1:
            # Was switched off, use service attach_port instead
            value = self.getServiceValue(field)
            
        wdbg = self.Control_Panel._getOb(CONTROL_PANEL_ID)
        if wdbg.getPropertyType(field) == 'boolean':
            value = not not value
            
        return value

Globals.InitializeClass(WingDBG)
