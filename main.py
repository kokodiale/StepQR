import qrcode
import dropbox
import customtkinter as ctk
from tkinter import filedialog, messagebox
from dropbox.exceptions import AuthError
from PIL import Image, ImageTk
import os
import re

# Dropbox API token
DROPBOX_TOKEN = 'your_dropbox_token_here'

generated_qr = None
qr_label = None
qr_image = None  # Przechowywanie referencji obrazu

def modify_dropbox_link(link):
    if "dropbox.com" in link:
        link = re.sub(r"dl=0$", "dl=1", link)
    return link

def generate_qr_code(data):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    return img

def generate_qr_from_link():
    global generated_qr
    link = entry_link.get()
    if not link:
        messagebox.showerror("Error", "Please enter a link to generate QR code")
        return
    
    generated_qr = generate_qr_code(link)
    display_qr()

def generate_qr_for_dropbox():
    global generated_qr
    dropbox_path = entry_dropbox.get()
    if not dropbox_path:
        messagebox.showerror("Error", "Please enter a Dropbox path to generate QR code")
        return
    
    dropbox_path = modify_dropbox_link(dropbox_path)
    generated_qr = generate_qr_code(dropbox_path)
    display_qr()

def display_qr():
    global generated_qr, qr_label, qr_image
    if generated_qr:
        qr_resized = generated_qr.resize((250, 250))
        qr_image = ImageTk.PhotoImage(qr_resized)
        
        if qr_label is None:
            qr_label = ctk.CTkLabel(frame, text="", image=qr_image)
            qr_label.image = qr_image
            qr_label.pack(pady=10)
        else:
            qr_label.configure(image=qr_image)
            qr_label.image = qr_image

def download_qr():
    global generated_qr
    if generated_qr:
        save_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png")])
        if save_path:
            generated_qr.save(save_path)
            messagebox.showinfo("Success", f"QR code saved at {save_path}")
    else:
        messagebox.showerror("Error", "No QR code generated yet")

# Tworzenie interfejsu
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

root = ctk.CTk()
root.geometry("500x600")
root.title("QR Code Generator")

frame = ctk.CTkFrame(root, corner_radius=10)
frame.pack(pady=20, padx=20, fill='both', expand=True)

label_link = ctk.CTkLabel(frame, text="Enter link for QR Code:", font=("Arial", 16))
label_link.pack(pady=5)

entry_link = ctk.CTkEntry(frame, width=300)
entry_link.pack(pady=10)

generate_link_button = ctk.CTkButton(frame, text="Generate QR Code from Link", command=generate_qr_from_link)
generate_link_button.pack(pady=10)

label_dropbox = ctk.CTkLabel(frame, text="Dropbox path (optional):", font=("Arial", 14))
label_dropbox.pack(pady=5)

entry_dropbox = ctk.CTkEntry(frame, width=300)
entry_dropbox.pack(pady=10)

generate_dropbox_button = ctk.CTkButton(frame, text="Generate QR Code for Dropbox Path", command=generate_qr_for_dropbox)
generate_dropbox_button.pack(pady=10)

download_button = ctk.CTkButton(frame, text="Download QR Code", command=download_qr)
download_button.pack(pady=20)

root.mainloop()
