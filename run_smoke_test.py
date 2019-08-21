import argparse
import os
import sys

from notion.smoke_test import run_live_smoke_test

if __name__ == "__main__":
    description = "Run notion-py client smoke tests"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--page", dest="page", help="page URL or ID", required=True, type=str
    )
    parser.add_argument("--token", dest="token", help="token_v2", type=str)
    args = parser.parse_args()

    token = args.token
    if not token:
        token = os.environ.get("NOTION_TOKEN")
    if not token:
        print(
            "Must either pass --token option or set NOTION_TOKEN environment variable"
        )
        sys.exit(1)

    run_live_smoke_test(token, args.page)
