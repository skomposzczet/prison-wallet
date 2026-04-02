import random
import ecdsa
import hashlib
import base58
# import math
# from datetime import datetime
# import requests
import os

# from dotenv import load_dotenv

# from bitcoinutils.setup import setup
# from bitcoinutils.keys import PrivateKey, P2pkhAddress
# from bitcoinutils.transactions import Transaction, TxInput, TxOutput
# from bitcoinutils.script import Script

# load_dotenv()
#
# SENDER_WIF = os.getenv("WIF")
# RECIPIENT_ADDRESS = os.getenv("DT_ADR")
# AMOUNT_TO_SEND = int(os.getenv("SAT"))
#
# setup("testnet")
#
# API_BASE = "https://blockstream.info/testnet/api"
#
#
# def get_utxos(address):
#     return requests.get(f"{API_BASE}/address/{address}/utxo").json()
#
#
# def get_fee_rate():
#     data = requests.get(f"{API_BASE}/fee-estimates").json()
#     return float(data.get("6", 2.0))
#
#
# def broadcast_tx(rawtx):
#     return requests.post(f"{API_BASE}/tx", data=rawtx).text
#
#
# def estimate_tx_size(inputs, outputs):
#     return 10 + 148 * inputs + 34 * outputs
#
#
# def make_transaction():
#     if not SENDER_WIF or not RECIPIENT_ADDRESS or not AMOUNT_TO_SEND:
#         raise ValueError("Brak danych w .env (WIF, DT_ADR, SAT)")
#
#     sender_priv = PrivateKey.from_wif(SENDER_WIF)
#     sender_pub = sender_priv.get_public_key()
#     sender_addr = sender_pub.get_address().to_string()
#
#     print("Sender:", sender_addr)
#     print("Recipient:", RECIPIENT_ADDRESS)
#     print("Amount:", AMOUNT_TO_SEND, "sat")
#
#     utxos = get_utxos(sender_addr)
#
#     if not utxos:
#         raise RuntimeError("Brak UTXO — doładuj faucet")
#
#     utxo = utxos[0]
#
#     txid = utxo["txid"]
#     vout = utxo["vout"]
#     value = int(utxo["value"])
#
#     fee_rate = get_fee_rate()
#     tx_size = estimate_tx_size(1, 2)
#     fee = math.ceil(fee_rate * tx_size)
#
#     change = value - AMOUNT_TO_SEND - fee
#
#     if change < 546:
#         raise RuntimeError("Change za mały (dust)")
#
#     txin = TxInput(txid, vout)
#
#     recipient = P2pkhAddress(RECIPIENT_ADDRESS)
#
#     txout1 = TxOutput(AMOUNT_TO_SEND, recipient.to_script_pub_key())
#     txout2 = TxOutput(change, sender_pub.get_address().to_script_pub_key())
#
#     tx = Transaction([txin], [txout1, txout2])
#
#     script_pubkey = sender_pub.get_address().to_script_pub_key()
#     signature = sender_priv.sign_input(tx, 0, script_pubkey)
#
#     txin.script_sig = Script([signature, sender_pub.to_hex()])
#
#     rawtx = tx.serialize()
#
#     now = datetime.now()
#     timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
#
#     print("\nDatetime:")
#     print(timestamp)
#
#     print("\nRaw TX:")
#     print(rawtx)
#
#     txid = broadcast_tx(rawtx)
#
#     print("\nTXID:", txid)


def save_wallet_stuff(private_key, address, name):
    path = f"./stuff/{name}"
    os.makedirs(path, exist_ok=True)
    with open(f"{path}/private_key", "w") as f:
        f.write(private_key.hex())
    with open(f"{path}/address", "w") as f:
        f.write(address.decode())


def read_wallet_stuff(name):
    path = f"./stuff/{name}"
    with open(f"{path}/private_key", "r") as f:
        private_key = int(f.read())
    return private_key


def generate_wallet():
    private_key = os.urandom(32)
    sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
    vk = sk.get_verifying_key()
    public_key = b"\x04" + vk.to_string()
    sha256_hash = hashlib.sha256(public_key).digest()
    ripemd160 = hashlib.new('ripemd160', sha256_hash).digest()
    network_byte = b'\x6e' + ripemd160
    checksum = hashlib.sha256(
        hashlib.sha256(network_byte).digest()).digest()[:4]
    address = base58.b58encode(network_byte + checksum)
    return private_key, address


if __name__ == '__main__':
    private_key, address = generate_wallet()
    print('Private key:', private_key.hex())
    print('Address:', address.decode())
    save_wallet_stuff(private_key, address, 'test')
    # print(read_wallet_stuff('test'))
