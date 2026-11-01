#!/usr/bin/env python3
"""Small desktop application for creating DNS Intent signature bundles."""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pydantic import ValidationError

from scripts.create_commit import create_bundle, load_private_key, read_intent
from scripts.create_panic_signature import create_panic_bundle, read_panic_change


APP_TITLE = "DNS Intent Signing"
NORMAL_SIGNATURE = "Standard signature"
PANIC_SIGNATURE = "Panic signature"


def sign_file(signature_type: str, input_path: str, output_path: str, private_key: str) -> None:
    """Validate the form values, create a bundle, and write it to disk."""
    if not input_path:
        raise ValueError("The input JSON file path is required.")
    if not output_path:
        raise ValueError("The output JSON file path is required.")

    source = Path(input_path).expanduser()
    destination = Path(output_path).expanduser()

    if not private_key.strip():
        raise ValueError("The private key is required.")
    if not source.is_file():
        raise ValueError("The input JSON file does not exist or is not a file.")
    if source.resolve() == destination.resolve():
        raise ValueError("The input and output files must be different.")
    if not destination.parent.is_dir():
        raise ValueError("The output folder does not exist.")

    key = load_private_key(private_key.strip())
    if signature_type == NORMAL_SIGNATURE:
        intent = read_intent(str(source))
        bundle = create_bundle(intent, key, intent_file=source.name)
    elif signature_type == PANIC_SIGNATURE:
        change = read_panic_change(str(source))
        bundle = create_panic_bundle(change, key)
    else:
        raise ValueError("Unknown signature type.")

    destination.write_text(
        f"{json.dumps(bundle, indent=2, ensure_ascii=False)}\n",
        encoding="utf-8",
    )


class SignatureApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x420")
        self.minsize(620, 390)

        self.signature_type = tk.StringVar(value=NORMAL_SIGNATURE)
        self.private_key = tk.StringVar()
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.show_key = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready to sign.")
        self._output_was_suggested = True

        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=24)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        ttk.Label(root, text=APP_TITLE, font=("Segoe UI", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(
            root,
            text="Choose a signature type, private key, and JSON files.",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 20))

        ttk.Label(root, text="Signature type").grid(row=2, column=0, sticky="w", padx=(0, 16))
        types = ttk.Frame(root)
        types.grid(row=2, column=1, columnspan=2, sticky="w")
        for value in (NORMAL_SIGNATURE, PANIC_SIGNATURE):
            ttk.Radiobutton(
                types,
                text=value,
                value=value,
                variable=self.signature_type,
                command=self._signature_type_changed,
            ).pack(side="left", padx=(0, 18))

        ttk.Label(root, text="Private key").grid(row=3, column=0, sticky="w", padx=(0, 16), pady=14)
        self.key_entry = ttk.Entry(root, textvariable=self.private_key, show="•")
        self.key_entry.grid(row=3, column=1, sticky="ew", pady=14)
        ttk.Checkbutton(
            root,
            text="Show",
            variable=self.show_key,
            command=self._toggle_key_visibility,
        ).grid(row=3, column=2, sticky="w", padx=(10, 0), pady=14)

        ttk.Label(root, text="Input JSON").grid(row=4, column=0, sticky="w", padx=(0, 16))
        ttk.Entry(root, textvariable=self.input_path).grid(row=4, column=1, sticky="ew")
        ttk.Button(root, text="Browse…", command=self._select_input).grid(
            row=4, column=2, padx=(10, 0)
        )

        ttk.Label(root, text="Output JSON").grid(row=5, column=0, sticky="w", padx=(0, 16), pady=14)
        output_entry = ttk.Entry(root, textvariable=self.output_path)
        output_entry.grid(row=5, column=1, sticky="ew", pady=14)
        output_entry.bind("<Key>", lambda _event: self._mark_output_edited())
        ttk.Button(root, text="Save as…", command=self._select_output).grid(
            row=5, column=2, padx=(10, 0), pady=14
        )

        ttk.Separator(root).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(8, 18))
        ttk.Label(root, textvariable=self.status).grid(row=7, column=0, columnspan=2, sticky="w")
        self.sign_button = ttk.Button(root, text="Sign JSON", command=self._sign)
        self.sign_button.grid(row=7, column=2, sticky="e")

        root.rowconfigure(8, weight=1)
        self.key_entry.focus_set()

    def _toggle_key_visibility(self) -> None:
        self.key_entry.configure(show="" if self.show_key.get() else "•")

    def _suggest_output(self) -> None:
        raw_path = self.input_path.get().strip()
        if not raw_path:
            return
        source = Path(raw_path)
        suffix = "panic-signature" if self.signature_type.get() == PANIC_SIGNATURE else "signing-bundle"
        self.output_path.set(str(source.with_name(f"{source.stem}-{suffix}.json")))
        self._output_was_suggested = True

    def _signature_type_changed(self) -> None:
        if self._output_was_suggested:
            self._suggest_output()

    def _mark_output_edited(self) -> None:
        self._output_was_suggested = False

    def _select_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select input JSON",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if selected:
            self.input_path.set(selected)
            if self._output_was_suggested or not self.output_path.get().strip():
                self._suggest_output()

    def _select_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Select output JSON",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
            initialfile=Path(self.output_path.get()).name if self.output_path.get() else "signature.json",
        )
        if selected:
            self.output_path.set(selected)
            self._output_was_suggested = False

    def _sign(self) -> None:
        self.status.set("Signing…")
        self.sign_button.configure(state="disabled")
        self.update_idletasks()
        try:
            sign_file(
                self.signature_type.get(),
                self.input_path.get().strip(),
                self.output_path.get().strip(),
                self.private_key.get(),
            )
        except (OSError, ValueError, ValidationError) as exc:
            self.status.set("Signing failed.")
            messagebox.showerror(APP_TITLE, str(exc), parent=self)
        else:
            output = str(Path(self.output_path.get().strip()).resolve())
            self.status.set(f"Signature saved: {output}")
            messagebox.showinfo(APP_TITLE, f"Signature successfully saved to:\n{output}", parent=self)
        finally:
            self.sign_button.configure(state="normal")


def main() -> None:
    SignatureApp().mainloop()


if __name__ == "__main__":
    main()
