import os
from tkinter import messagebox
import customtkinter as ctk

from main import Wallet

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Prison Wallet")
        self.geometry("1200x900")
        self.minsize(900, 650)
        self.resizable(True, True)

        self.current_user = None
        self.current_password = None
        self.current_wallet = None
        self.current_wallet_obj = None

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}

        for F in (LoginPage, RegisterPage, ProfilePage, NewWalletPage, WalletPage, SmartContractPage, NewTxPage):
            frame = F(self.container, self)
            self.frames[F.__name__] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginPage")

    def show_frame(self, name):
        self.frames[name].tkraise()

    def user_dir(self):
        return os.path.join(os.getcwd(), ".prison-wallet", self.current_user)

    def wallets_dir(self):
        return os.path.join(self.user_dir(), "wallets")

    def password_file(self):
        return os.path.join(self.user_dir(), "password.txt")


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
        wallets = os.path.join(base_user, "wallets")
        pw_file = os.path.join(base_user, "password.txt")

        if os.path.exists(base_user):
            messagebox.showerror("Error", "User already exists")
            return

        os.makedirs(wallets, exist_ok=True)

        with open(pw_file, "w") as f:
            f.write(password)

        messagebox.showinfo("Success", "User created")
        self.controller.show_frame("LoginPage")


class ProfilePage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.label = ctk.CTkLabel(self.content, text="Profile", font=(None, 30))
        self.label.pack(pady=10)

        self.wallets_frame = ctk.CTkFrame(self.content)
        self.wallets_frame.pack(pady=10)

        ctk.CTkButton(self.content, text="New Wallet", command=lambda: controller.show_frame("NewWalletPage"), width=200).pack(pady=5)
        ctk.CTkButton(self.content, text="Logout", command=lambda: controller.show_frame("LoginPage"), width=200).pack(pady=5)

        self.bind("<Visibility>", lambda e: self.refresh())

    def refresh(self):
        for w in self.wallets_frame.winfo_children():
            w.destroy()

        path = self.controller.wallets_dir()
        os.makedirs(path, exist_ok=True)

        for fname in sorted(os.listdir(path)):
            wallet_path = os.path.join(path, fname)
            if not os.path.isdir(wallet_path):
                continue
            btn = ctk.CTkButton(self.wallets_frame, text=fname,
                                command=lambda f=fname: self.open_wallet(f))
            btn.pack(pady=5)

    def open_wallet(self, fname):
        self.controller.current_wallet = fname
        self.controller.show_frame("WalletPage")


class NewWalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="Create / Import Wallet", font=(None, 30)).pack(pady=20)

        self.name = ctk.CTkEntry(self.content, placeholder_text="Wallet name", width=400)
        self.name.pack(pady=10)

        self.wif = ctk.CTkEntry(self.content, placeholder_text="Existing WIF (optional)", width=400)
        self.wif.pack(pady=10)

        self.import_button = ctk.CTkButton(self.content, text="Import Wallet", command=self.import_wallet, width=220)
        self.import_button.pack(pady=5)

        self.generate_button = ctk.CTkButton(self.content, text="Generate New Wallet", command=self.create_wallet, width=220)
        self.generate_button.pack(pady=5)

        ctk.CTkButton(self.content, text="Back", command=lambda: controller.show_frame("ProfilePage"), width=220).pack(pady=5)

    def create_wallet(self):
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a wallet name")
            return

        path = os.path.join(self.controller.wallets_dir(), name)
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

        path = os.path.join(self.controller.wallets_dir(), name)
        if os.path.exists(path):
            messagebox.showerror("Error", "Wallet already exists")
            return

        try:
            _, address = Wallet.import_from_wif(password=self.controller.current_password, wif=wif, output_dir=path)
            messagebox.showinfo("Success", f"Wallet imported\nAddress: {address}")
            self.controller.show_frame("ProfilePage")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import wallet: {e}")


class WalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.loaded_address = ""

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        self.label = ctk.CTkLabel(self.content, text="Wallet", font=(None, 60))
        self.label.pack(pady=10)

        self.address_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        self.address_frame.pack(fill="x", pady=10, padx=20)

        self.address_label = ctk.CTkLabel(self.address_frame, text="Address: ?", anchor="w", justify="left", font=(None, 36))
        self.address_label.pack(side="left", fill="x", expand=True)

        self.copy_button = ctk.CTkButton(self.address_frame, text="📋", command=self.copy_address, width=40, state="disabled", font=(None, 24))
        self.copy_button.pack(side="left", padx=10)

        self.balance_label = ctk.CTkLabel(self.content, text="Balance: 0", font=(None, 36))
        self.balance_label.pack(pady=10)

        ctk.CTkButton(self.content, text="Create Transaction", command=lambda: controller.show_frame("NewTxPage"), width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Create Smart Contract", command=lambda: controller.show_frame("SmartContractPage"), width=240, font=(None, 24)).pack(pady=5)
        ctk.CTkButton(self.content, text="Back", command=lambda: controller.show_frame("ProfilePage"), width=240, font=(None, 24)).pack(pady=5)

        self.bind("<Visibility>", lambda e: self.load_wallet())

    def load_wallet(self):
        if not self.controller.current_wallet:
            self.balance_label.configure(text="Balance: ?")
            self.address_label.configure(text="Address: ?")
            self.copy_button.configure(state="disabled")
            return

        wallet_dir = os.path.join(self.controller.wallets_dir(), self.controller.current_wallet)
        try:
            wallet = Wallet()
            wallet.load_user_keys(password=self.controller.current_password, wallet_dir=wallet_dir)
            self.controller.current_wallet_obj = wallet
            balance = wallet.satoshi
            address = wallet.user_addr or ""
            self.loaded_address = address
            self.balance_label.configure(text=f"Balance: {balance} satoshi")
            self.label.configure(text=f"Wallet: {self.controller.current_wallet}")
            self.address_label.configure(text=f"Address: {address}")
            self.copy_button.configure(state="normal" if address else "disabled")
        except Exception as e:
            messagebox.showerror("Error", f"Unable to load wallet: {e}")
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


class SmartContractPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.content = ctk.CTkFrame(self)
        self.content.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(self.content, text="New Smart Contract", font=(None, 30)).pack(pady=20)

        self.secret_text = ctk.CTkEntry(self.content, placeholder_text="Secret text", width=500)
        self.secret_text.pack(pady=10)

        self.recipient_address = ctk.CTkEntry(self.content, placeholder_text="Recipient wallet address", width=500)
        self.recipient_address.pack(pady=10)

        self.lock_time = ctk.CTkEntry(self.content, placeholder_text="Lock time (minutes)", width=500)
        self.lock_time.pack(pady=10)

        self.lock_amount = ctk.CTkEntry(self.content, placeholder_text="Amount to lock (satoshi)", width=500)
        self.lock_amount.pack(pady=10)

        ctk.CTkButton(self.content, text="Create Contract", command=self.create_contract, width=240).pack(pady=10)

        ctk.CTkLabel(self.content, text="Retrieve Contract", font=(None, 24)).pack(pady=20)

        self.contract_address = ctk.CTkEntry(self.content, placeholder_text="Contract address", width=500)
        self.contract_address.pack(pady=10)

        self.redeem_script = ctk.CTkEntry(self.content, placeholder_text="Redeem script hex", width=500)
        self.redeem_script.pack(pady=10)

        self.redeem_secret = ctk.CTkEntry(self.content, placeholder_text="Secret text", width=500)
        self.redeem_secret.pack(pady=10)

        ctk.CTkButton(self.content, text="Retrieve Contract", command=self.retrieve_contract, width=240).pack(pady=10)
        ctk.CTkButton(self.content, text="Back", command=lambda: controller.show_frame("WalletPage"), width=240).pack(pady=5)

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

        messagebox.showinfo(
            "Smart Contract Created",
            f"Contract Address: {contract_addr}\nRedeem Script: {redeem_hex}\nLock time: {lock_minutes} minutes ({lock_blocks} blocks)\nAmount: {amount} satoshi"
        )
        self.controller.show_frame("WalletPage")

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
        ctk.CTkButton(self.content, text="Back", command=lambda: controller.show_frame("WalletPage"), width=200).pack(pady=5)

        self.bind("<Visibility>", lambda e: self.refresh_balance())

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

        proceed = messagebox.askyesno("Confirm Transaction", f"Estimated fee: {fee} satoshi\n\nDo you want to continue?")
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


if __name__ == "__main__":
    app = App()
    app.mainloop()

