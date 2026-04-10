#!/usr/bin/env python3

import argparse
import asyncio
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import run_drone


def main():
    parser = argparse.ArgumentParser(description="启动单架无人机实例")
    parser.add_argument("id", type=int, help="无人机编号（从 0 开始）")
    args = parser.parse_args()
    asyncio.run(run_drone(uav_id=args.id))


if __name__ == "__main__":
    main()
