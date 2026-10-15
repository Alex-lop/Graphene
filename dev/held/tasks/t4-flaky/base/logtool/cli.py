"""The log command: print a log file. A line is '<ISO timestamp> <message>'."""

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="logtool")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    with open(args.path, encoding="utf-8") as fh:
        for line in fh:
            sys.stdout.write(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
