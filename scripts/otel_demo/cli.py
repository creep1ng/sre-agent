from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta

from .aws import AwsCli
from .common import (
    EXPECTED_ACCOUNT_ENV,
    OPERATOR_PROFILE,
    OPERATOR_REGION,
    DemoConfig,
    DemoError,
)
from .controller import DemoController


def _duration(value: str) -> timedelta:
    try:
        hours = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("duration must be in hours") from exc
    if hours <= 0 or hours > 12:
        raise argparse.ArgumentTypeError("duration must be greater than zero and at most 12 hours")
    return timedelta(hours=hours)


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("up")
    sub.add_parser("status")
    extend = sub.add_parser("extend")
    extend.add_argument("--hours", type=_duration, default=timedelta(hours=1))
    connect = sub.add_parser("connect")
    connect.add_argument("--local-port", type=int, default=8090)
    connect.add_argument("--remote-port", type=int, default=8090)
    sub.add_parser("down")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    config = DemoConfig(
        profile=OPERATOR_PROFILE,
        region=OPERATOR_REGION,
        expected_account_id=os.environ.get(EXPECTED_ACCOUNT_ENV),
    )
    controller = DemoController(
        aws=AwsCli(profile=config.profile, region=config.region, config=config),
        config=config,
    )
    try:
        controller.aws.verify_identity()
        if args.action == "up":
            result = controller.up()
        elif args.action == "status":
            result = controller.status()
        elif args.action == "extend":
            result = {"expires_at": controller.extend(extension=args.hours).isoformat()}
        elif args.action == "connect":
            try:
                controller.connect(local_port=args.local_port, remote_port=args.remote_port)
            except KeyboardInterrupt:
                print("SSM port-forwarding session interrupted", file=sys.stderr)
                return 130
            return 0
        else:
            controller.down()
            return 0
    except DemoError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0
