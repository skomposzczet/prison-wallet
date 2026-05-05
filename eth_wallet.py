"""
Ethereum wallet — Sepolia testnet.

Mirrors the interface of the BTC `Wallet` class used by gui.py:
    - generate_new(password, output_dir)  -> (private_key_hex, address)
    - import_from_key(password, private_key_hex, output_dir) -> (private_key_hex, address)
    - load_user_keys(password, wallet_dir)
    - transfer_to(target_addr, transfer_amount_wei) -> (tx_hash, fee_wei)
    - fetch_tx_history() -> list[dict]
    - estimate_fee(transfer_amount_wei) -> fee_wei
    - .user_addr  str
    - .wei        int   (balance in wei)
    - .eth        float (balance in ETH, convenience)
"""

import os
import secrets
import json
from typing import Optional

import requests
from eth_account import Account
from eth_account.signers.local import LocalAccount

from src.keys_handler import load_file, save_file

# ── Network ──────────────────────────────────────────────────────────────────
# Sepolia testnet — multiple public RPC endpoints tried in order so that if
# one goes offline the wallet still works.
ETHERSCAN_BASE = "https://api-sepolia.etherscan.io/api"

RPC_URLS = [
    "https://ethereum-sepolia-rpc.publicnode.com",   # PublicNode  (no key)
    "https://rpc.ankr.com/eth_sepolia",              # Ankr        (no key)
    "https://sepolia.drpc.org",                      # dRPC        (no key)
    "https://rpc2.sepolia.org",                      # EF backup
]

WEI_PER_ETH = 10 ** 18


# ── helpers ───────────────────────────────────────────────────────────────────

def _rpc(method: str, params: list) -> dict:
    """Call an Ethereum JSON-RPC method, trying each endpoint until one works."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last_error: Exception = Exception("No RPC endpoints configured.")
    for url in RPC_URLS:
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise Exception(f"RPC error from {url}: {data['error']}")
            return data["result"]
        except Exception as e:
            print(f"RPC endpoint failed ({url}): {e}")
            last_error = e
    raise Exception(f"All RPC endpoints failed. Last error: {last_error}")


def wei_to_eth(wei: int) -> float:
    return wei / WEI_PER_ETH


def eth_to_wei(eth: float) -> int:
    return int(eth * WEI_PER_ETH)


# ── Wallet ────────────────────────────────────────────────────────────────────

class EthWallet:
    """Ethereum wallet for the Sepolia testnet."""

    def __init__(self):
        self.user_addr: Optional[str] = None
        self._account: Optional[LocalAccount] = None
        self.wei: int = 0

    # ── convenience ──────────────────────────────────────────────────────────

    @property
    def eth(self) -> float:
        return wei_to_eth(self.wei)

    # ── static factory methods ───────────────────────────────────────────────

    @staticmethod
    def generate_new(password: str, output_dir: str):
        """Generate a brand-new Ethereum keypair and persist it encrypted."""
        os.makedirs(output_dir, exist_ok=True)

        private_key_bytes = secrets.token_bytes(32)
        private_key_hex = private_key_bytes.hex()

        account: LocalAccount = Account.from_key(private_key_hex)
        address = account.address  # EIP-55 checksum address

        save_file(filename=os.path.join(output_dir, "priv_key.txt"),
                  message=private_key_hex, password=password)
        save_file(filename=os.path.join(output_dir, "pub_addr.txt"),
                  message=address, password=password)

        print("Generated ETH wallet:")
        print(f"  address: {address}")
        return private_key_hex, address

    @staticmethod
    def import_from_key(password: str, private_key_hex: str, output_dir: str):
        """Import an existing private key and persist it encrypted."""
        os.makedirs(output_dir, exist_ok=True)

        # Strip leading 0x if present
        private_key_hex = private_key_hex.strip().removeprefix("0x")
        if len(private_key_hex) != 64:
            raise ValueError("Private key must be 32 bytes (64 hex chars).")

        account: LocalAccount = Account.from_key(private_key_hex)
        address = account.address

        save_file(filename=os.path.join(output_dir, "priv_key.txt"),
                  message=private_key_hex, password=password)
        save_file(filename=os.path.join(output_dir, "pub_addr.txt"),
                  message=address, password=password)

        print("Imported ETH wallet:")
        print(f"  address: {address}")
        return private_key_hex, address

    # ── instance methods ─────────────────────────────────────────────────────

    def load_user_keys(self, password: str, wallet_dir: str):
        """Decrypt and load keys, then fetch the current balance."""
        priv_hex = load_file(filename=os.path.join(wallet_dir, "priv_key.txt"),
                             password=password)
        address = load_file(filename=os.path.join(wallet_dir, "pub_addr.txt"),
                            password=password)

        for val, name in ((priv_hex, "private key"), (address, "address")):
            if not val or val.startswith("Wrong password"):
                raise Exception(f"Incorrect password or corrupted wallet file ({name}).")

        self._account = Account.from_key(priv_hex)
        self.user_addr = address

        print(f"Loaded ETH wallet: {self.user_addr}")
        self._fetch_balance()

    def _fetch_balance(self):
        """Query the Sepolia RPC for the current balance in wei."""
        result = _rpc("eth_getBalance", [self.user_addr, "latest"])
        self.wei = int(result, 16)
        print(f"Balance: {self.wei} wei  ({self.eth:.6f} ETH)")

    # ── fee estimation ────────────────────────────────────────────────────────

    def _get_gas_price(self) -> int:
        """Return current gas price in wei."""
        result = _rpc("eth_gasPrice", [])
        return int(result, 16)

    def _estimate_transfer_fee(self) -> int:
        """Simple ETH transfer always costs 21 000 gas."""
        gas_limit = 21_000
        gas_price = self._get_gas_price()
        return gas_limit * gas_price

    def estimate_fee(self, transfer_amount_wei: int = 0) -> int:
        """Return estimated fee in wei (transfer_amount_wei is unused for ETH)."""
        return self._estimate_transfer_fee()

    # ── transfer ──────────────────────────────────────────────────────────────

    def transfer_to(self, target_addr: str, transfer_amount_wei: int):
        """
        Sign and broadcast a simple ETH transfer on Sepolia.

        Parameters
        ----------
        target_addr : str
            Destination Ethereum address (0x…).
        transfer_amount_wei : int
            Amount to send in wei.

        Returns
        -------
        (tx_hash, fee_wei) : (str | None, int)
        """
        if self._account is None or self.user_addr is None:
            raise Exception("Wallet is not loaded.")

        fee = self._estimate_transfer_fee()
        if self.wei < transfer_amount_wei + fee:
            raise Exception(
                f"Insufficient funds.\n"
                f"  Balance : {self.wei} wei\n"
                f"  Needed  : {transfer_amount_wei + fee} wei (amount + fee)"
            )

        # Build transaction
        nonce_hex = _rpc("eth_getTransactionCount", [self.user_addr, "latest"])
        nonce = int(nonce_hex, 16)

        chain_id_hex = _rpc("eth_chainId", [])
        chain_id = int(chain_id_hex, 16)  # 11155111 for Sepolia

        gas_price = self._get_gas_price()

        tx = {
            "nonce": nonce,
            "to": target_addr,
            "value": transfer_amount_wei,
            "gas": 21_000,
            "gasPrice": gas_price,
            "chainId": chain_id,
        }

        signed = self._account.sign_transaction(tx)
        raw_tx = signed.raw_transaction.hex()
        print(f"Signed transaction (raw): {raw_tx[:60]}…")

        # Broadcast
        try:
            result = _rpc("eth_sendRawTransaction", [f"0x{raw_tx}"])
            tx_hash = result
            print(f"SUCCESS — TX hash: {tx_hash}")
            print(f"View: https://sepolia.etherscan.io/tx/{tx_hash}")
            return tx_hash, fee
        except Exception as e:
            print(f"Broadcast failed: {e}")
            return None, fee

    # ── transaction history ───────────────────────────────────────────────────

    def fetch_tx_history(self) -> list[dict]:
        """
        Fetch transaction history from Etherscan Sepolia API.

        Returns a list of dicts matching the BTC wallet's format:
            txid, type ("incoming"/"outgoing"), amount (wei), fee (wei|None), confirmed (bool)
        """
        if not self.user_addr:
            return []

        params = {
            "module": "account",
            "action": "txlist",
            "address": self.user_addr,
            "startblock": 0,
            "endblock": 99999999,
            "sort": "desc",
        }

        try:
            resp = requests.get(ETHERSCAN_BASE, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Failed to fetch tx history: {e}")
            return []

        if data.get("status") != "1":
            # status "0" can mean "no transactions" or a real error
            msg = data.get("message", "")
            if "No transactions found" in msg:
                return []
            print(f"Etherscan error: {msg}")
            return []

        result = []
        addr_lower = self.user_addr.lower()

        for tx in data.get("result", []):
            txid = tx.get("hash", "?")
            confirmed = int(tx.get("confirmations", 0)) > 0
            value_wei = int(tx.get("value", 0))
            gas_used = int(tx.get("gasUsed", 0))
            gas_price = int(tx.get("gasPrice", 0))
            fee_wei = gas_used * gas_price

            is_outgoing = tx.get("from", "").lower() == addr_lower
            tx_type = "outgoing" if is_outgoing else "incoming"

            result.append({
                "txid": txid,
                "type": tx_type,
                "amount": value_wei,
                "fee": fee_wei if is_outgoing else None,
                "confirmed": confirmed,
            })

        print(f"Fetched {len(result)} ETH transactions for {self.user_addr}")
        return result
