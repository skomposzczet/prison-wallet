from tkinter import messagebox

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Modern Secure App")
        self.geometry("500x400")
        self.attributes("-type", "dialog")

        self.container = ctk.CTkFrame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.frames = {}

        for func in (LoginPage, DashboardPage):
            page_name = func.__name__
            frame = func(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginPage")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()


class LoginPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.label = ctk.CTkLabel(self, text="Member Login", font=("Mononoki Nerd Font", 35))
        self.label.pack(pady=30)

        self.username_entry = ctk.CTkEntry(self, width=250, placeholder_text="Username")
        self.username_entry.pack(pady=12)

        self.password_entry = ctk.CTkEntry(self, width=250, placeholder_text="Password", show="*")
        self.password_entry.pack(pady=12)

        self.button = ctk.CTkButton(self, text="Login", command=self.handle_login)
        self.button.pack(pady=24)

    def handle_login(self):
        # Basic validation
        user = self.username_entry.get()
        pw = self.password_entry.get()

        if user == "admin" and pw == "password":
            self.controller.show_frame("DashboardPage")
        else:
            messagebox.showerror("Login Failed", "Try 'admin' and 'password'")


class DashboardPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.input_var = ctk.StringVar(value="")
        self.result_var = ctk.StringVar(value="Result: 0")

        ctk.CTkLabel(self, text="Calculator Dashboard", font=("Roboto", 20, "bold")).pack(pady=20)
        ctk.CTkLabel(self, text="Enter a number:").pack(pady=(10, 0))
        self.entry = ctk.CTkEntry(self, textvariable=self.input_var, placeholder_text="Type here...")
        self.entry.pack(pady=10)
        self.input_var.trace_add("write", self.calculate)

        self.result_label = ctk.CTkLabel(
            self,
            textvariable=self.result_var,
            font=("Roboto", 16, "italic"),
            text_color="#1f6aa5",
        )
        self.result_label.pack(pady=20)

        ctk.CTkButton(self, text="Log Out", fg_color="gray", command=lambda: controller.show_frame("LoginPage")).pack(
            side="bottom", pady=20
        )

    def calculate(self, *args):
        current_value = self.input_var.get()

        try:
            if current_value == "":
                self.result_var.set("Result: 0")
            else:
                num = float(current_value)
                result = num * 2
                self.result_var.set(f"Result: {result}")
        except ValueError:
            self.result_var.set("Error: Please enter a number")


if __name__ == "__main__":
    app = App()
    app.mainloop()
