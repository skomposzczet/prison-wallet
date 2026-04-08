import hashlib
import math
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
        # self.user_wif = os.getenv("KUBA_WIF", None)
        self.user_wif: str | None = None
        self.user_addr: str | None = None
        self.satoshi = 0
        self.chunks = []

    @staticmethod
    def generate_new(password: str):
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
        save_file(filename="priv_wif.txt", message=wallet_wif, password=password)
        save_file(filename="pub_addr.txt", message=wallet_address, password=password)
        print("Generated:")
        print(f"wif: {wallet_wif}")
        print(f"addr: {wallet_address}")

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

        # print(f"Available {self.satoshi} within {len(self.chunks)} chunks")

    def load_user_keys(self, password: str):
        self.user_wif = load_file(filename="priv_wif.txt", password=password)
        self.user_addr = load_file(filename="pub_addr.txt", password=password)
        print("Loaded:")
        print(f"wif: {self.user_wif}")
        print(f"addr: {self.user_addr}")
        self._set_user_wif()
        self._fetch_wallet_state()

    @staticmethod
    def _get_tx_fee_rate(transfer_priority: Literal["high", "low"] = "high") -> float:

        try:
            fee_rate_estimates = requests.get(f"{API_BASE}/fee-estimates").json()
        except requests.exceptions.ConnectionError as e:
            raise Exception("Failed to obtain fee rate estimates") from e

        fee_rate_sorted = sorted(fee_rate_estimates.items(), key=lambda item: item[1])
        priority_idx = PRIORITY_LVL[transfer_priority]
        fee_rate: float = round(fee_rate_sorted[priority_idx][1], 4)
        print(f"Estimated fee rate: {fee_rate}sat/vB for priority {transfer_priority}")
        return fee_rate

    @staticmethod
    def _estimate_tx_size(n_inputs: int, n_outputs: int = 2) -> float:
        """Estimate vB size for transaction fees.
        Args:
            n_inputs: chunks with required amount of satoshi.
            n_outputs: chunk* send to recipient and surplus of satoshi back to our wallet.
        """
        return 10 + (148 * n_inputs) + (34 * n_outputs)

    def _get_tx_chunks(self, transfer_amount: int, transfer_priority: Literal["high", "low"]) -> tuple[list, int]:
        if self.satoshi < transfer_amount:
            raise Exception("Not enough funds in wallet.")

        fee_rate = self._get_tx_fee_rate(transfer_priority=transfer_priority)
        tx_chunks = []

        for chunk in self.chunks:
            tx_chunks.append(chunk)
            tx_size = self._estimate_tx_size(len(tx_chunks))
            fee = tx_size * fee_rate
            if ((avaible_amount := sum([chunk["value"] for chunk in tx_chunks])) + fee) > transfer_amount:
                change = math.ceil(avaible_amount - transfer_amount - fee)
                print(f"Estimated fee: {fee} satoshi")
                return tx_chunks, change
        raise Exception("Cannot perform transaction with current fee rate.")

    @staticmethod
    def broadcast_transaction(raw_tx):
        return requests.post(f"{API_BASE}/tx", data=raw_tx).text

    def transfer_to(self, target_addr: str, transfer_amount: int):

        print(f"Sender Address: {self.user_addr}")
        print(f"Target Address: {target_addr}")
        print(f"Transaction: {transfer_amount} satoshi")

        chunks, change = self._get_tx_chunks(transfer_amount=transfer_amount, transfer_priority="high")
        print(f"Using chunks: \n{pformat(chunks)}")
        print(f"Return change: {change}")

        tx_inputs = [TxInput(chunk["txid"], chunk["vout"]) for chunk in chunks]
        tx_outputs = []

        if target_addr.startswith("2"):  # '2' for Testnet P2SH, '3' for Mainnet
            target_script = P2shAddress(target_addr).to_script_pub_key()
        else:
            target_script = P2pkhAddress(target_addr).to_script_pub_key()

        transfer_out = TxOutput(transfer_amount, target_script)
        change_back = TxOutput(change, P2pkhAddress(self.user_addr).to_script_pub_key())
        tx_outputs.append(transfer_out)
        tx_outputs.append(change_back)
        tx = Transaction(tx_inputs, tx_outputs)

        for i in range(len(tx_inputs)):
            script_pubkey = self.user_pub.get_address().to_script_pub_key()
            signature = self.user_priv.sign_input(tx, i, script_pubkey)
            tx_inputs[i].script_sig = Script([signature, self.user_pub.to_hex()])

        raw_tx = tx.serialize()
        print(f"Raw transaction: \n{raw_tx}")
        tx_id = self.broadcast_transaction(raw_tx)
        print(f"Broadcasted transaction: \n{tx_id}")

    def create_htlc(self, secret_text: str, time_to_expiry: int):
        """
        Creates a Hashlock + Timelock contract.
        Success path: Anyone with the secret can spend.
        Timeout path: Only THIS wallet can spend after expiry.
        """
        if not self.user_pub:
            raise Exception("Wallet keys not loaded. Load keys first.")

        secret_bytes = secret_text.encode()
        hash_lock = hashlib.sha256(secret_bytes).digest()
        expiry_time = int(time.time()) + (time_to_expiry * 60)
        redeem_script = Script([
            "OP_IF",
            "OP_SHA256",
            hash_lock.hex(),
            "OP_EQUALVERIFY",
            "OP_ELSE",
            expiry_time,
            "OP_CHECKLOCKTIMEVERIFY",
            "OP_DROP",
            self.user_pub.to_hex(),
            "OP_CHECKSIG",
            "OP_ENDIF",
        ])
        contract_addr = P2shAddress.from_script(redeem_script)
        print("\n--- NEW HTLC CONTRACT ---")
        print(f"Contract Address: {contract_addr.to_string()}")
        print(f"Secret (Keep safe): {secret_text}")
        print(f"Expiry Timestamp:  {expiry_time}")
        print(f"Redeem Script Hex: {redeem_script.to_hex()}")

        return {"address": contract_addr.to_string(), "redeem_script": redeem_script, "expiry": expiry_time}

    def _fetch_contract_utxo(self, contract_address: str):
        try:
            # Query the contract address instead of the user address
            response = requests.get(f"{API_BASE}/address/{contract_address}/utxo")
            utxos = response.json()

            if not utxos:
                print(f"No funds found at {contract_address} yet.")
                return None

            confirmed_utxos = [u for u in utxos if u["status"]["confirmed"]]
            if not confirmed_utxos:
                print("Funds found, but they are still unconfirmed (mempool).")
                return None

            target = confirmed_utxos[0]
            # print(f"Found UTXO: {target['txid']} at vout {target['vout']}")
            return target

        except Exception as e:
            print(f"Error fetching contract UTXO: {e}")
            return None

    def reclaim_with_secret(self, contract_address, secret_text, redeem_script):
        contract_utxo = self._fetch_contract_utxo(contract_address=contract_address)
        tx_input = TxInput(contract_utxo["txid"], contract_utxo["vout"])
        fee = 700
        amount_to_receive = contract_utxo["value"] - fee
        tx_output = TxOutput(amount_to_receive, P2pkhAddress(self.user_addr).to_script_pub_key())
        tx = Transaction([tx_input], [tx_output])
        secret_hex = secret_text.encode().hex()
        tx_input.script_sig = Script([secret_hex, "OP_1", redeem_script])
        raw_tx = tx.serialize()
        print(f"Reclaim Transaction Hex: {raw_tx}")
        return raw_tx


def main():
    w = Wallet()
    # target_addr = os.getenv("MATEUSZ_ADDR")
    # assert isinstance(target_addr, str)
    # w.generate_new(password="cat")
    w.load_user_keys(password="cat")
    # w._fetch_wallet_state()
    # w.create_htlc(secret_text="bingus666", time_to_expiry=30)
    # w.transfer_to(target_addr="2NEPp42AEJm7WNyyEkoDF7VcAyps5oStkM2", transfer_amount=2000)
    w.reclaim_with_secret(
        contract_address="2NEPp42AEJm7WNyyEkoDF7VcAyps5oStkM2",
        secret_text="bingus666",
        redeem_script="63a8200e13dcd36bf6694b1976ed3059f6e200cc498b9b1296b75b2921c730da960550886704c3c5d669b1752102d77b6a6e96be82b4d8cde6caa8257717a322693bd543278a9735e375d95b581fac68",
    )


if __name__ == "__main__":
    main()
