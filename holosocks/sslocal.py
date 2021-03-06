#!/usr/bin/env python3

import argparse
import asyncio
import functools
import json
import logging
import socket
import struct

try:
    from .encrypt import aes_cfb
except ModuleNotFoundError:  # develop mode
    from encrypt import aes_cfb

logging.basicConfig(
    level=logging.INFO,
    format='{asctime} {levelname} {message}',
    datefmt='%Y-%m-%d %H:%M:%S',
    style='{')


class Server:
    S2R, R2S = range(2)

    def __init__(self, server, server_port, key):
        self.server = server
        self.server_port = server_port
        self.key = key

    async def handle(self, reader, writer):
        logging.debug(
            'connect from {}'.format(writer.get_extra_info('peername')))
        request = await reader.read(2)
        if request[0] != 5:
            writer.close()
            logging.error('socks version not support')
            return None
        else:
            nmethods = request[1]
            logging.debug('methods number: {}'.format(nmethods))
            methods = await reader.read(nmethods)
            if 0 in methods:
                writer.write(b'\x05\x00')
                await writer.drain()
            else:
                writer.write(b'\x05\xff')
                logging.error('Authentication not support')
                writer.close()
                return None

        data = await reader.read(4)
        ver, cmd, rsv, atyp = data
        if cmd != 1:
            data = []
            data.append(b'\x05\x07\x00\x01')
            data.append(socket.inet_aton('0.0.0.0'))
            data.append(struct.pack('>H', 0))
            writer.write(b''.join(data))
            writer.close()
            logging.error('cmd not support')
            return None
        else:
            if atyp == 1:
                _addr = await reader.read(4)
                addr = socket.inet_ntoa(_addr).encode()

            elif atyp == 3:
                addr_len = await reader.read(1)
                addr = await reader.read(ord(addr_len))

            elif atyp == 4:
                _addr = await reader.read(16)
                addr = socket.inet_ntop(socket.AF_INET6, _addr).encode()

            else:
                response = [
                    b'\x05\x08\x00\x01',
                    socket.inet_aton('0.0.0.0'),
                    struct.pack('>H', 0)
                ]
                writer.write(b''.join(response))
                writer.close()
                return None

            _port = await reader.read(2)
            port = struct.unpack('>H', _port)[0]
            logging.debug('remote: {}:{}'.format(addr, port))

            target = [struct.pack('>B', len(addr)), addr, _port]
            target = b''.join(target)

            try:
                r_reader, r_writer = await asyncio.open_connection(
                    self.server, self.server_port)

            except OSError as e:
                logging.error(e)
                writer.close()
                return None

            except ConnectionError as e:
                logging.error(e)
                writer.close()
                return None

            except TimeoutError as e:
                logging.error(e)
                writer.close()
                return None

            if atyp != 4:
                data = [
                    b'\x05\x00\x00\x01',
                    socket.inet_aton('0.0.0.0'),
                    struct.pack('>H', 0)
                ]
                writer.write(b''.join(data))
                await writer.drain()

            else:
                data = [
                    b'\x05\x00\x00\x04',
                    socket.inet_pton(socket.AF_INET6, '::'),
                    struct.pack('>H', 0)
                ]
                writer.write(b''.join(data))
                await writer.drain()

            Encrypt = aes_cfb(self.key)
            iv = Encrypt.iv
            Decrypt = aes_cfb(self.key, iv)

            r_writer.write(iv)
            r_writer.write(Encrypt.encrypt(target))
            await r_writer.drain()

            logging.debug('start relay')

            s2r = asyncio.ensure_future(
                self.relay(reader, r_writer, Encrypt, self.S2R))

            r2s = asyncio.ensure_future(
                self.relay(r_reader, writer, Decrypt, self.R2S))

            s2r.add_done_callback(
                functools.partial(self.close_transport, writer, r_writer))

            r2s.add_done_callback(
                functools.partial(self.close_transport, writer, r_writer))

    async def relay(self, reader, writer, cipher, mode):
        while True:
            try:
                data = await reader.read(8192)

                if not data:
                    break

                else:
                    if mode == self.S2R:
                        writer.write(cipher.encrypt(data))
                    elif mode == self.R2S:
                        writer.write(cipher.decrypt(data))

                    await writer.drain()

            except OSError as e:
                logging.error(e)
                break

            except ConnectionError as e:
                logging.error(e)
                break

            except TimeoutError as e:
                logging.error(e)
                break

    def close_transport(self, writer, r_writer, future):
        writer.close()
        r_writer.close()


def main():
    #logging.info('start shadowsocks local')
    parser = argparse.ArgumentParser(description='holosocks local')
    parser.add_argument('-c', '--config', help='config file')
    args = parser.parse_args()
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)

    SERVER = config['server']
    SERVER_PORT = config['server_port']
    LOCAL = config['local']
    PORT = config['local_port']
    KEY = config['password']

    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logging.info('use uvloop event loop instead of asyncio event loop')
    except ImportError:
        logging.info('not found uvloop, use asyncio event lopp')
        pass

    server = Server(SERVER, SERVER_PORT, KEY)
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(server.handle, LOCAL, PORT, loop=loop)
    server = loop.run_until_complete(coro)

    try:
        loop.run_forever()

    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()


if __name__ == '__main__':
    main()
