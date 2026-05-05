import argparse
import sys

import requests
from eth_abi import decode, encode
from eth_utils import keccak

from eth_wallet import RPC_URLS


def rpc_call(method: str, params: list, rpc_urls: list[str]) -> str:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_error: Exception = Exception("No RPC endpoints configured.")

    for url in rpc_urls:
        try:
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise Exception(data["error"])
            return data["result"]
        except Exception as e:
            print(f"RPC endpoint failed ({url}): {e}", file=sys.stderr)
            last_error = e

    raise Exception(f"All RPC endpoints failed. Last error: {last_error}")


def call_greet(contract_address: str, name: str = "test", rpc_url: str | None = None) -> str:
    if not contract_address.startswith("0x") or len(contract_address) != 42:
        raise ValueError("Contract address must start with 0x and have 42 characters.")

    function_selector = keccak(text="greet(string)")[:4]
    encoded_args = encode(["string"], [name])
    call_data = "0x" + (function_selector + encoded_args).hex()

    rpc_urls = [rpc_url] if rpc_url else RPC_URLS
    result = rpc_call(
        "eth_call",
        [
            {
                "to": contract_address,
                "data": call_data,
            },
            "latest",
        ],
        rpc_urls,
    )

    if result == "0x":
        raise Exception("Contract returned empty data. Check address and greet(string) function.")

    return decode(["string"], bytes.fromhex(result.removeprefix("0x")))[0]


def main():
    parser = argparse.ArgumentParser(
        description='Call greet("test") on a deployed Sepolia smart contract.'
    )
    parser.add_argument("contract_address", help="Deployed contract address, e.g. 0x...")
    parser.add_argument("--name", default="test", help='Value passed to greet(string). Default: "test"')
    parser.add_argument("--rpc", default=None, help="Optional custom Sepolia RPC URL")
    args = parser.parse_args()

    greeting = call_greet(args.contract_address, name=args.name, rpc_url=args.rpc)
    print(greeting)


if __name__ == "__main__":
    main()
