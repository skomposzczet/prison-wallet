import hashlib
import math
import os
import secrets
import time
from pprint import pformat
from typing import Literal

import base58
import ecdsa
import requests
from bitcoinutils.keys import P2pkhAddress, P2shAddress, P2wpkhAddress, PrivateKey
from bitcoinutils.script import Script
from bitcoinutils.setup import setup
from bitcoinutils.transactions import Transaction, TxInput, TxOutput
from dotenv import load_dotenv

from src.keys_handler import load_file, save_file

PRIORITY_LVL = {"high": 0, "low": -1}
API_BASE = "https://blockstream.info/testnet/api"

load_dotenv()
setup(network="testnet")


def hex_to_wif(hex_key: str) -> str:
    raw_key = bytes.fromhex(hex_key)
    prefix = b"\xef" + raw_key
    with_compression = prefix + b"\x01"
    first_sha = hashlib.sha256(with_compression).digest()
    second_sha = hashlib.sha256(first_sha).digest()
    checksum = second_sha[:4]
    final_binary = with_compression + checksum
    wif_string = base58.b58encode(final_binary).decode("utf-8")
    return wif_string


class Wallet:
    def __init__(self):
        self.user_wif: str | None = None
        self.user_addr: str | None = None
        self.satoshi = 0
        self.chunks = []

    @staticmethod
    def generate_new(password: str, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)

        private_key = secrets.token_bytes(32)
        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        public_key = vk.to_string("compressed")
        sha256_hash = hashlib.sha256(public_key).digest()
        ripemd160 = hashlib.new("ripemd160", sha256_hash).digest()
        network_byte = b"\x6f" + ripemd160
        checksum = hashlib.sha256(hashlib.sha256(network_byte).digest()).digest()[:4]
        address = base58.b58encode(network_byte + checksum)

        wallet_private_key = private_key.hex()
        wallet_wif = hex_to_wif(wallet_private_key)
        wallet_address = address.decode("utf-8")

        save_file(filename=os.path.join(output_dir, "priv_wif.txt"), message=wallet_wif, password=password)
        save_file(filename=os.path.join(output_dir, "pub_addr.txt"), message=wallet_address, password=password)

        return wallet_wif, wallet_address

    @staticmethod
    def import_from_wif(password: str, wif: str, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)

        wallet_priv = PrivateKey.from_wif(wif)
        wallet_pub = wallet_priv.get_public_key()
        wallet_address = wallet_pub.get_address().to_string()

        save_file(filename=os.path.join(output_dir, "priv_wif.txt"), message=wif, password=password)
        save_file(filename=os.path.join(output_dir, "pub_addr.txt"), message=wallet_address, password=password)

        return wif, wallet_address

    def _set_user_wif(self):
        assert isinstance(self.user_wif, str)
        self.user_priv = PrivateKey.from_wif(self.user_wif)
        self.user_pub = self.user_priv.get_public_key()
        self.user_addr = self.user_pub.get_address().to_string()

    def _fetch_wallet_state(self):
        account = requests.get(f"{API_BASE}/address/{self.user_addr}/utxo").json()
        account = sorted(account, key=lambda d: d["value"], reverse=True)
        for chunk in account:
            if chunk["status"]["confirmed"]:
                self.chunks.append(chunk)
                self.satoshi += chunk["value"]

    def load_user_keys(self, password: str, wallet_dir: str):
        self.user_wif = load_file(filename=os.path.join(wallet_dir, "priv_wif.txt"), password=password)
        self.user_addr = load_file(filename=os.path.join(wallet_dir, "pub_addr.txt"), password=password)

        if not self.user_wif or not self.user_addr or self.user_wif.startswith("Wrong password"):
            raise Exception("Incorrect password or corrupted wallet file.")

        self._set_user_wif()
        self.chunks = []
        self.satoshi = 0
        self._fetch_wallet_state()

    @staticmethod
    def _get_tx_fee_rate(transfer_priority: Literal["high", "low"] = "high") -> float:
        try:
            fee_rate_estimates = requests.get(f"{API_BASE}/fee-estimates").json()
        except requests.exceptions.ConnectionError as e:
            raise Exception("Failed to obtain fee rate estimates") from e

        fee_rate_sorted = sorted(fee_rate_estimates.items(), key=lambda item: item[1])
        priority_idx = PRIORITY_LVL[transfer_priority]
        return round(fee_rate_sorted[priority_idx][1], 4)

    @staticmethod
    def _estimate_tx_size(n_inputs: int, n_outputs: int = 2) -> float:
        return 10 + (148 * n_inputs) + (34 * n_outputs)

    def estimate_fee(self, transfer_amount: int, transfer_priority: Literal["high", "low"] = "high") -> int:
        _, _, fee = self._get_tx_chunks(transfer_amount=transfer_amount, transfer_priority=transfer_priority)
        return fee

    def _get_tx_chunks(self, transfer_amount: int, transfer_priority: Literal["high", "low"]) -> tuple[list, int, int]:
        if self.satoshi < transfer_amount:
            raise Exception("Not enough funds in wallet.")

        fee_rate = self._get_tx_fee_rate(transfer_priority=transfer_priority)
        tx_chunks = []

        for chunk in self.chunks:
            tx_chunks.append(chunk)
            tx_size = self._estimate_tx_size(len(tx_chunks))
            fee = math.ceil(tx_size * fee_rate)
            if ((available_amount := sum([c["value"] for c in tx_chunks])) + fee) > transfer_amount:
                change = math.ceil(available_amount - transfer_amount - fee)
                return tx_chunks, change, fee
        raise Exception("Cannot perform transaction with current fee rate.")

    @staticmethod
    def _address_to_hash160(address: str) -> bytes:
        decoded = base58.b58decode(address)
        return decoded[1:-4]

    @staticmethod
    def broadcast_transaction(raw_tx: str):
        url = f"{API_BASE}/tx"
        try:
            response = requests.post(url, data=raw_tx)
            return response.text if response.status_code == 200 else None
        except requests.exceptions.RequestException:
            return None

    def transfer_to(self, target_addr: str, transfer_amount: int):
        chunks, change, fee = self._get_tx_chunks(transfer_amount=transfer_amount, transfer_priority="high")
        tx_inputs = [TxInput(chunk["txid"], chunk["vout"]) for chunk in chunks]

        if target_addr.startswith("2"):
            target_script = P2shAddress(target_addr).to_script_pub_key()
        else:
            target_script = P2pkhAddress(target_addr).to_script_pub_key()

        tx_outputs = [
            TxOutput(transfer_amount, target_script),
            TxOutput(change, P2pkhAddress(self.user_addr).to_script_pub_key()),
        ]

        tx = Transaction(tx_inputs, tx_outputs)
        for i in range(len(tx_inputs)):
            script_pubkey = self.user_pub.get_address().to_script_pub_key()
            signature = self.user_priv.sign_input(tx, i, script_pubkey)
            tx_inputs[i].script_sig = Script([signature, self.user_pub.to_hex()])

        tx_id = self.broadcast_transaction(tx.serialize())
        return tx_id, fee

    def create_htlc(self, secret_text: str, lock_time_blocks: int, amount: int, recipient_addr: str):
        secret_hash = hashlib.sha256(secret_text.encode()).digest()
        recipient_hash = self._address_to_hash160(recipient_addr)

        htlc_script = Script([
            "OP_IF",
            "OP_SHA256",
            secret_hash.hex(),
            "OP_EQUALVERIFY",
            "OP_DUP",
            "OP_HASH160",
            recipient_hash.hex(),
            "OP_EQUALVERIFY",
            "OP_CHECKSIG",
            "OP_ELSE",
            lock_time_blocks,
            "OP_CHECKSEQUENCEVERIFY",
            "OP_DROP",
            self.user_pub.to_hex(),
            "OP_CHECKSIG",
            "OP_ENDIF",
        ])

        contract_addr = P2shAddress.from_script(htlc_script).to_string()
        self.transfer_to(target_addr=contract_addr, transfer_amount=amount)
        return contract_addr, htlc_script.to_hex()

    def retrieve_from_htlc(self, contract_addr: str, redeem_script_hex: str, secret_text: str):
        redeem_script = Script.from_raw(redeem_script_hex)
        utxos = requests.get(f"{API_BASE}/address/{contract_addr}/utxo").json()
        if not utxos:
            return None

        chunk = utxos[0]
        tx_in = TxInput(chunk["txid"], chunk["vout"])
        fee = 1000
        tx_out = TxOutput(chunk["value"] - fee, P2pkhAddress(self.user_addr).to_script_pub_key())
        tx = Transaction([tx_in], [tx_out])

        sig = self.user_priv.sign_input(tx, 0, redeem_script)
        tx_in.script_sig = Script([sig, self.user_pub.to_hex(), secret_text.encode().hex(), 1, redeem_script_hex])
        return self.broadcast_transaction(tx.serialize())

    def get_transaction_history(self) -> list:
        """Fetches transaction history and accurately identifies Incoming vs Outgoing."""
        if not self.user_addr:
            return []

        response = requests.get(f"{API_BASE}/address/{self.user_addr}/txs")
        if response.status_code != 200:
            return []

        txs = response.json()
        history = []

        for tx in txs:
            # Step 1: Check if this wallet provided any inputs (means it is Outgoing)
            is_outgoing = any(vin.get("prevout", {}).get("scriptpubkey_address") == self.user_addr for vin in tx["vin"])

            tx_type = "Outgoing" if is_outgoing else "Incoming"

            if is_outgoing:
                # Find the primary recipient (first output that isn't the user's change address)
                destinations = [
                    vout["scriptpubkey_address"]
                    for vout in tx["vout"]
                    if vout.get("scriptpubkey_address") != self.user_addr
                ]
                address = destinations[0] if destinations else "Self/Change"
                # Amount is the sum of what was sent to others
                amount = sum(vout["value"] for vout in tx["vout"] if vout.get("scriptpubkey_address") != self.user_addr)
            else:
                # Incoming: Find who sent it (first input address)
                address = tx["vin"][0].get("prevout", {}).get("scriptpubkey_address", "Unknown")
                # Amount is the sum received by this wallet
                amount = sum(vout["value"] for vout in tx["vout"] if vout.get("scriptpubkey_address") == self.user_addr)

            history.append({
                "type": tx_type,
                "status": "Confirmed" if tx["status"]["confirmed"] else "Unconfirmed",
                "address": address,
                "amount": amount,
                "fee": tx["fee"],
            })

        return history
