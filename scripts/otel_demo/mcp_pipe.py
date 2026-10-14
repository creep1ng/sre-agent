"""Opaque socket transport. No credentials, HTTP parsing, logging, or public port."""

import argparse
import socket
import socketserver
import threading


def copy(source, destination):
    try:
        while data := source.recv(65536):
            destination.sendall(data)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class Pipe(socketserver.BaseRequestHandler):
    def handle(self):
        if isinstance(self.server, UnixPipe):
            upstream = socket.create_connection(("127.0.0.1", self.server.port), timeout=30)
        else:
            upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            upstream.connect(self.server.path)
        self.request.settimeout(120)
        upstream.settimeout(120)
        with upstream:
            worker = threading.Thread(target=copy, args=(self.request, upstream), daemon=True)
            worker.start()
            copy(upstream, self.request)
            worker.join(timeout=121)


class Quiet:
    daemon_threads = True

    def handle_error(self, *_args):
        pass


class UnixPipe(Quiet, socketserver.ThreadingUnixStreamServer):
    pass


class TcpPipe(Quiet, socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    with TcpPipe(("0.0.0.0", 8000), Pipe) as server:
        server.path = args.socket
        server.serve_forever()


if __name__ == "__main__":
    main()
