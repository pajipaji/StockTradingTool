import socket
import backend.core.net as net
from backend.core.net import force_ipv4


def test_force_ipv4_filters_ipv6(monkeypatch):
    monkeypatch.setattr(net, "_APPLIED", False)

    def fake(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert force_ipv4() is True
    assert force_ipv4() is False
    results = socket.getaddrinfo("example.com", 443)
    assert all(r[0] == socket.AF_INET for r in results)
