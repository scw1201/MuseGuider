#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml


API_ENDPOINT = "https://open.volcengineapi.com/"


def build_basic_token(ak: str, sk: str) -> str:
    raw = f"{ak}:{sk}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query Volcengine account balance.")
    parser.add_argument("--ak", help="AccessKey (for Basic token building)")
    parser.add_argument("--sk", help="SecretKey (for Basic token building)")
    parser.add_argument(
        "--basic",
        help="Authorization Basic token (Base64 of AK:SK)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response",
    )
    return parser.parse_args()


def resolve_basic_token(args: argparse.Namespace) -> str:
    if args.basic:
        return args.basic

    if args.ak and args.sk:
        return build_basic_token(args.ak, args.sk)

    secrets_path = Path(__file__).parents[1] / "configs" / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = yaml.safe_load(f) or {}
        billing = secrets.get("billing", {})
        if billing.get("basic"):
            return billing["basic"]
        if billing.get("access_key") and billing.get("secret_key"):
            return build_basic_token(billing["access_key"], billing["secret_key"])

    ak = os.getenv("VOLC_ACCESS_KEY")
    sk = os.getenv("VOLC_SECRET_KEY")
    if ak and sk:
        return build_basic_token(ak, sk)

    env_basic = os.getenv("VOLC_BILLING_BASIC")
    if env_basic:
        return env_basic

    raise RuntimeError(
        "Missing credentials. Provide --basic or --ak/--sk or set "
        "billing in secrets.yaml or VOLC_BILLING_BASIC or VOLC_ACCESS_KEY/VOLC_SECRET_KEY."
    )


def main() -> int:
    args = parse_args()
    try:
        basic = resolve_basic_token(args)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    params = {
        "Action": "QueryBalanceAcct",
        "Version": "2022-01-01",
    }
    url = API_ENDPOINT + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {basic}",
        },
        method="GET",
    )

    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")

    if args.pretty:
        data = json.loads(body)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(body)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
