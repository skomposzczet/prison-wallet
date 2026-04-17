import os
from tkinter import messagebox
import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def generate_wallet_stub():
    return {
        "address": "stub_address",
        "wif": "stub_wif"
    }

def get_balance_stub(address):
    return 0.0

def create_transaction_stub(from_addr, to_addr, amount):
    pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Prison Wallet")
        self.geometry("1200x900")

        self.current_user = None
        self.current_wallet = None

        self.container = ctk.CTkFrame(self)
        self.container.pack(fill="both", expand=True)

        self.frames = {}

        for F in (LoginPage, RegisterPage, ProfilePage, NewWalletPage, WalletPage, NewTxPage):
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

        ctk.CTkLabel(self, text="Login", font=(None, 30)).pack(pady=20)

        self.user = ctk.CTkEntry(self, placeholder_text="Username")
        self.user.pack(pady=10)

        self.pw = ctk.CTkEntry(self, placeholder_text="Password", show="*")
        self.pw.pack(pady=10)

        ctk.CTkButton(self, text="Login", command=self.login).pack(pady=10)
        ctk.CTkButton(self, text="Register", command=lambda: controller.show_frame("RegisterPage")).pack(pady=5)

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
            self.controller.show_frame("ProfilePage")
        else:
            messagebox.showerror("Error", "Wrong password")


class RegisterPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ctk.CTkLabel(self, text="Register", font=(None, 30)).pack(pady=20)

        self.user = ctk.CTkEntry(self, placeholder_text="Username")
        self.user.pack(pady=10)

        self.pw = ctk.CTkEntry(self, placeholder_text="Password", show="*")
        self.pw.pack(pady=10)

        ctk.CTkButton(self, text="Create", command=self.register).pack(pady=10)
        ctk.CTkButton(self, text="Back", command=lambda: controller.show_frame("LoginPage")).pack(pady=5)

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

        self.label = ctk.CTkLabel(self, text="Profile", font=(None, 30))
        self.label.pack(pady=10)

        self.wallets_frame = ctk.CTkFrame(self)
        self.wallets_frame.pack(fill="both", expand=True, pady=10)

        ctk.CTkButton(self, text="New Wallet", command=lambda: controller.show_frame("NewWalletPage")).pack(pady=5)
        ctk.CTkButton(self, text="Logout", command=lambda: controller.show_frame("LoginPage")).pack(pady=5)

        self.bind("<Visibility>", lambda e: self.refresh())

    def refresh(self):
        for w in self.wallets_frame.winfo_children():
            w.destroy()

        path = self.controller.wallets_dir()
        os.makedirs(path, exist_ok=True)

        for fname in os.listdir(path):
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

        ctk.CTkLabel(self, text="Create Wallet", font=(None, 30)).pack(pady=20)

        self.name = ctk.CTkEntry(self, placeholder_text="Wallet name")
        self.name.pack(pady=10)

        ctk.CTkButton(self, text="Generate", command=self.create_wallet).pack(pady=10)
        ctk.CTkButton(self, text="Back", command=lambda: controller.show_frame("ProfilePage")).pack(pady=5)

    def create_wallet(self):
        name = self.name.get()
        data = generate_wallet_stub()

        path = os.path.join(self.controller.wallets_dir(), name)
        os.makedirs(path, exist_ok=True)

        with open(os.path.join(path, "wallet.txt"), "w") as f:
            f.write(f"address:{data['address']}\n")
            f.write(f"wif:{data['wif']}\n")

        messagebox.showinfo("Success", "Wallet created")
        self.controller.show_frame("ProfilePage")


class WalletPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.label = ctk.CTkLabel(self, text="Wallet", font=(None, 30))
        self.label.pack(pady=10)

        self.balance_label = ctk.CTkLabel(self, text="Balance: 0")
        self.balance_label.pack(pady=10)

        ctk.CTkButton(self, text="Send", command=lambda: controller.show_frame("NewTxPage")).pack(pady=5)
        ctk.CTkButton(self, text="Back", command=lambda: controller.show_frame("ProfilePage")).pack(pady=5)

        self.bind("<Visibility>", lambda e: self.load_wallet())

    def load_wallet(self):
        wallet_path = os.path.join(self.controller.wallets_dir(), self.controller.current_wallet, "wallet.txt")

        address = ""
        if os.path.exists(wallet_path):
            with open(wallet_path) as f:
                for line in f:
                    if line.startswith("address:"):
                        address = line.strip().split(":")[1]

        balance = get_balance_stub(address)
        self.balance_label.configure(text=f"Balance: {balance}")


class NewTxPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        ctk.CTkLabel(self, text="New Transaction", font=(None, 30)).pack(pady=20)

        self.to = ctk.CTkEntry(self, placeholder_text="Target address")
        self.to.pack(pady=10)

        self.amount = ctk.CTkEntry(self, placeholder_text="Amount")
        self.amount.pack(pady=10)

        ctk.CTkButton(self, text="Send", command=self.send).pack(pady=10)
        ctk.CTkButton(self, text="Back", command=lambda: controller.show_frame("WalletPage")).pack(pady=5)

    def send(self):
        to = self.to.get()
        amount = self.amount.get()

        create_transaction_stub(None, to, amount)
        messagebox.showinfo("Stub", "Transaction created (stub)")
        self.controller.show_frame("WalletPage")


if __name__ == "__main__":
    app = App()
    app.mainloop()

