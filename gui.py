import os
import threading
from tkinter import messagebox
import customtkinter as ctk

from main import Wallet
from eth_wallet import EthWallet, wei_to_eth, eth_to_wei, fmt_wei

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CURRENCY_ICON = {"btc": "₿", "eth": "Ξ"}
CURRENCY_COLOR = {"btc": "#f7931a", "eth": "#627eea"}

DEFAULT_SOLIDITY_CONTRACT = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract HelloWorld {
    string private message = "Hello from Prison Wallet";

    function greet(string memory name) public view returns (string memory) {
        return string(abi.encodePacked(message, ", ", name));
    }
}
"""


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Prison Wallet")
        self.geometry("1200x900")
        self.minsize(900, 650)
        self.resizable(True, True)

        self.current_user = None
        self.current_password = None
        self.current_wallet = None        # wallet folder name
        self.current_currency = None      # "btc" or "eth"
        self.current_wallet_obj = None
        self.current_wallet_key = None
        self.contract_confirm_data = {}

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.page_classes = {
            F.__name__: F for F in (
                LoginPage, RegisterPage, ProfilePage,
                SelectCurrencyPage,
                NewBtcWalletPage, NewEthWalletPage,
                WalletPage, EthWalletPage,
                EthNewTxPage, EthTxHistoryPage,
                SmartContractPage, NewTxPage, TxHistoryPage, ContractConfirmPage,
            )
        }
        self.frames = {}

        self.show_frame("LoginPage")

    def get_frame(self, name):
        if name not in self.frames:
            frame_class = self.page_classes[name]
            frame = frame_class(self.container, self)
            self.frames[name] = frame
            frame.grid(row=0, column=0, sticky="nsew")
        return self.frames[name]

    def show_frame(self, name):
        frame = self.get_frame(name)
        frame.tkraise()
        on_show = getattr(frame, "on_show", None)
        if on_show:
            on_show()

    def user_dir(self):
        return os.path.join(os.getcwd(), ".prison-wallet", self.current_user)

    def wallets_dir(self, currency=None):
        cur = currency or self.current_currency or "btc"
        return os.path.join(self.user_dir(), "wallets", cur)

    def password_file(self):
        return os.path.join(self.user_dir(), "password.txt")


# ---------------------------------------------------------------------------
# Auth pages
# ---------------------------------------------------------------------------

class LoginPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="Login", font=(None, 30)).pack(pady=20)

        self.user = ctk.CTkEntry(self.content, placeholder_text="Username", width=400)
        self.user.pack(pady=10)

        self.pw = ctk.CTkEntry(self.content, placeholder_text="Password", show="*", width=400)
        self.pw.pack(pady=10)

        ctk.CTkButton(self.content, text="Login", command=self.login, width=200).pack(pady=10)
        ctk.CTkButton(self.content, text="Register", command=lambda: controller.show_frame("RegisterPage"), width=200).pack(pady=5)

    def login(self):
        username = self.user.get()
        password = self.pw.get()

        user_path = os.path.join(os.getcwd(), ".prison-wallet", username)
        pw_file = os.path.join(user_path, "password.txt")

        if not os.path.exists(user_path):
            messagebox.showerror("Error", "User does not exist")
            return
        if not os.path.exists(pw_file):
            messagebox.showerror("Error", "Password file missing")
            return

        with open(pw_file) as f:
            stored_pw = f.read().strip()

        if password == stored_pw:
            self.controller.current_user = username
            self.controller.current_password = password
            self.controller.current_wallet = None
            self.controller.current_currency = None
            self.controller.current_wallet_obj = None
            self.controller.current_wallet_key = None
            self.controller.show_frame("ProfilePage")
        else:
            messagebox.showerror("Error", "Wrong password")


class RegisterPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="Register", font=(None, 30)).pack(pady=20)

        self.user = ctk.CTkEntry(self.content, placeholder_text="Username", width=400)
        self.user.pack(pady=10)

        self.pw = ctk.CTkEntry(self.content, placeholder_text="Password", show="*", width=400)
        self.pw.pack(pady=10)

        ctk.CTkButton(self.content, text="Create", command=self.register, width=200).pack(pady=10)
        ctk.CTkButton(self.content, text="Back", command=lambda: controller.show_frame("LoginPage"), width=200).pack(pady=5)

    def register(self):
        username = self.user.get()
        password = self.pw.get()

        base_user = os.path.join(os.getcwd(), ".prison-wallet", username)
        pw_file = os.path.join(base_user, "password.txt")

        if os.path.exists(base_user):
            messagebox.showerror("Error", "User already exists")
            return

        os.makedirs(base_user, exist_ok=True)
        os.makedirs(os.path.join(base_user, "wallets", "btc"), exist_ok=True)
        os.makedirs(os.path.join(base_user, "wallets", "eth"), exist_ok=True)

        with open(pw_file, "w") as f:
            f.write(password)

        messagebox.showinfo("Success", "User created")
        self.controller.show_frame("LoginPage")


# ---------------------------------------------------------------------------
# Profile — lists wallets from both currencies
# ---------------------------------------------------------------------------

class ProfilePage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.label = ctk.CTkLabel(self.content, text="Profile", font=(None, 30))
        self.label.pack(pady=10)

        self.wallets_frame = ctk.CTkScrollableFrame(self.content, width=400, height=300)
        self.wallets_frame.pack(pady=10)

        ctk.CTkButton(self.content, text="New Wallet",
                      command=lambda: controller.show_frame("SelectCurrencyPage"), width=200).pack(pady=5)
        ctk.CTkButton(self.content, text="Logout",
                      command=lambda: controller.show_frame("LoginPage"), width=200).pack(pady=5)

    def on_show(self):
        self.refresh()

    def refresh(self):
        for w in self.wallets_frame.winfo_children():
            w.destroy()

        for currency in ("btc", "eth"):
            path = self.controller.wallets_dir(currency)
            os.makedirs(path, exist_ok=True)
            for fname in sorted(os.listdir(path)):
                wallet_path = os.path.join(path, fname)
                if not os.path.isdir(wallet_path):
                    continue

                icon = CURRENCY_ICON[currency]
                color = CURRENCY_COLOR[currency]

                row = ctk.CTkFrame(self.wallets_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)

                ctk.CTkLabel(row, text=icon, font=(None, 18, "bold"),
                             text_color=color, width=30).pack(side="left", padx=(4, 6))
                ctk.CTkButton(row, text=fname, anchor="w",
                              command=lambda f=fname, c=currency: self.open_wallet(f, c),
                              width=340).pack(side="left")

    def open_wallet(self, fname, currency):
        self.controller.current_wallet = fname
        self.controller.current_currency = currency
        self.controller.current_wallet_obj = None
        self.controller.current_wallet_key = None
        if currency == "btc":
            self.controller.show_frame("WalletPage")
        else:
            self.controller.show_frame("EthWalletPage")


# ---------------------------------------------------------------------------
# Select currency before creating a wallet
# ---------------------------------------------------------------------------

class SelectCurrencyPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="Select Currency", font=(None, 30)).pack(pady=20)
        ctk.CTkLabel(self.content, text="Which type of wallet do you want to create?",
                     font=(None, 14), text_color="gray").pack(pady=(0, 20))

        ctk.CTkButton(
            self.content, text=f"{CURRENCY_ICON['btc']}  Bitcoin (BTC)",
            command=lambda: controller.show_frame("NewBtcWalletPage"),
            width=260, height=60, font=(None, 22, "bold"),
            fg_color=CURRENCY_COLOR["btc"], hover_color="#c97800",
        ).pack(pady=10)

        ctk.CTkButton(
            self.content, text=f"{CURRENCY_ICON['eth']}  Ethereum (ETH)",
            command=lambda: controller.show_frame("NewEthWalletPage"),
            width=260, height=60, font=(None, 22, "bold"),
            fg_color=CURRENCY_COLOR["eth"], hover_color="#3d56b0",
        ).pack(pady=10)

        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("ProfilePage"), width=200).pack(pady=(20, 10))


# ---------------------------------------------------------------------------
# New BTC wallet
# ---------------------------------------------------------------------------

class NewBtcWalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text=f"{CURRENCY_ICON['btc']}  New Bitcoin Wallet",
                     font=(None, 30), text_color=CURRENCY_COLOR["btc"]).pack(pady=20)

        self.name = ctk.CTkEntry(self.content, placeholder_text="Wallet name", width=400)
        self.name.pack(pady=10)

        self.wif = ctk.CTkEntry(self.content,
                                placeholder_text="Existing WIF (optional – leave blank to generate)", width=400)
        self.wif.pack(pady=10)

        ctk.CTkButton(self.content, text="Import Wallet", command=self.import_wallet, width=220).pack(pady=5)
        ctk.CTkButton(self.content, text="Generate New Wallet", command=self.create_wallet, width=220).pack(pady=5)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("SelectCurrencyPage"), width=220).pack(pady=5)

    def _wallet_path(self, name):
        return os.path.join(self.controller.wallets_dir("btc"), name)

    def create_wallet(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a wallet name")
            return

        path = self._wallet_path(name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Wallet already exists")
            return

        try:
            _, address = Wallet.generate_new(password=self.controller.current_password, output_dir=path)
            messagebox.showinfo("Success", f"Wallet created\nAddress: {address}")
            self.controller.show_frame("ProfilePage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create wallet: {e}")

    def import_wallet(self):
        name = self.name.get().strip()
        wif = self.wif.get().strip()

        if not name:
            messagebox.showerror("Error", "Please enter a wallet name")
            return
        if not wif:
            messagebox.showerror("Error", "Please enter the WIF to import")
            return

        path = self._wallet_path(name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Wallet already exists")
            return

        try:
            _, address = Wallet.import_from_wif(
                password=self.controller.current_password, wif=wif, output_dir=path)
            messagebox.showinfo("Success", f"Wallet imported\nAddress: {address}")
            self.controller.show_frame("ProfilePage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import wallet: {e}")


# ---------------------------------------------------------------------------
# New ETH wallet — stub
# ---------------------------------------------------------------------------

class NewEthWalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text=f"{CURRENCY_ICON['eth']}  New Ethereum Wallet",
                     font=(None, 30), text_color=CURRENCY_COLOR["eth"]).pack(pady=20)

        self.name = ctk.CTkEntry(self.content, placeholder_text="Wallet name", width=400)
        self.name.pack(pady=10)

        self.privkey = ctk.CTkEntry(
            self.content,
            placeholder_text="Existing private key hex (optional – leave blank to generate)",
            width=400,
        )
        self.privkey.pack(pady=10)

        ctk.CTkButton(self.content, text="Import Wallet", command=self.import_wallet, width=220).pack(pady=5)
        ctk.CTkButton(self.content, text="Generate New Wallet", command=self.create_wallet, width=220).pack(pady=5)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("SelectCurrencyPage"), width=220).pack(pady=5)

    def _wallet_path(self, name: str) -> str:
        return os.path.join(self.controller.wallets_dir("eth"), name)

    def create_wallet(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a wallet name")
            return

        path = self._wallet_path(name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Wallet already exists")
            return

        try:
            _, address = EthWallet.generate_new(
                password=self.controller.current_password, output_dir=path
            )
            messagebox.showinfo("Success", f"ETH wallet created\nAddress: {address}")
            self.controller.show_frame("ProfilePage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create wallet: {e}")

    def import_wallet(self):
        name = self.name.get().strip()
        key = self.privkey.get().strip()

        if not name:
            messagebox.showerror("Error", "Please enter a wallet name")
            return
        if not key:
            messagebox.showerror("Error", "Please enter the private key to import")
            return

        path = self._wallet_path(name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Wallet already exists")
            return

        try:
            _, address = EthWallet.import_from_key(
                password=self.controller.current_password,
                private_key_hex=key,
                output_dir=path,
            )
            messagebox.showinfo("Success", f"ETH wallet imported\nAddress: {address}")
            self.controller.show_frame("ProfilePage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import wallet: {e}")


# ---------------------------------------------------------------------------
# BTC Wallet page
# ---------------------------------------------------------------------------

class WalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.loaded_address = ""
        self.load_generation = 0

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.label = ctk.CTkLabel(self.content, text="Wallet", font=(None, 60))
        self.label.pack(pady=10)

        self.address_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.address_frame.pack(fill="x", pady=10, padx=20)

        self.address_label = ctk.CTkLabel(self.address_frame, text="Address: ?",
                                          anchor="w", justify="left", font=(None, 36))
        self.address_label.pack(side="left", fill="x", expand=True)

        self.copy_button = ctk.CTkButton(self.address_frame, text="📋", command=self.copy_address,
                                         width=40, state="disabled", font=(None, 24))
        self.copy_button.pack(side="left", padx=10)

        self.balance_label = ctk.CTkLabel(self.content, text="Balance: 0", font=(None, 36))
        self.balance_label.pack(pady=10)

        ctk.CTkButton(self.content, text="Create Transaction",
                      command=lambda: controller.show_frame("NewTxPage"), width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Create Smart Contract",
                      command=lambda: controller.show_frame("SmartContractPage"), width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Transaction History",
                      command=lambda: controller.show_frame("TxHistoryPage"), width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("ProfilePage"), width=240, font=(None, 24)).pack(pady=5)

    def on_show(self):
        self.load_wallet()

    def load_wallet(self):
        if not self.controller.current_wallet:
            self.balance_label.configure(text="Balance: ?")
            self.address_label.configure(text="Address: ?")
            self.copy_button.configure(state="disabled")
            return

        wallet_key = ("btc", self.controller.current_wallet)
        if self.controller.current_wallet_key == wallet_key and isinstance(self.controller.current_wallet_obj, Wallet):
            self.show_wallet(self.controller.current_wallet_obj)
            return

        wallet_dir = os.path.join(self.controller.wallets_dir("btc"), self.controller.current_wallet)
        wallet_name = self.controller.current_wallet
        password = self.controller.current_password
        self.load_generation += 1
        generation = self.load_generation

        self.label.configure(text=f"₿  {wallet_name}")
        self.balance_label.configure(text="Balance: loading...")
        self.address_label.configure(text="Address: loading...")
        self.copy_button.configure(state="disabled")

        def _load():
            try:
                wallet = Wallet()
                wallet.load_user_keys(password=password, wallet_dir=wallet_dir)
            except Exception as e:
                self.after(0, lambda err=e, gen=generation: self.show_wallet_error(err, gen))
                return
            self.after(0, lambda w=wallet, key=wallet_key, gen=generation: self.finish_wallet_load(w, key, gen))

        threading.Thread(target=_load, daemon=True).start()

    def finish_wallet_load(self, wallet, wallet_key, generation):
        selected_key = (self.controller.current_currency, self.controller.current_wallet)
        if generation != self.load_generation or selected_key != wallet_key:
            return
        self.controller.current_wallet_obj = wallet
        self.controller.current_wallet_key = wallet_key
        self.show_wallet(wallet)

    def show_wallet(self, wallet):
        balance = wallet.satoshi
        address = wallet.user_addr or ""
        self.loaded_address = address
        self.balance_label.configure(text=f"Balance: {balance} satoshi")
        self.label.configure(text=f"₿  {self.controller.current_wallet}")
        self.address_label.configure(text=f"Address: {address}")
        self.copy_button.configure(state="normal" if address else "disabled")

    def show_wallet_error(self, error, generation):
        if generation != self.load_generation:
            return
        messagebox.showerror("Error", f"Unable to load wallet: {error}")
        self.balance_label.configure(text="Balance: ?")
        self.address_label.configure(text="Address: ?")
        self.copy_button.configure(state="disabled")

    def copy_address(self):
        if not self.loaded_address:
            messagebox.showerror("Error", "No wallet address available to copy")
            return
        self.clipboard_clear()
        self.clipboard_append(self.loaded_address)
        messagebox.showinfo("Copied", "Wallet address copied to clipboard")


# ---------------------------------------------------------------------------
# ETH Wallet page — stub
# ---------------------------------------------------------------------------

class EthWalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.loaded_address = ""
        self.load_generation = 0

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.label = ctk.CTkLabel(self.content, text="Ξ  ETH Wallet", font=(None, 60),
                                  text_color=CURRENCY_COLOR["eth"])
        self.label.pack(pady=10)

        # Address row with copy button
        self.address_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.address_frame.pack(fill="x", pady=10, padx=20)

        self.address_label = ctk.CTkLabel(self.address_frame, text="Address: ?",
                                          anchor="w", justify="left", font=(None, 20))
        self.address_label.pack(side="left", fill="x", expand=True)

        self.copy_button = ctk.CTkButton(self.address_frame, text="📋",
                                         command=self.copy_address,
                                         width=40, state="disabled", font=(None, 24))
        self.copy_button.pack(side="left", padx=10)

        self.balance_label = ctk.CTkLabel(self.content, text="Balance: ?", font=(None, 36))
        self.balance_label.pack(pady=10)

        ctk.CTkButton(self.content, text="Send ETH",
                      command=lambda: controller.show_frame("EthNewTxPage"),
                      width=240, font=(None, 24),
                      fg_color=CURRENCY_COLOR["eth"], hover_color="#3d56b0").pack(pady=5)
        ctk.CTkButton(self.content, text="Deploy Smart Contract",
                      command=lambda: controller.show_frame("SmartContractPage"),
                      width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Transaction History",
                      command=lambda: controller.show_frame("EthTxHistoryPage"),
                      width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("ProfilePage"),
                      width=240, font=(None, 24)).pack(pady=5)

    def on_show(self):
        self.load_wallet()

    def load_wallet(self):
        if not self.controller.current_wallet:
            self.balance_label.configure(text="Balance: ?")
            self.address_label.configure(text="Address: ?")
            self.copy_button.configure(state="disabled")
            return

        wallet_key = ("eth", self.controller.current_wallet)
        if self.controller.current_wallet_key == wallet_key and isinstance(self.controller.current_wallet_obj, EthWallet):
            self.show_wallet(self.controller.current_wallet_obj)
            return

        wallet_dir = os.path.join(
            self.controller.wallets_dir("eth"), self.controller.current_wallet
        )
        wallet_name = self.controller.current_wallet
        password = self.controller.current_password
        self.load_generation += 1
        generation = self.load_generation

        self.label.configure(text=f"Ξ  {wallet_name}")
        self.balance_label.configure(text="Balance: loading...")
        self.address_label.configure(text="Address: loading...")
        self.copy_button.configure(state="disabled")

        def _load():
            try:
                wallet = EthWallet()
                wallet.load_user_keys(password=password, wallet_dir=wallet_dir)
            except Exception as e:
                self.after(0, lambda err=e, gen=generation: self.show_wallet_error(err, gen))
                return
            self.after(0, lambda w=wallet, key=wallet_key, gen=generation: self.finish_wallet_load(w, key, gen))

        threading.Thread(target=_load, daemon=True).start()

    def finish_wallet_load(self, wallet, wallet_key, generation):
        selected_key = (self.controller.current_currency, self.controller.current_wallet)
        if generation != self.load_generation or selected_key != wallet_key:
            return
        self.controller.current_wallet_obj = wallet
        self.controller.current_wallet_key = wallet_key
        self.show_wallet(wallet)

    def show_wallet(self, wallet):
        address = wallet.user_addr or ""
        self.loaded_address = address
        self.label.configure(text=f"Ξ  {self.controller.current_wallet}")
        self.address_label.configure(text=f"Address: {address}")
        self.balance_label.configure(
            text=f"Balance: {wallet.eth:.6f} ETH  ({fmt_wei(wallet.wei)})"
        )
        self.copy_button.configure(state="normal" if address else "disabled")

    def show_wallet_error(self, error, generation):
        if generation != self.load_generation:
            return
        messagebox.showerror("Error", f"Unable to load ETH wallet: {error}")
        self.balance_label.configure(text="Balance: ?")
        self.address_label.configure(text="Address: ?")
        self.copy_button.configure(state="disabled")

    def copy_address(self):
        if not self.loaded_address:
            messagebox.showerror("Error", "No wallet address available to copy")
            return
        self.clipboard_clear()
        self.clipboard_append(self.loaded_address)
        messagebox.showinfo("Copied", "Wallet address copied to clipboard")


# ---------------------------------------------------------------------------
# ETH New Transaction page
# ---------------------------------------------------------------------------

class EthNewTxPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="Ξ  Send ETH", font=(None, 30),
                     text_color=CURRENCY_COLOR["eth"]).pack(pady=20)

        self.balance_label = ctk.CTkLabel(self.content, text="Balance: ?", font=(None, 16))
        self.balance_label.pack(pady=(0, 10))

        self.to = ctk.CTkEntry(self.content, placeholder_text="Recipient address (0x…)", width=440)
        self.to.pack(pady=10)

        self.amount_eth = ctk.CTkEntry(self.content, placeholder_text="Amount in ETH (e.g. 0.001)", width=440)
        self.amount_eth.pack(pady=10)

        ctk.CTkButton(self.content, text="Send", command=self.send,
                      width=200, fg_color=CURRENCY_COLOR["eth"], hover_color="#3d56b0").pack(pady=10)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("EthWalletPage"), width=200).pack(pady=5)

    def on_show(self):
        self.refresh_balance()

    def refresh_balance(self):
        wallet = self.controller.current_wallet_obj
        if wallet is None or not hasattr(wallet, "eth"):
            self.balance_label.configure(text="Balance: ?")
            return
        self.balance_label.configure(
            text=f"Balance: {wallet.eth:.6f} ETH  ({fmt_wei(wallet.wei)})"
        )

    def send(self):
        target_addr = self.to.get().strip()
        amount_text = self.amount_eth.get().strip()

        if not target_addr or not amount_text:
            messagebox.showerror("Error", "Please enter a destination address and amount")
            return

        if not target_addr.startswith("0x") or len(target_addr) != 42:
            messagebox.showerror("Error", "Invalid Ethereum address (must start with 0x, 42 chars)")
            return

        try:
            amount_eth_float = float(amount_text)
            if amount_eth_float <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Amount must be a positive number (e.g. 0.001)")
            return

        amount_wei = eth_to_wei(amount_eth_float)

        wallet = self.controller.current_wallet_obj
        if wallet is None or not hasattr(wallet, "wei"):
            messagebox.showerror("Error", "ETH wallet is not loaded")
            return

        try:
            fee_wei = wallet.estimate_fee()
        except Exception as e:
            messagebox.showerror("Error", f"Unable to estimate fee: {e}")
            return

        fee_eth = wei_to_eth(fee_wei)
        proceed = messagebox.askyesno(
            "Confirm Transaction",
            f"Amount : {amount_eth_float:.6f} ETH  ({fmt_wei(amount_wei)})\n"
            f"Fee    : {fee_eth:.6f} ETH  ({fmt_wei(fee_wei)})\n\n"
            f"Do you want to continue?",
        )
        if not proceed:
            return

        try:
            tx_hash, fee = wallet.transfer_to(
                target_addr=target_addr, transfer_amount_wei=amount_wei
            )
            if tx_hash:
                messagebox.showinfo(
                    "Success",
                    f"Transaction broadcasted!\n"
                    f"TX Hash: {tx_hash}\n"
                    f"Fee: {wei_to_eth(fee):.6f} ETH\n\n"
                    f"View: https://sepolia.etherscan.io/tx/{tx_hash}",
                )
                self.controller.show_frame("EthWalletPage")
            else:
                messagebox.showerror("Error", "Broadcast failed. Check console for details.")
        except Exception as e:
            messagebox.showerror("Error", f"Transaction failed: {e}")


# ---------------------------------------------------------------------------
# ETH Transaction History page
# ---------------------------------------------------------------------------

class EthTxHistoryPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(header, text="Ξ  ETH Transaction History", font=(None, 28),
                     text_color=CURRENCY_COLOR["eth"]).pack(side="left", padx=10)
        ctk.CTkButton(header, text="Refresh", command=self.load_history, width=120).pack(side="right", padx=10)
        ctk.CTkButton(header, text="Back",
                      command=lambda: controller.show_frame("EthWalletPage"), width=100).pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(self, text="", font=(None, 14))
        self.status_label.pack(pady=(5, 0))

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

    def on_show(self):
        self.load_history()

    def load_history(self):
        wallet = self.controller.current_wallet_obj
        if wallet is None or not hasattr(wallet, "wei") or not wallet.user_addr:
            for w in self.scroll_frame.winfo_children():
                w.destroy()
            self.status_label.configure(text="No ETH wallet loaded.")
            return

        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self.status_label.configure(text="Loading...")
        self.update_idletasks()

        def _fetch():
            try:
                txs = wallet.fetch_tx_history()
            except Exception as e:
                self.after(0, lambda err=e: self.status_label.configure(
                    text=f"Error: {err}"))
                return
            self.after(0, lambda t=txs: self._render_txs(t))

        threading.Thread(target=_fetch, daemon=True).start()

    def _render_txs(self, txs: list):
        if not txs:
            self.status_label.configure(text="No transactions found for this address.")
            return

        self.status_label.configure(text=f"{len(txs)} transaction(s) found")

        for tx in txs:
            txid = tx["txid"]
            confirmed = tx["confirmed"]
            tx_type = tx["type"]
            amount_wei = tx["amount"]
            fee_wei = tx["fee"]

            amount_eth = wei_to_eth(amount_wei)

            if tx_type == "incoming":
                type_label = "+ INCOMING"
                type_color = "#2ecc71"
            else:
                type_label = "- OUTGOING"
                type_color = "#e74c3c"

            fee_str = (
                f"{wei_to_eth(fee_wei):.6f} ETH  ({fmt_wei(fee_wei)})"
                if fee_wei is not None else "—"
            )

            card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
            card.pack(fill="x", pady=4, padx=4)

            # ── row 1: type + ETH amount ──────────────────────────────────
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 2))

            ctk.CTkLabel(top, text=type_label, font=(None, 16, "bold"),
                         text_color=type_color, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(top, text=f"{amount_eth:.6f} ETH", font=(None, 16, "bold"),
                         anchor="e").pack(side="right")

            # ── row 2: wei in scientific notation ─────────────────────────
            mid = ctk.CTkFrame(card, fg_color="transparent")
            mid.pack(fill="x", padx=12, pady=(0, 2))

            ctk.CTkLabel(mid, text="", width=140).pack(side="left")   # spacer
            ctk.CTkLabel(mid, text=fmt_wei(amount_wei), font=(None, 11),
                         text_color="gray", anchor="e").pack(side="right")

            # ── row 3: txid + fee + status ────────────────────────────────
            bottom = ctk.CTkFrame(card, fg_color="transparent")
            bottom.pack(fill="x", padx=12, pady=(0, 10))

            short_txid = f"{txid[:16]}…{txid[-8:]}" if len(txid) > 26 else txid
            ctk.CTkLabel(bottom, text=f"TX: {short_txid}", font=(None, 11),
                         text_color="gray", anchor="w").pack(side="left")

            status_text = "Confirmed" if confirmed else "Pending"
            status_color = "#2ecc71" if confirmed else "#f39c12"
            ctk.CTkLabel(bottom, text=f"Fee: {fee_str}   |   {status_text}",
                         font=(None, 11), text_color=status_color, anchor="e").pack(side="right")


# ---------------------------------------------------------------------------
# Smart Contract page
# ---------------------------------------------------------------------------

class SmartContractPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.title_label = ctk.CTkLabel(self.content, text="New Smart Contract", font=(None, 30))
        self.title_label.pack(pady=20)

        self.btc_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.eth_frame = ctk.CTkFrame(self.content, fg_color="transparent")

        self.secret_text = ctk.CTkEntry(self.btc_frame, placeholder_text="Secret text", width=500)
        self.secret_text.pack(pady=10)

        self.recipient_address = ctk.CTkEntry(self.btc_frame, placeholder_text="Recipient wallet address", width=500)
        self.recipient_address.pack(pady=10)

        self.lock_time = ctk.CTkEntry(self.btc_frame, placeholder_text="Lock time (minutes)", width=500)
        self.lock_time.pack(pady=10)

        self.lock_amount = ctk.CTkEntry(self.btc_frame, placeholder_text="Amount to lock (satoshi)", width=500)
        self.lock_amount.pack(pady=10)

        ctk.CTkButton(self.btc_frame, text="Create Contract", command=self.create_contract, width=240).pack(pady=10)

        ctk.CTkLabel(self.btc_frame, text="Retrieve Contract", font=(None, 24)).pack(pady=20)

        self.contract_address = ctk.CTkEntry(self.btc_frame, placeholder_text="Contract address", width=500)
        self.contract_address.pack(pady=10)

        self.redeem_script = ctk.CTkEntry(self.btc_frame, placeholder_text="Redeem script hex", width=500)
        self.redeem_script.pack(pady=10)

        self.redeem_secret = ctk.CTkEntry(self.btc_frame, placeholder_text="Secret text", width=500)
        self.redeem_secret.pack(pady=10)

        ctk.CTkButton(self.btc_frame, text="Retrieve Contract", command=self.retrieve_contract, width=240).pack(pady=10)

        ctk.CTkLabel(self.eth_frame, text="Solidity source (.sol)", font=(None, 16),
                     text_color=CURRENCY_COLOR["eth"]).pack(anchor="w", padx=4, pady=(0, 6))
        self.sol_source = ctk.CTkTextbox(self.eth_frame, width=760, height=360, font=("monospace", 13))
        self.sol_source.pack(pady=6)
        self.sol_source.insert("1.0", DEFAULT_SOLIDITY_CONTRACT)

        self.eth_status = ctk.CTkLabel(self.eth_frame, text="Network: Sepolia public RPC", font=(None, 13),
                                       text_color="gray")
        self.eth_status.pack(pady=(4, 10))
        self.deploy_button = ctk.CTkButton(
            self.eth_frame,
            text="Deploy Contract",
            command=self.deploy_eth_contract,
            width=240,
            fg_color=CURRENCY_COLOR["eth"],
            hover_color="#3d56b0",
        )
        self.deploy_button.pack(pady=5)

        self.back_button = ctk.CTkButton(self.content, text="Back",
                                         command=self.go_back, width=240)
        self.back_button.pack(pady=10)

    def on_show(self):
        self.refresh_mode()

    def refresh_mode(self):
        self.btc_frame.pack_forget()
        self.eth_frame.pack_forget()

        if self.controller.current_currency == "eth":
            self.title_label.configure(text="Ξ  Deploy Smart Contract", text_color=CURRENCY_COLOR["eth"])
            self.eth_frame.pack(pady=0)
            self.back_button.configure(command=lambda: self.controller.show_frame("EthWalletPage"))
        else:
            self.title_label.configure(text="New Smart Contract", text_color=("gray10", "#DCE4EE"))
            self.btc_frame.pack(pady=0)
            self.back_button.configure(command=lambda: self.controller.show_frame("WalletPage"))

    def go_back(self):
        if self.controller.current_currency == "eth":
            self.controller.show_frame("EthWalletPage")
        else:
            self.controller.show_frame("WalletPage")

    def deploy_eth_contract(self):
        sol_source = self.sol_source.get("1.0", "end").strip()
        if not sol_source:
            messagebox.showerror("Error", "Please provide Solidity source code")
            return

        wallet = self.controller.current_wallet_obj
        if wallet is None or not hasattr(wallet, "deploy_contract"):
            messagebox.showerror("Error", "ETH wallet is not loaded")
            return

        try:
            fee_wei, gas_limit, contract_name, abi, bytecode = wallet.estimate_contract_deploy_fee(sol_source)
        except Exception as e:
            messagebox.showerror("Error", f"Unable to prepare contract deployment: {e}")
            return

        proceed = messagebox.askyesno(
            "Confirm Contract Deployment",
            f"Contract : {contract_name}\n"
            f"Gas limit: {gas_limit}\n"
            f"Fee      : {wei_to_eth(fee_wei):.6f} ETH  ({fmt_wei(fee_wei)})\n\n"
            f"Do you want to deploy it to Sepolia?",
        )
        if not proceed:
            return

        self.deploy_button.configure(state="disabled")
        self.eth_status.configure(text="Deploying contract, waiting for receipt...")

        def _deploy():
            try:
                result = wallet.deploy_contract(
                    sol_source=sol_source,
                    contract_name=contract_name,
                    abi=abi,
                    bytecode=bytecode,
                    gas_limit=gas_limit,
                )
            except Exception as e:
                self.after(0, lambda err=e: self._finish_eth_deploy_error(err))
                return
            self.after(0, lambda res=result: self._finish_eth_deploy_success(res))

        threading.Thread(target=_deploy, daemon=True).start()

    def _finish_eth_deploy_success(self, result: dict):
        self.deploy_button.configure(state="normal")
        self.eth_status.configure(text=f"Deployed: {result['contract_address']}")
        self.controller.contract_confirm_data = {
            "currency": "eth",
            "contract_name": result["contract_name"],
            "contract_addr": result["contract_address"],
            "tx_hash": result["tx_hash"],
            "fee_wei": result["fee_wei"],
            "gas_used": result["gas_used"],
            "gas_limit": result["gas_limit"],
            "explorer_address": f"https://sepolia.etherscan.io/address/{result['contract_address']}",
            "explorer_tx": f"https://sepolia.etherscan.io/tx/{result['tx_hash']}",
        }
        self.controller.get_frame("ContractConfirmPage").populate()
        self.controller.show_frame("ContractConfirmPage")

    def _finish_eth_deploy_error(self, error: Exception):
        self.deploy_button.configure(state="normal")
        self.eth_status.configure(text="Deployment failed")
        messagebox.showerror("Error", f"Contract deployment failed: {error}")

    def create_contract(self):
        secret = self.secret_text.get().strip()
        lock_time_text = self.lock_time.get().strip()
        amount_text = self.lock_amount.get().strip()

        if not secret or not lock_time_text or not amount_text:
            messagebox.showerror("Error", "Please complete all smart contract fields")
            return

        try:
            lock_minutes = int(lock_time_text)
            amount = int(amount_text)
        except ValueError:
            messagebox.showerror("Error", "Lock time and amount must be integers")
            return

        recipient = self.recipient_address.get().strip()
        if not recipient:
            messagebox.showerror("Error", "Please enter the recipient wallet address")
            return

        if lock_minutes <= 0 or amount <= 0:
            messagebox.showerror("Error", "Lock time and amount must be positive")
            return

        wallet = self.controller.current_wallet_obj
        if wallet is None:
            messagebox.showerror("Error", "Wallet is not loaded")
            return

        lock_blocks = max(1, (lock_minutes + 9) // 10)

        try:
            contract_addr, redeem_hex = wallet.create_htlc(
                secret_text=secret,
                lock_time_blocks=lock_blocks,
                amount=amount,
                recipient_addr=recipient,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create smart contract: {e}")
            return

        self.controller.contract_confirm_data = {
            "currency": "btc",
            "contract_addr": contract_addr,
            "redeem_hex": redeem_hex,
            "lock_minutes": lock_minutes,
            "lock_blocks": lock_blocks,
            "amount": amount,
            "recipient": recipient,
        }
        self.controller.get_frame("ContractConfirmPage").populate()
        self.controller.show_frame("ContractConfirmPage")

    def retrieve_contract(self):
        contract_addr = self.contract_address.get().strip()
        redeem_script_hex = self.redeem_script.get().strip()
        secret = self.redeem_secret.get().strip()

        if not contract_addr or not redeem_script_hex or not secret:
            messagebox.showerror("Error", "Please complete all retrieval fields")
            return

        wallet = self.controller.current_wallet_obj
        if wallet is None:
            messagebox.showerror("Error", "Wallet is not loaded")
            return

        try:
            tx_id = wallet.retrieve_from_htlc(
                contract_addr=contract_addr,
                redeem_script_hex=redeem_script_hex,
                secret_text=secret,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Retrieval failed: {e}")
            return

        if tx_id:
            messagebox.showinfo("Retrieved", f"Retrieval transaction broadcasted\nTXID: {tx_id}")
            self.controller.show_frame("WalletPage")
        else:
            messagebox.showerror("Error", "Retrieval broadcast failed")


# ---------------------------------------------------------------------------
# New Transaction page (unchanged)
# ---------------------------------------------------------------------------

class NewTxPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="New Transaction", font=(None, 30)).pack(pady=20)

        self.balance_label = ctk.CTkLabel(self.content, text="Balance: ?")
        self.balance_label.pack(pady=10)

        self.to = ctk.CTkEntry(self.content, placeholder_text="Target address", width=400)
        self.to.pack(pady=10)

        self.amount = ctk.CTkEntry(self.content, placeholder_text="Amount", width=400)
        self.amount.pack(pady=10)

        ctk.CTkButton(self.content, text="Create", command=self.send, width=200).pack(pady=10)
        ctk.CTkButton(self.content, text="Back",
                      command=lambda: controller.show_frame("WalletPage"), width=200).pack(pady=5)

    def on_show(self):
        self.refresh_balance()

    def refresh_balance(self):
        wallet = self.controller.current_wallet_obj
        if wallet is None:
            self.balance_label.configure(text="Balance: ?")
            return
        self.balance_label.configure(text=f"Balance: {wallet.satoshi} satoshi")

    def send(self):
        target_addr = self.to.get().strip()
        amount_text = self.amount.get().strip()

        if not target_addr or not amount_text:
            messagebox.showerror("Error", "Please enter destination address and amount")
            return

        try:
            amount = int(amount_text)
        except ValueError:
            messagebox.showerror("Error", "Amount must be an integer")
            return

        wallet = self.controller.current_wallet_obj
        if wallet is None:
            messagebox.showerror("Error", "Wallet is not loaded")
            return

        try:
            fee = wallet.estimate_fee(transfer_amount=amount)
        except Exception as e:
            messagebox.showerror("Error", f"Unable to estimate fee: {e}")
            return

        proceed = messagebox.askyesno("Confirm Transaction",
                                      f"Estimated fee: {fee} satoshi\n\nDo you want to continue?")
        if not proceed:
            return

        try:
            tx_id, fee = wallet.transfer_to(target_addr=target_addr, transfer_amount=amount)
            if tx_id:
                messagebox.showinfo("Success", f"Transaction broadcasted\nTXID: {tx_id}\nFee: {fee} satoshi")
            else:
                messagebox.showerror("Error", f"Transaction broadcast failed\nEstimated fee: {fee} satoshi")
        except Exception as e:
            messagebox.showerror("Error", f"Transaction failed: {e}")

        self.controller.show_frame("WalletPage")


# ---------------------------------------------------------------------------
# Transaction History page (unchanged)
# ---------------------------------------------------------------------------

class TxHistoryPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=20, pady=(20, 0))

        ctk.CTkLabel(header, text="Transaction History", font=(None, 30)).pack(side="left", padx=10)
        ctk.CTkButton(header, text="Refresh", command=self.load_history, width=120).pack(side="right", padx=10)
        ctk.CTkButton(header, text="Back",
                      command=lambda: controller.show_frame("WalletPage"), width=100).pack(side="right", padx=5)

        self.status_label = ctk.CTkLabel(self, text="", font=(None, 14))
        self.status_label.pack(pady=(5, 0))

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)

    def on_show(self):
        self.load_history()

    def load_history(self):
        wallet = self.controller.current_wallet_obj
        if wallet is None or not wallet.user_addr:
            self.status_label.configure(text="No wallet loaded.")
            return

        self.status_label.configure(text="Loading...")
        self.update_idletasks()

        for w in self.scroll_frame.winfo_children():
            w.destroy()

        try:
            txs = wallet.fetch_tx_history()
        except Exception as e:
            self.status_label.configure(text=f"Error fetching transactions: {e}")
            return

        if not txs:
            self.status_label.configure(text="No transactions found for this address.")
            return

        self.status_label.configure(text=f"{len(txs)} transaction(s) found")

        for tx in txs:
            txid = tx["txid"]
            confirmed = tx["confirmed"]
            tx_type = tx["type"]
            amount = tx["amount"]
            fee = tx["fee"]

            if tx_type == "incoming":
                type_label = "+ INCOMING"
                type_color = "#2ecc71"
            else:
                type_label = "- OUTGOING"
                type_color = "#e74c3c"

            fee_str = f"{fee} sat" if fee is not None else "—"

            card = ctk.CTkFrame(self.scroll_frame, corner_radius=8)
            card.pack(fill="x", pady=4, padx=4)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 4))

            ctk.CTkLabel(top, text=type_label, font=(None, 16, "bold"),
                         text_color=type_color, width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(top, text=f"{amount:,} sat", font=(None, 16, "bold"),
                         anchor="e").pack(side="right")

            bottom = ctk.CTkFrame(card, fg_color="transparent")
            bottom.pack(fill="x", padx=12, pady=(0, 10))

            short_txid = f"{txid[:16]}...{txid[-8:]}"
            ctk.CTkLabel(bottom, text=f"TXID: {short_txid}", font=(None, 11),
                         text_color="gray", anchor="w").pack(side="left")

            status_text = "Confirmed" if confirmed else "Unconfirmed"
            status_color = "#2ecc71" if confirmed else "#f39c12"
            ctk.CTkLabel(bottom, text=f"Fee: {fee_str}   |   {status_text}",
                         font=(None, 11), text_color=status_color, anchor="e").pack(side="right")


# ---------------------------------------------------------------------------
# Contract Confirm page
# ---------------------------------------------------------------------------

class ContractConfirmPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.title_label = ctk.CTkLabel(self.content, text="Contract Created", font=(None, 34, "bold"),
                                        text_color="#2ecc71")
        self.title_label.pack(pady=(20, 10))
        self.subtitle_label = ctk.CTkLabel(self.content, text="", font=(None, 14), text_color="gray")
        self.subtitle_label.pack(pady=(0, 20))

        self.addr_row = ctk.CTkFrame(self.content, fg_color="transparent")
        self.addr_row.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(self.addr_row, text="Contract Address", font=(None, 13), text_color="gray",
                     width=160, anchor="w").pack(side="left")
        self.addr_value = ctk.CTkLabel(self.addr_row, text="", font=(None, 14), anchor="w",
                                       wraplength=520, justify="left")
        self.addr_value.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(self.addr_row, text="📋", width=40, font=(None, 16),
                      command=lambda: self._copy(self.addr_value.cget("text"))).pack(side="left", padx=(8, 0))

        self.rs_row = ctk.CTkFrame(self.content, fg_color="transparent")
        self.rs_row.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(self.rs_row, text="Redeem Script", font=(None, 13), text_color="gray",
                     width=160, anchor="w").pack(side="left")
        self.rs_value = ctk.CTkLabel(self.rs_row, text="", font=(None, 14), anchor="w",
                                     wraplength=460, justify="left")
        self.rs_value.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(self.rs_row, text="📋", width=40, font=(None, 16),
                      command=lambda: self._copy(self.rs_value.cget("text"))).pack(side="left", padx=(8, 0))

        self.tx_row = self._detail_row("TX Hash")
        self.fee_row = self._detail_row("Fee")
        self.gas_row = self._detail_row("Gas")
        self.explorer_row = self._detail_row("Explorer")

        self.recipient_label = ctk.CTkLabel(self.content, text="", font=(None, 14))
        self.recipient_label.pack(pady=4)
        self.amount_label = ctk.CTkLabel(self.content, text="", font=(None, 14))
        self.amount_label.pack(pady=4)
        self.locktime_label = ctk.CTkLabel(self.content, text="", font=(None, 14))
        self.locktime_label.pack(pady=4)

        self.copy_all_button = ctk.CTkButton(self.content, text="Copy All",
                                             command=self.copy_all,
                                             width=240, font=(None, 18))
        self.copy_all_button.pack(pady=(24, 6))
        self.back_button = ctk.CTkButton(self.content, text="Back to Wallet",
                                         command=lambda: controller.show_frame("WalletPage"),
                                         width=240, font=(None, 20))
        self.back_button.pack(pady=(6, 20))

    def _detail_row(self, label: str):
        row = ctk.CTkFrame(self.content, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(row, text=label, font=(None, 13), text_color="gray",
                     width=160, anchor="w").pack(side="left")
        value = ctk.CTkLabel(row, text="", font=(None, 14), anchor="w",
                             wraplength=520, justify="left")
        value.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="📋", width=40, font=(None, 16),
                      command=lambda: self._copy(value.cget("text"))).pack(side="left", padx=(8, 0))
        return row, value

    def populate(self):
        data = self.controller.contract_confirm_data
        currency = data.get("currency", "btc")

        for row in (self.rs_row, self.tx_row[0], self.fee_row[0], self.gas_row[0], self.explorer_row[0]):
            row.pack_forget()
        for label in (self.recipient_label, self.amount_label, self.locktime_label):
            label.pack_forget()

        self.addr_value.configure(text=data["contract_addr"])
        self.addr_row.pack(fill="x", padx=20, pady=6, before=self.copy_all_button)

        if currency == "eth":
            self.title_label.configure(text="Ξ  Contract Deployed", text_color="#2ecc71")
            self.subtitle_label.configure(text="Save or copy the deployment details below.")
            self.tx_row[1].configure(text=data["tx_hash"])
            self.fee_row[1].configure(text=f"{wei_to_eth(data['fee_wei']):.6f} ETH  ({fmt_wei(data['fee_wei'])})")
            self.gas_row[1].configure(text=f"{data['gas_used']} used / {data['gas_limit']} limit")
            self.explorer_row[1].configure(text=f"{data['explorer_address']}\n{data['explorer_tx']}")
            for row in (self.tx_row[0], self.fee_row[0], self.gas_row[0], self.explorer_row[0]):
                row.pack(fill="x", padx=20, pady=6, before=self.copy_all_button)
            self.back_button.configure(command=lambda: self.controller.show_frame("EthWalletPage"))
            return

        self.title_label.configure(text="Contract Created", text_color="#2ecc71")
        self.subtitle_label.configure(text="Save the details below — you will need them to retrieve funds.")
        self.rs_value.configure(text=data["redeem_hex"])
        self.recipient_label.configure(text=f"Recipient:    {data['recipient']}")
        self.amount_label.configure(text=f"Amount:       {data['amount']:,} satoshi")
        self.locktime_label.configure(text=f"Lock time:    {data['lock_minutes']} minutes  ({data['lock_blocks']} blocks)")
        self.rs_row.pack(fill="x", padx=20, pady=6, before=self.copy_all_button)
        self.recipient_label.pack(pady=4, before=self.copy_all_button)
        self.amount_label.pack(pady=4, before=self.copy_all_button)
        self.locktime_label.pack(pady=4, before=self.copy_all_button)
        self.back_button.configure(command=lambda: self.controller.show_frame("WalletPage"))

    def copy_all(self):
        data = self.controller.contract_confirm_data
        if data.get("currency") == "eth":
            text = (
                f"Contract: {data['contract_name']}\n"
                f"Contract Address: {data['contract_addr']}\n"
                f"TX Hash: {data['tx_hash']}\n"
                f"Fee: {wei_to_eth(data['fee_wei']):.6f} ETH ({fmt_wei(data['fee_wei'])})\n"
                f"Gas: {data['gas_used']} used / {data['gas_limit']} limit\n"
                f"Explorer Address: {data['explorer_address']}\n"
                f"Explorer TX: {data['explorer_tx']}"
            )
        else:
            text = (
                f"Contract Address: {data['contract_addr']}\n"
                f"Redeem Script: {data['redeem_hex']}\n"
                f"Recipient: {data['recipient']}\n"
                f"Amount: {data['amount']} satoshi\n"
                f"Lock time: {data['lock_minutes']} minutes ({data['lock_blocks']} blocks)"
            )
        self._copy(text)

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Copied to clipboard")


if __name__ == "__main__":
    app = App()
    app.mainloop()
