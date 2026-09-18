"""Opt-in network deny guard for isolated engineering verification only."""
import os
import socket

if os.environ.get('AURALIS_TEST_OFFLINE') == '1':
    _connect = socket.socket.connect
    _connect_ex = socket.socket.connect_ex

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError('Offline verification forbids network connections')
        return _connect(self, address)

    def guarded_connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise RuntimeError('Offline verification forbids network connections')
        return _connect_ex(self, address)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
