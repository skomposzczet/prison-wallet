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
import subprocess
import tempfile
import time
from typing import Optional

import requests
from eth_account import Account
from eth_account.signers.local import LocalAccount

from src.keys_handler import load_file, save_file

# ── Network ──────────────────────────────────────────────────────────────────
# Sepolia testnet — multiple public RPC endpoints tried in order so that if
# one goes offline the wallet still works.

RPC_URLS = [
    "https://ethereum-sepolia-rpc.publicnode.com",   # PublicNode  (no key)
    "https://rpc.ankr.com/eth_sepolia",              # Ankr        (no key)
    "https://sepolia.drpc.org",                      # dRPC        (no key)
    "https://rpc2.sepolia.org",                      # EF backup
]

WEI_PER_ETH = 10 ** 18
DEFAULT_SOLC_VERSION = "0.8.30"
SOLC_BINARY_DOWNLOAD_BASE = "https://binaries.soliditylang.org/{}-amd64/{}"


def _solcx_install_dir() -> str:
    return os.path.join(os.getcwd(), ".prison-wallet", "solcx")


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


def fmt_wei(wei: int) -> str:
    """Format a wei amount in scientific notation, e.g. 1.234e+15 wei."""
    if wei == 0:
        return "0 wei"
    return f"{wei:.3e} wei"


def _int_or_zero(value) -> int:
    """Convert Blockscout numeric strings to int without failing on missing values."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _address_hash(value) -> str:
    """Extract an address hash from a Blockscout address object."""
    if isinstance(value, dict):
        return (value.get("hash") or "").lower()
    if isinstance(value, str):
        return value.lower()
    return ""


# ── Wallet ────────────────────────────────────────────────────────────────────

class EthWallet:
    """Ethereum wallet for the Sepolia testnet."""

    def __init__(self):
        self.user_addr: Optional[str] = None
        self._account: Optional[LocalAccount] = None
        self.wei: int = 0
        self.wallet_dir: Optional[str] = None

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
        self.wallet_dir = wallet_dir
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

    @staticmethod
    def _raw_transaction_hex(raw_transaction) -> str:
        raw_hex = raw_transaction.hex()
        return raw_hex if raw_hex.startswith("0x") else f"0x{raw_hex}"

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
        raw_tx = self._raw_transaction_hex(signed.raw_transaction)
        print(f"Signed transaction (raw): {raw_tx[:60]}…")

        # Broadcast
        try:
            result = _rpc("eth_sendRawTransaction", [raw_tx])
            tx_hash = result
            print(f"SUCCESS — TX hash: {tx_hash}")
            print(f"View: https://sepolia.etherscan.io/tx/{tx_hash}")
            return tx_hash, fee
        except Exception as e:
            print(f"Broadcast failed: {e}")
            return None, fee

    # ── transaction history ───────────────────────────────────────────────────

    def fetch_tx_history(self, limit: int = 50) -> list[dict]:
        """
        Fetch transaction history from the Blockscout REST API v2 (no API key needed).

        Endpoint: GET https://eth-sepolia.blockscout.com/api/v2/addresses/{addr}/transactions

        Returns a list of dicts matching the BTC wallet's format:
            txid, type ("incoming"/"outgoing"), amount (wei), fee (wei|None), confirmed (bool)
        """
        if not self.user_addr:
            return []

        base = "https://eth-sepolia.blockscout.com/api/v2"
        url = f"{base}/addresses/{self.user_addr}/transactions"
        params = {}

        result = []
        addr_lower = self.user_addr.lower()

        while url and len(result) < limit:
            try:
                resp = requests.get(url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                raise Exception(f"Blockscout API error: {e}") from e

            for tx in data.get("items", []):
                txid      = tx.get("hash", "?")
                status    = tx.get("status", "")          # "ok" | "error" | null (pending)
                confirmed = status in ("ok", "error")     # any mined tx is confirmed

                value_wei = _int_or_zero(tx.get("value"))

                fee = tx.get("fee")
                if isinstance(fee, dict):
                    fee_wei = _int_or_zero(fee.get("value"))
                else:
                    fee_wei = _int_or_zero(fee)

                if fee_wei == 0:
                    gas_used = _int_or_zero(tx.get("gas_used"))
                    gas_price = _int_or_zero(tx.get("gas_price"))
                    fee_wei = gas_used * gas_price

                tx_from = _address_hash(tx.get("from"))
                is_outgoing = tx_from == addr_lower
                tx_type = "outgoing" if is_outgoing else "incoming"

                result.append({
                    "txid":      txid,
                    "type":      tx_type,
                    "amount":    value_wei,
                    "fee":       fee_wei if is_outgoing else None,
                    "confirmed": confirmed,
                })

                if len(result) >= limit:
                    break

            # Blockscout v2 paginates via next_page_params
            next_params = data.get("next_page_params")
            if next_params and len(result) < limit:
                url    = f"{base}/addresses/{self.user_addr}/transactions"
                params = next_params
            else:
                url = None

        print(f"Fetched {len(result)} ETH transaction(s) for {self.user_addr}")
        return result

    # ── smart contracts ──────────────────────────────────────────────────────

    @staticmethod
    def _compile_solidity(sol_source: str) -> tuple[str, list, str]:
        """
        Compile a Solidity source string with solc.

        Returns (contract_name, abi, bytecode). The first contract reported by
        the compiler is used, mirroring the simple one-file workflow from
        create_contract.py.
        """
        if not sol_source.strip():
            raise ValueError("Solidity source cannot be empty.")

        with tempfile.TemporaryDirectory() as tmpdir:
            sol_path = os.path.join(tmpdir, "Contract.sol")
            with open(sol_path, "w", encoding="utf-8") as f:
                f.write(sol_source)

            try:
                result = subprocess.run(
                    ["solc", "--combined-json", "abi,bin", sol_path],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except FileNotFoundError:
                return EthWallet._compile_solidity_with_solcx(sol_source)
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.strip() or e.stdout.strip()
                raise Exception(f"Solidity compilation failed:\n{stderr}") from e

        contracts = json.loads(result.stdout).get("contracts", {})
        if not contracts:
            return EthWallet._compile_solidity_with_solcx(sol_source)

        contract_key, data = next(iter(contracts.items()))
        contract_name = contract_key.rsplit(":", 1)[-1]
        abi = data["abi"]
        bytecode = data["bin"]
        if not bytecode:
            raise Exception(f"Contract {contract_name} has no deployable bytecode.")

        return contract_name, abi, bytecode

    @staticmethod
    def _compile_solidity_with_solcx(sol_source: str) -> tuple[str, list, str]:
        try:
            import solcx
            import solcx.install
        except ImportError as e:
            raise Exception(
                "solc is not installed and Python package py-solc-x is missing. "
                "Install dependencies again, e.g. `uv sync` or `pip install py-solc-x`."
            ) from e

        try:
            solcx.install.BINARY_DOWNLOAD_BASE = SOLC_BINARY_DOWNLOAD_BASE
            solcx_dir = _solcx_install_dir()
            os.makedirs(solcx_dir, exist_ok=True)
            installed_versions = {
                str(version)
                for version in solcx.get_installed_solc_versions(solcx_binary_path=solcx_dir)
            }
            solc_binary = os.path.join(solcx_dir, f"solc-v{DEFAULT_SOLC_VERSION}")
            if DEFAULT_SOLC_VERSION not in installed_versions:
                try:
                    solcx.install_solc(DEFAULT_SOLC_VERSION, solcx_binary_path=solcx_dir)
                except Exception:
                    if not os.path.exists(solc_binary):
                        raise
            compiled = solcx.compile_source(
                sol_source,
                output_values=["abi", "bin"],
                solc_binary=solc_binary,
            )
        except requests.exceptions.RequestException as e:
            raise Exception(
                "Solidity compiler is not installed yet and automatic download failed. "
                f"Install solc {DEFAULT_SOLC_VERSION} or restore network access so py-solc-x "
                f"can download it from binaries.soliditylang.org into {_solcx_install_dir()}.\n{e}"
            ) from e
        except Exception as e:
            raise Exception(f"Solidity compilation failed:\n{e}") from e

        contracts = compiled or {}
        if not contracts:
            raise Exception("solc did not return any compiled contracts.")

        contract_key, data = next(iter(contracts.items()))
        contract_name = contract_key.rsplit(":", 1)[-1]
        abi = data["abi"]
        bytecode = data["bin"]
        if not bytecode:
            raise Exception(f"Contract {contract_name} has no deployable bytecode.")

        return contract_name, abi, bytecode

    def estimate_contract_deploy_fee(self, sol_source: str) -> tuple[int, int, str, list, str]:
        """
        Compile Solidity and estimate deployment fee.

        Returns (fee_wei, gas_limit, contract_name, abi, bytecode).
        """
        if self._account is None or self.user_addr is None:
            raise Exception("Wallet is not loaded.")

        contract_name, abi, bytecode = self._compile_solidity(sol_source)
        gas_price = self._get_gas_price()
        tx_for_estimate = {
            "from": self.user_addr,
            "data": f"0x{bytecode}",
            "value": "0x0",
        }
        gas_hex = _rpc("eth_estimateGas", [tx_for_estimate])
        gas_limit = int(int(gas_hex, 16) * 1.2)
        return gas_limit * gas_price, gas_limit, contract_name, abi, bytecode

    def deploy_contract(
        self,
        sol_source: str,
        contract_name: Optional[str] = None,
        abi: Optional[list] = None,
        bytecode: Optional[str] = None,
        gas_limit: Optional[int] = None,
    ) -> dict:
        """
        Deploy a no-argument Solidity contract to Sepolia using public RPC.

        The current implementation supports contracts without constructor
        parameters, matching the attached create_contract.py workflow.
        """
        if self._account is None or self.user_addr is None:
            raise Exception("Wallet is not loaded.")

        if contract_name is None or abi is None or bytecode is None:
            contract_name, abi, bytecode = self._compile_solidity(sol_source)

        gas_price = self._get_gas_price()
        if gas_limit is None:
            fee, gas_limit, _, _, _ = self.estimate_contract_deploy_fee(sol_source)
        else:
            fee = gas_limit * gas_price

        self._fetch_balance()
        if self.wei < fee:
            raise Exception(
                f"Insufficient funds for deployment fee.\n"
                f"  Balance : {self.wei} wei\n"
                f"  Needed  : {fee} wei"
            )

        nonce_hex = _rpc("eth_getTransactionCount", [self.user_addr, "pending"])
        chain_id_hex = _rpc("eth_chainId", [])

        tx = {
            "nonce": int(nonce_hex, 16),
            "value": 0,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": int(chain_id_hex, 16),
            "data": f"0x{bytecode}",
        }

        signed = self._account.sign_transaction(tx)
        raw_tx = self._raw_transaction_hex(signed.raw_transaction)
        tx_hash = _rpc("eth_sendRawTransaction", [raw_tx])
        print("--- ETH CONTRACT DEPLOYMENT ---")
        print(f"Contract: {contract_name}")
        print(f"Deployment TX: {tx_hash}")

        receipt = None
        deadline = time.time() + 180
        while time.time() < deadline:
            receipt = _rpc("eth_getTransactionReceipt", [tx_hash])
            if receipt:
                break
            time.sleep(5)

        if not receipt:
            raise Exception(f"Deployment transaction sent but not mined yet: {tx_hash}")
        if receipt.get("status") != "0x1":
            raise Exception(f"Deployment transaction failed: {tx_hash}")

        contract_address = receipt.get("contractAddress")
        if not contract_address:
            raise Exception(f"Deployment mined without contract address: {tx_hash}")

        gas_used = int(receipt.get("gasUsed", "0x0"), 16)
        fee_wei = gas_used * gas_price
        print(f"Contract Address: {contract_address}")
        print(f"Gas used: {gas_used}")
        print(f"Fee: {fee_wei} wei")
        print(f"View contract: https://sepolia.etherscan.io/address/{contract_address}")
        print(f"View transaction: https://sepolia.etherscan.io/tx/{tx_hash}")

        if self.wallet_dir:
            contracts_dir = os.path.join(self.wallet_dir, "contracts")
            os.makedirs(contracts_dir, exist_ok=True)
            safe_name = "".join(ch for ch in contract_name if ch.isalnum() or ch in "_-") or "Contract"
            artifact_path = os.path.join(contracts_dir, f"{contract_address}_{safe_name}_ABI.json")
            with open(artifact_path, "w", encoding="utf-8") as f:
                json.dump(abi, f, indent=2)
            print(f"ABI saved: {artifact_path}")

        self._fetch_balance()
        return {
            "contract_name": contract_name,
            "contract_address": contract_address,
            "tx_hash": tx_hash,
            "fee_wei": fee_wei,
            "gas_used": gas_used,
            "gas_limit": gas_limit,
            "abi": abi,
        }
