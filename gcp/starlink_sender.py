import argparse
import json
import socket
import sys

DEFAULT_PRIMARY_ADDR = ("192.168.8.67", 57000)
DEFAULT_EXTRA_ADDRS = [("192.168.61.75", port) for port in range(57001, 57012)]


def _parse_addr(value):
    host, sep, port_str = value.rpartition(":")
    if not sep:
        raise ValueError(f"Address must be HOST:PORT, got: {value!r}")
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(f"Port must be an integer, got: {port_str!r}") from exc
    if not (0 < port < 65536):
        raise ValueError(f"Port out of range: {port}")
    return host, port


def _format_addr(addr):
    return f"{addr[0]}:{addr[1]}"


def _build_payload(lat, lon):
    return {"cmd": "target_location_starlink_sender", "location": [lat, lon]}


def _send_payload(payload, primary_addr, extra_addrs):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    count = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(data, primary_addr)
        count += 1
        for addr in extra_addrs:
            sock.sendto(data, addr)
            count += 1
    finally:
        sock.close()
    return count


def send_starlink_sim(lat, lon, primary_addr=DEFAULT_PRIMARY_ADDR, extra_addrs=None):
    if extra_addrs is None:
        extra_addrs = DEFAULT_EXTRA_ADDRS
    payload = _build_payload(lat, lon)
    return _send_payload(payload, primary_addr, extra_addrs)


def main():
    parser = argparse.ArgumentParser(
        description="Send a Starlink simulated target location to UAVs via UDP.",
    )
    parser.add_argument("--lat", type=float, required=True, help="Target latitude.")
    parser.add_argument("--lon", type=float, required=True, help="Target longitude.")
    parser.add_argument(
        "--target",
        default=_format_addr(DEFAULT_PRIMARY_ADDR),
        help="Primary command address as HOST:PORT.",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="Extra command address as HOST:PORT (repeatable).",
    )
    parser.add_argument(
        "--no-default-extra",
        action="store_true",
        help="Disable the default extra command addresses.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload and targets without sending.",
    )
    args = parser.parse_args()

    try:
        primary_addr = _parse_addr(args.target)
        extra_addrs = [] if args.no_default_extra else list(DEFAULT_EXTRA_ADDRS)
        if args.extra:
            extra_addrs.extend(_parse_addr(item) for item in args.extra)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    payload = _build_payload(args.lat, args.lon)
    targets = [primary_addr] + list(extra_addrs)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False))
        print("Targets:")
        for addr in targets:
            print(f"  - {_format_addr(addr)}")
        return 0

    count = _send_payload(payload, primary_addr, extra_addrs)
    print(f"Sent Starlink sim target to {count} address(es).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
