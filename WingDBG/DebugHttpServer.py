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

import sys
import os
if sys.platform != 'win32':
    import fcntl
    if sys.hexversion >= 0x02020000:
        from fcntl import F_SETFD
    else:
        from FCNTL import F_SETFD
    
import asyncore
import errno
import thread
import socket
import select
        
from ZServer import zhttp_server, zhttp_handler
from ZServer.HTTPServer import zhttp_channel
from ZServer.PubCore import ZRendezvous
from ZServer.PubCore import ZServerPublisher


class CDebugZServerPublisher (ZServerPublisher.ZServerPublisher):
    """ Publisher class which starts debugger when thread begins and stops 
    debugger when thread terminates. """
    
    def __init__(self, accept, debugger):
        """ Thread start function -- starts debugging for this thread and then 
        waits for requests.  Changes from non-debug Zope publisher class: if
        name is callable, it is called w/o any arguments and if name is None,
        the thread is terminated through a return. """

        debugger.fErr.out('New thread created; Python ident =', thread.get_ident())
        
        # Only debug this one thread
        debugger.SetDebugThreads({thread.get_ident():1}, 0)
        
        # Start w/o connecting
        debugger.StartDebug(connect = 0)

        # Loop until an accepted name is None and return is executed
        while 1:
            try:
                # Accept a new named request
                name, request, response=accept()
                
                # Terminate thread if name is None
                if name == None:
                    debugger.StopDebug()
                    debugger.fErr.out('Thread', thread.get_ident(), 'terminating')
                    return
                # Call name if it's callable
                elif callable(name):
                    name()
                # Else publish through standard publisher
                else:
                    if name == 'Zope' and debugger.ChannelClosed():
                        # We are about to run a Zope module, but we have no IDE
                        # connection. See if we need to auto-reconnect, and do
                        # so if necessary.
                        import Zope
                        from config import CONTROL_PANEL_ID
                        odb = Zope.bobo_application()
                        try:
                            wds = odb.Control_Panel._getOb(CONTROL_PANEL_ID)
                            ari = wds.auto_reconnect_ide
                        finally:
                            # Make sure we close the connection, otherwise
                            # we'll run out.
                            odb._p_jar.close()
                        if ari:
                            # Wrap in bare accept and raise to avoid exception
                            # detection.
                            try:
                                debugger.ConnectToClient()
                            except:
                                raise
                    if hasattr(ZServerPublisher, 'publish_module'):
                        ZServerPublisher.publish_module(name, request=request,
                                                        response=response)
                    # Zope 2.7+ has moved the publish_module call
                    else:
                        from ZPublisher import publish_module
                        publish_module(name, request=request,
                                       response=response)                        
            finally:
                if response != None:
                    response._finish()
                name=request=response=None

class CDebugZRendezvous (ZRendezvous.ZRendevous):
    """ Rendezvous class which uses CDebugZServerPublisher to service requests
    and passes the debugger instance through to them.  n should be 1 as long
    as Wing's debugger is single threaded. """
    
    def __init__(self, n=1, debugger=None, persist_debug_conn=1):

        # Calling __init__ with n=0 means that the pool will be empty
        ZRendezvous.ZRendevous.__init__(self, 0)

        # Zope 2.7+ changed the name of these methods
        if not hasattr(self, '_a'):
            self._a = self._acquire
        if not hasattr(self, '_r'):
            self._r = self._release
            
        # Create locks, subthreads to use the debug publisher
        pool, requests, ready = self._lists
        self._a()
        try:
            while n > 0:
                l=thread.allocate_lock()
                l.acquire()
                pool.append(l)
                thread.start_new_thread(CDebugZServerPublisher,
                                        (self.accept, debugger))
                n=n-1
        finally:
            self._r()
            
    def shutdown(self):
        """ Shutdown all threads. """
        
        self._a()
        try:
            pool, requests, ready = self._lists
            thread_count = len(pool) + len(ready)
        finally:
            self._r()
        
        for i in range(0, thread_count):
            self.handle(None, None, None)

class CDebugZHttpChannel (zhttp_channel):
    """ Http channel which call server._handle to handle requests. """
    
    #----------------------------------------------------------------------
    def work(self):
        """ Redirect request to server._handle method. """
        
        if not self.working:
            if self.queue:
                self.working=1
                try: module_name, request, response=self.queue.pop(0)
                except: return                

                self.server._handle(module_name, request, response)

class CDbgSocketDispatcher (asyncore.dispatcher):
    """ Asyncore dispatcher to watch debug socket. """
    
    #----------------------------------------------------------------------
    def __init__(self, sock, hook_obj):
        """ Constructor -- sock is the socket to select on and hook object is the
        object that created this one and is used to access the debugger. """
    
        asyncore.dispatcher.__init__(self, sock)
        self.fReadPending = 0
        self.fHookObj = hook_obj
        self.fErr = hook_obj.fErr
        self.__fClosed = 0
        
    #----------------------------------------------------------------------
    def readable(self):
        """ Select for reads when there's not a read pending. """
        
        return not self.fReadPending
    
    #----------------------------------------------------------------------
    def writable(self):
        """ Never select for writes. """
        
        return 0
    
    #----------------------------------------------------------------------
    def close(self):
        """ Override close so we can actually call close on the main thread. """

        # Do nothing if called multiple times
        if self.__fClosed:
            return
        
        self.fErr.out('Scheduling socket close')
        
        self.__fClosed = 1
        self.fHookObj.fAsyncInterrupt.interrupt(self.__close_impl)
        self.fHookObj = None
        
    #----------------------------------------------------------------------
    def __close_impl(self):
        """ Call close on the main thread. """
        
        self.fErr.out('Closing socket')

        # Call the inherited close method
        asyncore.dispatcher.close(self)

    #----------------------------------------------------------------------
    def handle_read(self):
        """ Handle read in main thread.  This simply queues a function to run in
        the work thread. """
      
        self.fErr.out(self.handle_read, 'called')
      
        if self.__fClosed:
            return
        
        # Put callback to work thread read in queue
        self.fReadPending = 1
        self.fHookObj.fZRendevzous.handle(self.__CB_WorkThreadRead, None, None)
      
    #----------------------------------------------------------------------
    def __CB_WorkThreadRead(self):
        """ Socket read callback to be called in the work thread (the one
        being debugged). """
        
        self.fErr.out(self.__CB_WorkThreadRead, 'called')

        # Do nothing if closed and grab hook obj ref in case another thread
        # sets it to None
        hook = self.fHookObj
        if self.__fClosed or hook is None:
            return
        
        # Call into the debugger
        if hook.fDbgCallback != None:
            hook.fDbgCallback()
      
        # Mark the dispatcher as readable and interrupt asynccore's select so
        # dispatcher is added to the readable list
        self.fReadPending = 0
        hook.fAsyncInterrupt.interrupt()

class CWingDbgSocketHook:
  """ Class for managing the debug server sockets:  This is used to instantiate
  our custom dispatchers and provide access to the debugger for them. """

  #----------------------------------------------------------------------
  def __init__(self, err, zrend, async_interrupt):
      """ Constructor """
      self.fErr = err
      self.fDbgCallback = None
      self.fZRendevzous = zrend
      self.fAsyncInterrupt = async_interrupt
      
  #-----------------------------------------------------------------------
  def _Setup(self, mod, s, cb_fct):
      """ Attempt to set up socket registration with the given module
      reference : This should be a reference to the indicator module
      for the supported environment.  The first socket is registered 
      with given action callback via _RegisterSocket().  Returns the
      socket if succeeded or None if fails (e.g. because the module is 
      not yet fully loaded and we cannot yet use it to start registering 
      sockets.  Note that the returned socket may be different than the
      socket passed in because some environments require a wrapper:  The
      returned socket is then used in place of the original in the
      debug server code. """
      
      # Just try to register the first socket; no extra tests needed
      return self._RegisterSocket(s, cb_fct)
  
  #----------------------------------------------------------------------
  def _RegisterSocket(self, s, cb_fct):
      """ Function to register a socket with a mainloop: Subsequently the given
      callback function is called whenever there is data to be read on the
      socket.  Returns the socket if succeeded; None if fails. As in _Setup(),
      the returned socket may differ from the one passed in, in which case
      the debug server will substitute the socket that is used in its code."""
  
      self.fDbgCallback = cb_fct
      
      # Construct dispatcher
      dispatcher = CDbgSocketDispatcher(s, self)

      self.fErr.out("################ Registered socket with Zope: ", s, 
                    "sockname =", s.getsockname())

      return dispatcher
      
  #----------------------------------------------------------------------
  def _UnregisterSocket(self, s):
      """ Function to unregister a socket with the supported environment.
      The socket passed in should be the one returned from _Setup() or
      _RegisterSocket(). """
      
      self.fErr.out("################ Deregistered socket with Zope: ", s)
 
      # Close dispatcher 
      s.close()

      
class CDebugZHttpServer (zhttp_server):
    """ Debug version of zhttp_server.  Exists to specify that CDebugZHttpChannel
    be used and to implement a _handle method, which calls dowan to a
    CDebugZRendezvous instance. """

    channel_class = CDebugZHttpChannel

    def __init__ (self, ip, port, resolver=None, logger_object=None, 
                  debugger=None, async_interrupt = None):
        zhttp_server.__init__(self, ip, port, resolver, logger_object)
        self.zrend = CDebugZRendezvous(1, debugger, 1)
        self.debugger = debugger
        self.__fErr = debugger.fErr

        if async_interrupt is None:
            self.async_interrupt = CAsyncoreInterrupt()
        else:
            self.async_interrupt = async_interrupt
            
        # Create socket hook and install it into debugger
        socket_hook = CWingDbgSocketHook(debugger.fErr, self.zrend, 
                                         async_interrupt)
        debugger.SetSocketRegHook(socket_hook)
        
    def _handle(self, *args):
        apply(self.zrend.handle, args)

    def RunOnDebugThread(self, func):
        """ Schedules func to be run on debug thread. """
        
        self.zrend.handle(func, None, None)
        
    def Shutdown(self):
        """ Shutdown the server.  This actually schedules a method on the main
        server to perform the shutdown. """
        
        self.async_interrupt.interrupt(self.__Shutdown)
        self.debugger = None
        
    def __Shutdown(self):
        """ Shutdown the server.  This must be called on the thread that the
        asyncore's mainloop runs on. """

        self.__fErr.out('Shutting down debug http server')
        self.close()
        self.zrend.shutdown()
        
        # Close all channels that referred to self
        for dispatcher in asyncore.socket_map.values():
            if isinstance(dispatcher, CDebugZHttpChannel) \
               and dispatcher.server == self:
                dispatcher.close()
        
        
def CreateSocketPipe():
    """ Creates a pair of tcp/ip sockets, one for reading & one for writing.
    Similiar to os.pipe, but return values can be used with asyncore.  Raises
    exception on failure. """

    # Timeout on each individual op is .5 seconds
    timeout = 0.5
    
    # Create listening socket to only listen for local connections
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listen_sock.setblocking(0)
        if sys.platform != 'win32':
          fcntl.fcntl(listen_sock.fileno(), F_SETFD, 1)
        listen_sock.bind(('127.0.0.1', 0))
        listen_sock.listen(1)
        listen_addr = listen_sock.getsockname()
        
        # Create read socket & connect to our listener
        rd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rd.setblocking(0)
        if sys.platform != 'win32':
          fcntl.fcntl(rd.fileno(), F_SETFD, 1)
        rd.connect_ex(listen_addr)
        
        # Accept the connection from the read socket
        r = e = [listen_sock]
        w = []
        try:
            r,w,e = select.select (r,w,e, timeout)
        except select.error, err:
            if err[0] != EINTR:
                if rd is not None:
                    rd.close()
                raise
        if len(r) != 1:
            if rd is not None:
                rd.close()
            raise ValueError('Connection not made')
        wr, addr = listen_sock.accept()
        wr.setblocking(0)
        if sys.platform != 'win32':
          fcntl.fcntl(wr.fileno(), F_SETFD, 1)

        return rd, wr

    finally:
        listen_sock.close()
        
class CAsyncoreInterrupt (asyncore.dispatcher):
    """ A class that allows the asyncore mainloop select to be interrupted.
    Implemented with a pair of sockets that act like a pipe: one is registered in
    the asyncore map as a readable socket and then a byte is sent via the other
    socket so the mainloop is woken up from its select call. """
    
    def __init__(self):
        """ Constructor -- creates pipe andregisters read end of the pipe. """
        
        rd, wr = CreateSocketPipe()
        
        asyncore.dispatcher.__init__(self, rd)
        self.__fReadSock = rd
        self.__fWriteSock = wr
        
        self.__fMainThreadFunctions = []
        self.__fFunctionsLock = thread.allocate_lock()
        
    def writable(self):
        """ Writable test for dispatcher; always returns false. """

        return 0
    
    def handle_error(self):
        """ Handle error -- treated as a handle_read. """
        
        return self.handle_read()
    
    def handle_expt(self):
        """ Handle expt -- treated as a handle_read. """

        return self.handle_read()
    
    def handle_read(self):
        """ Handle read -- read all bytes in the pipe so multiple calls to interrupt
        before it is interrupted only interrupt it once. """

        # Read 50 bytes at a time as long as there's more data
        kReadSize = 50
        more_data = 1
        while more_data:

            # Read and check length of resulting data
            try:
                data = self.recv(kReadSize)
                if len(data) == 0:
                    self.close()
                    more_data = 0
                else:
                    more_data = (len(data) == kReadSize)
            # Convert EWOULDBLOCK exception to more_data == false, but let other
            # exceptions through
            except socket.error, exc:
                if exc[0] == errno.EWOULDBLOCK:
                    more_data = 0
                else:
                    raise

        # Get list of functions to run while locked
        self.__fFunctionsLock.acquire()
        try:
            to_run = self.__fMainThreadFunctions
            self.__fMainThreadFunctions = []
        finally:
            self.__fFunctionsLock.release()

        # Run any functions
        for func, args in to_run:
            if callable(func):
                apply(func, args)
                
    def interrupt(self, func = None, args = ()):
        """ Schedule an interruption of the mainloop. If func is callable, it will be
        called sometime in the future (possibly before this method returns) on the
        main thread. """

        if callable(func):
            self.__fFunctionsLock.acquire()
            try:
                self.__fMainThreadFunctions.insert(0, (func, args))
            finally:
                self.__fFunctionsLock.release()
        
        self.__fWriteSock.send('?')
