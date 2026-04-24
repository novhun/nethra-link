"""
ip_discovery.py
---------------
Utility to discover the machine's primary LAN IP address using the socket library.
No external dependencies required.
"""

import socket


def get_local_ip() -> str:
    """
    Return the local machine's primary LAN IP address.

    The trick: we open a UDP socket to a well-known public address (8.8.8.8:80).
    No data is actually sent; we just need the OS to pick the right network
    interface and expose its bound address.

    Returns
    -------
    str
        The local IPv4 address string (e.g. '192.168.1.15').
        Falls back to '127.0.0.1' if discovery fails.
    """
    ip = "127.0.0.1"
    try:
        # Create a UDP socket (SOCK_DGRAM) – no connection is made.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Connect to an external host so the OS selects the correct interface.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except Exception:
        # If anything fails, fall back to loopback.
        pass
    return ip


if __name__ == "__main__":
    print(f"Detected local IP: {get_local_ip()}")
