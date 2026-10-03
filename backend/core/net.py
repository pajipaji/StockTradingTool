import socket

_ORIGINAL = None
_APPLIED = False


def force_ipv4() -> bool:
    """只解析 IPv4，规避东财 IPv6 出口被 RST。幂等。"""
    global _ORIGINAL, _APPLIED
    if _APPLIED:
        return False
    _ORIGINAL = socket.getaddrinfo

    def _ipv4_only(host, *args, **kwargs):
        results = _ORIGINAL(host, *args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results

    socket.getaddrinfo = _ipv4_only
    _APPLIED = True
    return True
