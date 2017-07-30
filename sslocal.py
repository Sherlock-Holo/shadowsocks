#!/usr/bin/env python3

import argparse
import json
import logging
import select
import socket
import struct
from socketserver import StreamRequestHandler, ThreadingTCPServer

from encrypt import aes_cfb


SOCSK_VERSION = 5    # use socks5
SOCKS_AUTHENTICATION = 0    # no Authentication
SOCKS_MODE = 1    # mode: connection


class Socks5Server(StreamRequestHandler):
    def encrypt(self, data):    # encrypt data
        return self._encrypt.encrypt(data)

    def decrypt(self, data):    # decrypt data
        return self._decrypt.decrypt(data)

    def tcp_relay(self, sock, remote):    # relay data
        fdset = [sock, remote]
        logging.info('start relay')
        while True:
            r, w, e = select.select(fdset, [], [])
            logging.info(r)
            if sock in r:
                if remote.send(self.encrypt(sock.recv(4096))) <= 0:
                    break

            if remote in r:
                if sock.send(self.decrypt(remote.recv(4096))) <= 0:
                    break

    def handle(self):
        try:
            sock = self.connection
            client_ask = self.rfile.read(3)
            logging.info('socks5 ask from: {}:{}'.format(
                self.client_address[0], self.client_address[1]))

            if client_ask[0] == SOCSK_VERSION:    # check client socks version
                if client_ask[-1] == SOCKS_AUTHENTICATION:    # check client auth
                    self.wfile.write(b'\x05\x00')

                else:
                    logging.warn('socks Authentication error')
                    return None    # SOCKS_AUTHENTICATION error
            else:
                logging.warn('socks version error')
                return None    # SOCSK_VERSION error

            data = self.rfile.read(4)    # request format: VER CMD RSV ATYP (4 bytes)

            if not data[1] == SOCKS_MODE:   # only support CMD mode: connect
                data = b'\x05\x07\x00\x01' + socket.inet_aton('0.0.0.0') + struct.pack('>H', 0)
                self.wfile.write(data)
                logging.warn('not support CMD mode')
                return None

            addr_type = data[3]
            logging.info('addr type: {}'.format(addr_type))
            data_to_send = struct.pack('>B', addr_type)

            if addr_type == 1:
                addr_ip = self.rfile.read(4)    # addr ip (4 bytes)
                # addr = socket.inet_ntoa(addr_ip)    # deprecated
                data_to_send += addr_ip

            elif addr_type == 3:
                addr_len = self.rfile.read(1)
                data_to_send += addr_len
                addr = self.rfile.read(ord(addr_len))
                data_to_send += addr

            else:
                logging.warn('addr_type not support')    # addr type not support
                return None

            addr_port = self.rfile.read(2)
            data_to_send += addr_port

            reply = b'\x05\x00\x00\x01'    # VER REP RSV ATYP
            reply += socket.inet_aton('0.0.0.0') + struct.pack('>H', 3389)    # bind info
            self.wfile.write(reply)    # resonse packet

            self._encrypt = aes_cfb(KEY)    # instantiate encrypt class
            self._encrypt.new()
            self._decrypt = aes_cfb(KEY)
            self._decrypt.new(self._encrypt.iv)

            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            remote.connect((SERVER, SERVER_PORT))    # connect to shadowsocks server
            logging.info('shadowsocks server {}:{}'.format(remote.getpeername()[0], remote.getpeername()[1]))
            remote.send(self._encrypt.iv)    # send iv
            remote.send(self.encrypt(data_to_send))
            self.tcp_relay(sock, remote)    # start relay

        except socket.error as e:
            logging.warn(e)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='{asctime} {levelname} {message}',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        style='{')

    parser = argparse.ArgumentParser(description='shadowsocks local')
    parser.add_argument('-c', '--config', help='config file')
    args = parser.parse_args()
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)

    SERVER = config['server']
    SERVER_PORT = config['server_port']
    PORT = config['local_port']
    KEY = config['password']

    with ThreadingTCPServer(('127.0.0.2', PORT), Socks5Server) as server:
        server.allow_reuse_address = True
        server.serve_forever()
