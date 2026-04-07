import math
import os
from pprint import pformat
from typing import Literal

import requests
from bitcoinutils.keys import P2pkhAddress, P2shAddress, P2wpkhAddress, PrivateKey
from bitcoinutils.script import Script
from bitcoinutils.setup import setup
from bitcoinutils.transactions import Transaction, TxInput, TxOutput
from dotenv import load_dotenv

PRIORITY_LVL = {"high": 0, "low": -1}
API_BASE = "https://blockstream.info/testnet/api"

load_dotenv()
setup(network="testnet")


class Wallet:
    def __init__(self):
        self.user_wif = os.getenv("KUBA_WIF", None)
        self.satoshi = 0
        self.chunks = []
        self._set_user_keys()
        self._fetch_wallet_state()

    def _set_user_keys(self):
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
        transfer_out = TxOutput(transfer_amount, P2pkhAddress(target_addr).to_script_pub_key())
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


def main():
    w = Wallet()
    target_addr = os.getenv("MATEUSZ_ADDR")
    assert isinstance(target_addr, str)
    w.transfer_to(target_addr=target_addr, transfer_amount=2000)


if __name__ == "__main__":
    main()
