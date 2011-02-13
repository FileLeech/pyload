# -*- coding: utf-8 -*-
"""
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License,
    or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, see <http://www.gnu.org/licenses/>.
    
    @author: mkaay
"""

SERVER_VERSION = "0.4.4"

from time import sleep
from uuid import uuid4 as uuid

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import socket

from module.remote.thriftbackend.ThriftClient import ThriftClient, WrongLogin, NoSSL, NoConnection
from thrift.Thrift import TException

class Connector(QObject):
    def __init__(self):
        QObject.__init__(self)
        self.mutex = QMutex()
        self.connectionID = None
        self.host = None
        self.port = None
        self.user = None
        self.password = None
        self.ssl = None
        self.running = True
        self.proxy = self.Dummy()
    
    def setConnectionData(self, host, port, user, password, ssl=False):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.ssl = ssl
    
    def connectProxy(self):
        try:
            client = ThriftClient(self.host, self.port, self.user, self.password)
        except WrongLogin:
            self.emit(SIGNAL("error_box"), "bad login credentials")
            return False
        except NoSSL:
            self.emit(SIGNAL("error_box"), "no ssl support")
            return False
        except NoConnection:
            self.emit(SIGNAL("connectionLost"))
            return False
        
        self.proxy = DispatchRPC(self.mutex, client)
        self.connect(self.proxy, SIGNAL("proxy_error"), self._proxyError)
        self.connect(self.proxy, SIGNAL("connectionLost"), self, SIGNAL("connectionLost"))
        
        server_version = self.proxy.getServerVersion()
        self.connectionID = uuid().hex
        
        if not server_version == SERVER_VERSION:
            self.emit(SIGNAL("error_box"), "server is version %s client accepts version %s" % (server_version, SERVER_VERSION))
            return False
        
        return True
    
    def _proxyError(self, func, e):
        """
            formats proxy error msg
        """
        msg = "proxy error in '%s':\n%s" % (func, e)
        print msg
        self.emit(SIGNAL("error_box"), msg)
    
    def __getattr__(self, attr):
        return getattr(self.proxy, attr)
    
    class Dummy(object):
        def __getattr__(self, attr):
            def dummy(*args, **kwargs):
                return None
            return dummy

class DispatchRPC(QObject):
    def __init__(self, mutex, server):
        QObject.__init__(self)
        self.mutex = mutex
        self.server = server
    
    def __getattr__(self, attr):
        self.mutex.lock()
        self.fname = attr
        f = self.Wrapper(getattr(self.server, attr), self.mutex, self)
        return f
    
    class Wrapper(object):
        def __init__(self, f, mutex, dispatcher):
            self.f = f
            self.mutex = mutex
            self.dispatcher = dispatcher
        
        def __call__(self, *args, **kwargs):
            lost = False
            error = False
            try:
                return self.f(*args, **kwargs)
            except socket.error:
                lost = True
            except TException:
                lost = True
            except Exception, e:
                err = e
            finally:
                self.mutex.unlock()
            if lost:
                self.dispatcher.emit(SIGNAL("connectionLost"))
            if error:
                self.dispatcher.emit(SIGNAL("proxy_error"), self.dispatcher.fname, error)
