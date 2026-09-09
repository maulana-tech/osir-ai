"""Run a loop from your laptop, once or on a timer, or serve console commands.

python run_local.py inbox --dry-run
python run_local.py calendar
python run_local.py all --every 900      # inbox + calendar every 15 minutes
python run_local.py digest
python run_local.py command "Plan next week for the LinkedIn page"
python run_local.py worker               # execute commands queued from the Osir Console
"""

from __future__ import annotations

import argparse
import json
import logging
import time

from osir_agent.loops import run_all, run_task, work_pending


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("task", choices=["inbox", "calendar", "digest", "all", "command", "worker"])
    p.add_argument("instruction", nargs="?", help="what to do (command task only)")
    p.add_argument("--dry-run", action="store_true", help="hide write tools; observe and report only")
    p.add_argument("--every", type=int, metavar="SECONDS", help="repeat forever at this interval")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.task == "worker":
        work_pending(poll_seconds=args.every or 10)
        return

    while True:
        dry_run = args.dry_run or None
        if args.task == "all":
            reports = [r.model_dump() for r in run_all(dry_run=dry_run)]
        else:
            reports = [run_task(args.task, instruction=args.instruction, dry_run=dry_run).model_dump()]
        print(json.dumps(reports, indent=2))
        if not args.every:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
