import base64
import secrets

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def save_file(filename, message, password):
    salt = secrets.token_bytes(16)
    key = derive_key(password, salt)
    f = Fernet(key)

    encrypted_data = f.encrypt(message.encode())

    with open(filename, "wb") as file:
        file.write(salt + encrypted_data)


def load_file(filename, password):
    with open(filename, "rb") as file:
        file_content = file.read()

    salt = file_content[:16]
    encrypted_data = file_content[16:]

    key = derive_key(password, salt)
    f = Fernet(key)

    try:
        return f.decrypt(encrypted_data).decode()
    except Exception:
        return "Wrong password or tampered file."
