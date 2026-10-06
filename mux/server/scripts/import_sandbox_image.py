"""Imports the starter image (infra/sandbox-image) into Token Factory Sandboxes, once per new image version.

Push the image to a registry the sandbox service can pull from first, e.g.:
    cd mux && docker build -f infra/sandbox-image/Dockerfile -t ghcr.io/<you>/mux-starter:1 . \
        && docker push ghcr.io/<you>/mux-starter:1

Then, from mux/server (SANDBOX_API_KEY and SANDBOX_BASE_URL in .env):
    .venv/bin/python -m scripts.import_sandbox_image ghcr.io/<you>/mux-starter:1 [--tag mux-starter]
    [--username <user> --password <token>]   # for a private registry

It prints the line to put in .env: SANDBOX_IMAGE=<uuid>.
"""

import argparse
import asyncio

from contree_sdk import Contree

from mux.config import settings


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ref", help="OCI reference of the pushed image, e.g. ghcr.io/you/mux-starter:1")
    parser.add_argument("--tag", default=None, help="tag to give the image in the sandbox service")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    if not settings.sandbox_api_key or not settings.sandbox_base_url:
        raise SystemExit("Set SANDBOX_API_KEY and SANDBOX_BASE_URL in mux/server/.env first")

    sdk = Contree(base_url=settings.sandbox_base_url, token=settings.sandbox_api_key)
    image = await sdk.images.oci(
        args.ref, tag=args.tag, username=args.username, password=args.password, timeout=args.timeout
    )
    print(f"Imported {args.ref} (tag {image.tag or '-'})")
    print(f"SANDBOX_IMAGE={image.uuid}")


if __name__ == "__main__":
    asyncio.run(main())
