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
        # self.user_wif = os.getenv("KUBA_WIF", None)
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

        print("Generated:")
        print(f"wif: {wallet_wif}")
        print(f"addr: {wallet_address}")
        return wallet_wif, wallet_address

    @staticmethod
    def import_from_wif(password: str, wif: str, output_dir: str):
        os.makedirs(output_dir, exist_ok=True)

        wallet_priv = PrivateKey.from_wif(wif)
        wallet_pub = wallet_priv.get_public_key()
        wallet_address = wallet_pub.get_address().to_string()

        save_file(filename=os.path.join(output_dir, "priv_wif.txt"), message=wif, password=password)
        save_file(filename=os.path.join(output_dir, "pub_addr.txt"), message=wallet_address, password=password)

        print("Imported wallet:")
        print(f"wif: {wif}")
        print(f"addr: {wallet_address}")
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

        print(f"Available {self.satoshi} within {len(self.chunks)} chunks")

    def load_user_keys(self, password: str, wallet_dir: str):
        self.user_wif = load_file(filename=os.path.join(wallet_dir, "priv_wif.txt"), password=password)
        self.user_addr = load_file(filename=os.path.join(wallet_dir, "pub_addr.txt"), password=password)

        if not self.user_wif or not self.user_addr or self.user_wif.startswith("Wrong password") or self.user_addr.startswith("Wrong password"):
            raise Exception("Incorrect password or corrupted wallet file.")

        print("Loaded:")
        print(f"wif: {self.user_wif}")
        print(f"addr: {self.user_addr}")
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
            if ((avaible_amount := sum([chunk["value"] for chunk in tx_chunks])) + fee) > transfer_amount:
                change = math.ceil(avaible_amount - transfer_amount - fee)
                print(f"Estimated fee: {fee} satoshi")
                return tx_chunks, change, fee
        raise Exception("Cannot perform transaction with current fee rate.")


    @staticmethod
    def broadcast_transaction(raw_tx: str):
        """
        Broadcasts the hex transaction to the network and provides detailed feedback.
        """
        print("--- BROADCASTING TRANSACTION ---")
        url = f"{API_BASE}/tx"

        try:
            response = requests.post(url, data=raw_tx)

            if response.status_code == 200:
                tx_id = response.text
                print(f"SUCCESS!")
                print(f"Transaction ID: {tx_id}")
                print(f"View here: https://mempool.space/testnet/tx/{tx_id}")
                return tx_id

            else:
                print(f"BROADCAST FAILED (Status {response.status_code})")
                error_msg = response.text

                if "non-BIP68-final" in error_msg:
                    print("Error: The Timelock (CLTV) has not expired yet.")
                elif "bad-txns-inputs-spent" in error_msg:
                    print("Error: This UTXO has already been spent (Double Spend).")
                elif "min relay fee not met" in error_msg:
                    print("Error: The fee is too low for the network to accept.")
                elif "mandatory-script-verify-flag-failed" in error_msg:
                    print("Error: The Secret or the Redeem Script is incorrect.")
                else:
                    print(f"API Message: {error_msg}")

                return None

        except requests.exceptions.RequestException as e:
            print(f"NETWORK ERROR: Could not reach the API. {e}")
            return None

    def transfer_to(self, target_addr: str, transfer_amount: int):

        print(f"Sender Address: {self.user_addr}")
        print(f"Target Address: {target_addr}")
        print(f"Transaction: {transfer_amount} satoshi")

        chunks, change, fee = self._get_tx_chunks(transfer_amount=transfer_amount, transfer_priority="high")
        print(f"Using chunks: \n{pformat(chunks)}")
        print(f"Return change: {change}")
        print(f"Estimated fee: {fee} satoshi")

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
        return tx_id, fee

    def create_htlc(self, secret_text: str, lock_time_blocks: int, amount: int):
        """
        Locks funds in a P2SH HTLC contract.
        - secret_text: The string that will be hashed.
        - lock_time_blocks: Number of blocks to wait before owner can reclaim funds (1=~10min).
        """
        secret_hash = hashlib.sha256(secret_text.encode()).digest()

        htlc_script = Script([
            "OP_IF",
            "OP_SHA256",
            secret_hash.hex(),
            "OP_EQUALVERIFY",
            self.user_pub.to_hex(),
            "OP_CHECKSIG",
            "OP_ELSE",
            lock_time_blocks,
            "OP_CHECKSEQUENCEVERIFY",
            "OP_DROP",
            self.user_pub.to_hex(),
            "OP_CHECKSIG",
            "OP_ENDIF",
        ])

        p2sh_addr = P2shAddress.from_script(htlc_script)
        contract_addr = p2sh_addr.to_string()

        print(f"Contract Address: {contract_addr}")
        print(f"Redeem Script (Save this!): {htlc_script.to_hex()}")

        self.transfer_to(target_addr=contract_addr, transfer_amount=amount)
        return contract_addr, htlc_script.to_hex()

    def retrieve_from_htlc(self, contract_addr: str, redeem_script_hex: str, secret_text: str):
        """
        Retrieves funds from the HTLC using the secret.
        """
        redeem_script = Script.from_raw(redeem_script_hex)

        url = f"{API_BASE}/address/{contract_addr}/utxo"
        response = requests.get(url)
        utxos = response.json()
        if not utxos:
            print("Error: No UTXOs found for this contract address. Is it funded?")
            return None
        chunk = utxos[0]
        tx_in = TxInput(chunk["txid"], chunk["vout"])
        fee = 1000
        amount_to_receive = chunk["value"] - fee
        tx_out = TxOutput(amount_to_receive, P2pkhAddress(self.user_addr).to_script_pub_key())
        tx = Transaction([tx_in], [tx_out])
        sig = self.user_priv.sign_input(tx, 0, redeem_script)
        secret_bytes = secret_text.encode("utf-8")
        tx_in.script_sig = Script([
            sig,
            secret_bytes.hex(),
            1,
            redeem_script_hex,
        ])

        try:
            raw_tx = tx.serialize()
            print(f"Raw Transaction: {raw_tx}")
            return self.broadcast_transaction(raw_tx)
        except Exception as e:
            print(f"Serialization Error: {e}")
            for i, token in enumerate(tx_in.script_sig.script):
                print(f"Token {i} ({type(token)}): {token}")
            return None


def main():
    w = Wallet()
    # target_addr = str(os.getenv("KUBA_ADDR"))
    # assert isinstance(target_addr, str)
    # w.generate_new(password="cat")
    # w.load_user_keys(password="12345")
    # w.create_htlc(secret_text="bingus", lock_time_blocks=1, amount=27000)
    w.retrieve_from_htlc(
        contract_addr="2MxX3K46B9VXfRP5kuR7Uy8Ay7Uwmcdqvmp",
        redeem_script_hex="63a82059a3cbc4ff8edc40c9eccfbfbb98cd45a7bccc581c132868d106069828933753882102d77b6a6e96be82b4d8cde6caa8257717a322693bd543278a9735e375d95b581fac6751b2752102d77b6a6e96be82b4d8cde6caa8257717a322693bd543278a9735e375d95b581fac68",
        secret_text="bingus",
    )


if __name__ == "__main__":
    main()
