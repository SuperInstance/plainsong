"""Whether an HTTP `Host` header names this machine.

Both local servers -- the web interface and the MCP HTTP transport -- refuse a
request whose `Host` is not a loopback name. That is the guard against DNS
rebinding, and comparing `Origin` against `Host` does not replace it: an
attacker points `evil.example` at 127.0.0.1, and a page served from that domain
sends both headers reading `evil.example`. They match perfectly. What gives the
attack away is that a rebound request always carries the attacker's hostname,
so the name itself is the thing to check.

This lived as two copies of the same eight lines, and both carried the same two
faults, because the copy was a copy:

- `[::1]:8765` and `[::1]` are both valid `Host` values for a loopback IPv6
  caller -- the second is what a client sends when the port is the default.
  Stripping the port with `rsplit(":", 1)` before removing the brackets turned
  the second into `":"`, which is not a loopback name, so a local caller was
  refused. The brackets are what separate an IPv6 address from its port; they
  have to be read first.

- `name.startswith("127.")` admits `127.evil.example`, which is a domain, is
  registrable, and can be pointed at 127.0.0.1 -- so the string test the guard
  used to recognise the 127/8 block also let the attack it exists to stop walk
  straight through. An address is parsed as an address now.

`is_loopback` on an IPv4-mapped IPv6 address answers differently across the
versions we support, so the mapping is undone here rather than left to it: a
security check must not depend on which interpreter is running.
"""

from __future__ import annotations

import ipaddress

LOOPBACK_NAMES = frozenset({"localhost", ""})


def hostname_of(host_header: str) -> str:
    """The host part of a `Host` header, lowercased, with any port removed.

    An IPv6 literal is bracketed (`[::1]:8765`) and the closing bracket, not
    the last colon, ends the address. An unbracketed value has at most one
    meaningful colon, before the port.
    """
    host = (host_header or "").strip()
    if host.startswith("["):
        return host[1:].split("]", 1)[0].lower()
    if ":" in host:
        return host.rsplit(":", 1)[0].lower()
    return host.lower()


def _address(name: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    return mapped if mapped is not None else address


def host_is_local(host_header: str) -> bool:
    """Whether `Host` names this machine rather than a domain that resolves to it.

    `0.0.0.0` counts, because a server bound to every interface is legitimately
    reached that way and the header is not the place to second-guess the bind.
    Whether the *bind* is safe is `bind_is_loopback`, a different question with
    a different answer.
    """
    name = hostname_of(host_header)
    if name in LOOPBACK_NAMES:
        return True
    address = _address(name)
    if address is None:
        return False  # a name, not an address, and only `localhost` is ours
    return address.is_loopback or address.is_unspecified


def bind_is_loopback(host: str) -> bool:
    """Whether binding a server to `host` keeps it on this machine.

    Both servers warn when it does not. Unlike `host_is_local`, `0.0.0.0` and
    `::` are emphatically *not* loopback here -- binding to every interface is
    precisely the case the warning exists for.

    This does not go through `hostname_of`, because a bind address is not a
    `Host` header: the port is a separate argument, so `::1` arrives bare and
    unbracketed and there is no port to strip. Stripping one anyway would read
    it as `":"` and warn about a loopback bind.
    """
    name = (host or "").strip()
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    name = name.lower()
    if name == "localhost":
        return True
    address = _address(name)
    return address is not None and address.is_loopback
