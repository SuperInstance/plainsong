"""The one loopback check both local servers use.

The guard itself is exercised over a real socket in `test_web.py` and
`test_mcp.py` -- that is where it is proved to actually refuse a rebound
request. This file is the parsing, which is where the bug was: the two servers
each carried their own copy of the same eight lines, and both got IPv6 wrong in
the same way, because the copy was a copy.
"""

from __future__ import annotations

import unittest

from plainsong.runtime.localhost import bind_is_loopback, host_is_local, hostname_of


class TestHostnameOf(unittest.TestCase):
    def test_a_port_is_removed(self):
        self.assertEqual(hostname_of("localhost:8765"), "localhost")

    def test_a_bare_name_survives(self):
        self.assertEqual(hostname_of("127.0.0.1"), "127.0.0.1")

    def test_a_bracketed_ipv6_with_a_port_loses_only_the_port(self):
        self.assertEqual(hostname_of("[::1]:8765"), "::1")

    def test_a_bracketed_ipv6_with_no_port_is_not_mangled(self):
        """The bug. `rsplit(":", 1)` before stripping brackets reads this as
        `":"`, so a loopback caller on the default port was refused."""
        self.assertEqual(hostname_of("[::1]"), "::1")

    def test_case_is_not_significant(self):
        self.assertEqual(hostname_of("LocalHost:80"), "localhost")

    def test_surrounding_whitespace_is_not_significant(self):
        self.assertEqual(hostname_of("  localhost:80 "), "localhost")

    def test_a_missing_header_is_the_empty_name(self):
        self.assertEqual(hostname_of(""), "")


class TestHostIsLocal(unittest.TestCase):
    def test_the_names_a_local_client_sends_are_local(self):
        for host in (
            "localhost",
            "localhost:8765",
            "127.0.0.1",
            "127.0.0.1:8765",
            "127.1.2.3",
            "[::1]",
            "[::1]:8765",
            "0.0.0.0:8765",
            "",
        ):
            with self.subTest(host=host):
                self.assertTrue(host_is_local(host))

    def test_a_domain_is_not_local_however_it_resolves(self):
        """This is the whole point: `evil.example` may well answer 127.0.0.1,
        and the Host header is what gives that away."""
        for host in (
            "evil.example",
            "evil.example:8765",
            "localhost.evil.example",
            "127.0.0.1.evil.example",
            "192.168.1.10:8765",
            "[::ffff:8.8.8.8]",
        ):
            with self.subTest(host=host):
                self.assertFalse(host_is_local(host))

    def test_a_domain_that_merely_opens_with_127_is_not_local(self):
        """The second fault in the copies. `startswith("127.")` was meant to
        admit the 127/8 block, but `127.evil.example` is a registrable domain
        that starts with those characters -- so the string test let the exact
        attack it exists to stop walk through. Parse the address."""
        for host in ("127.evil.example", "127.0.0.1.evil.example", "1270.0.0.1"):
            with self.subTest(host=host):
                self.assertFalse(host_is_local(host))

    def test_an_ipv4_mapped_loopback_is_local_on_every_supported_version(self):
        """`is_loopback` answers differently across 3.10-3.13 for a mapped
        address, so the mapping is undone before asking."""
        self.assertTrue(host_is_local("[::ffff:127.0.0.1]"))
        self.assertTrue(host_is_local("[::ffff:127.0.0.1]:8765"))

    def test_the_mapping_is_undone_rather_than_left_to_the_interpreter(self):
        """The assertion above cannot see this: on the interpreters where
        `IPv6Address.is_loopback` already follows a mapped address, removing
        the normalisation changes no answer, and a version where it does not
        is not the one running the test. So pin the normalisation itself --
        `::ffff:127.0.0.1` must come back as the IPv4 address it wraps, which
        is true on every version and does not ask `is_loopback` anything."""
        import ipaddress

        from plainsong.runtime.localhost import _address

        self.assertEqual(_address("::ffff:127.0.0.1"), ipaddress.IPv4Address("127.0.0.1"))
        self.assertEqual(_address("::ffff:8.8.8.8"), ipaddress.IPv4Address("8.8.8.8"))
        self.assertEqual(_address("::1"), ipaddress.IPv6Address("::1"))
        self.assertIsNone(_address("evil.example"))


class TestBindIsLoopback(unittest.TestCase):
    """A different question from `host_is_local`, and the difference is 0.0.0.0."""

    def test_the_loopback_binds_do_not_warn(self):
        for host in ("127.0.0.1", "localhost", "::1", "127.0.0.5"):
            with self.subTest(host=host):
                self.assertTrue(bind_is_loopback(host))

    def test_binding_to_every_interface_is_not_loopback(self):
        """`host_is_local("0.0.0.0")` is true and this is false, deliberately.
        A request may legitimately arrive addressed to 0.0.0.0; a server bound
        there is reachable by anyone who can route to the machine, which is
        exactly what the warning is for."""
        for host in ("0.0.0.0", "::", "[::]", ""):
            with self.subTest(host=host):
                self.assertFalse(bind_is_loopback(host))
        self.assertTrue(host_is_local("0.0.0.0"))
        self.assertTrue(host_is_local("[::]"))

    def test_a_bind_address_carries_no_port_so_bare_ipv6_is_read_whole(self):
        """`--host ::1` is how a person writes it; the port is a separate
        argument. Running that through the `Host` parser reads it as `":"`."""
        self.assertTrue(bind_is_loopback("::1"))
        self.assertTrue(bind_is_loopback("[::1]"))
        self.assertEqual(hostname_of("::1"), ":")  # which is why it is not used here

    def test_a_routable_bind_is_not_loopback(self):
        self.assertFalse(bind_is_loopback("192.168.1.10"))
        self.assertFalse(bind_is_loopback("0000:0000::0001".replace("0001", "beef")))


class TestThereIsOneCopy(unittest.TestCase):
    """Two copies drifted into the same two bugs. A third would too."""

    def test_no_module_matches_loopback_names_for_itself(self):
        from pathlib import Path

        package = Path(__file__).resolve().parent.parent / "plainsong"
        offenders = []
        for path in package.rglob("*.py"):
            if path.name == "localhost.py":
                continue
            text = path.read_text(encoding="utf-8")
            # A default bind address is fine -- that is configuration. Deciding
            # whether a name *is* loopback is what has to live in one place, and
            # both faults were in that decision.
            if 'startswith("127.' in text or '"localhost", "::1"' in text:
                offenders.append(str(path.relative_to(package)))
        self.assertEqual(offenders, [], f"these should call runtime.localhost instead: {offenders}")

    def test_both_servers_read_the_host_header_through_the_shared_check(self):
        from pathlib import Path

        package = Path(__file__).resolve().parent.parent / "plainsong"
        for relative in ("interfaces/web/server.py", "mcp/server.py"):
            with self.subTest(module=relative):
                text = (package / relative).read_text(encoding="utf-8")
                self.assertIn("from ", text)
                self.assertIn("localhost import", text)
                self.assertIn('host_is_local(self.headers.get("Host", ""))', text)


if __name__ == "__main__":
    unittest.main()
