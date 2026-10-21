"""User-invoked local backup utility (no cloud or automatic restore)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.privacy.local_backup import create_backup, restore_to_empty_directory, verify_backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Karrierekrake local backup")
    parser.add_argument('--result-json', type=Path,
                        help='Write a fresh completion receipt (never overwrite an existing file).')
    actions = parser.add_subparsers(dest="action", required=True)
    backup = actions.add_parser("create")
    backup.add_argument("source", type=Path)
    backup.add_argument("archive", type=Path)
    verify = actions.add_parser("verify")
    verify.add_argument("archive", type=Path)
    restore = actions.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    if args.result_json is not None and args.result_json.exists():
        raise FileExistsError('backup_result_receipt_exists')
    if args.action == "create":
        archive_path = create_backup(args.source, args.archive)
        result = verify_backup(archive_path)
    elif args.action == "verify":
        result = verify_backup(args.archive)
    else:
        result = restore_to_empty_directory(args.archive, args.destination)
    payload = json.dumps({"status": "ok", **result}, sort_keys=True)
    if args.result_json is not None:
        with args.result_json.open('x', encoding='utf-8') as receipt:
            receipt.write(payload + '\n')
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
