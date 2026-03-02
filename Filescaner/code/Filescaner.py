"""
GUI-приложение для сканирования файлов по указанному пути.
"""
from __future__ import annotations

import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SEARCH_HISTORY_FILE = APP_DIR / "search_history.txt"


def scan_directory(path: str) -> list[dict]:
    """Рекурсивно сканирует директорию и возвращает список файлов с метаданными."""
    files = []
    path = path.strip()
    if not path:
        return files
    try:
        root = Path(path)
        if not root.exists():
            return []
        if not root.is_dir():
            try:
                stat = root.stat()
                return [{
                    "path": str(root),
                    "name": root.name,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "ext": root.suffix.lower(),
                }]
            except (OSError, PermissionError):
                return []
        for item in root.rglob("*"):
            if item.is_file():
                try:
                    stat = item.stat()
                    files.append({
                        "path": str(item),
                        "name": item.name,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "ext": item.suffix.lower(),
                    })
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError) as e:
        raise e
    return files


def open_file(path: str) -> None:
    """Открывает файл в ассоциированном приложении."""
    if os.name == "nt":
        os.startfile(path)
    else:
        import subprocess
        opener = "xdg-open" if os.name != "darwin" else "open"
        subprocess.run([opener, path], check=False)


class FileScannerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Сканер файлов")
        self.root.resizable(True, True)
        self.root.configure(bg="#1e1e1e")

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # Базовые цвета
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#e0e0e0")
        style.configure("TButton", background="#333333", foreground="#e0e0e0")
        style.configure("TCheckbutton", background="#1e1e1e", foreground="#e0e0e0")
        style.map("TButton", background=[("active", "#444444")])

        # Тёмные поля ввода и комбобокс сортировки
        style.configure(
            "Dark.TEntry",
            fieldbackground="#111111",
            background="#111111",
            foreground="#e0e0e0",
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground="#111111",
            background="#111111",
            foreground="#e0e0e0",
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#111111"), ("active", "#111111")],
            background=[("readonly", "#111111"), ("active", "#111111")],
            foreground=[("readonly", "#e0e0e0"), ("active", "#e0e0e0")],
        )

        # Тёмный скроллбар
        style.configure(
            "Dark.Vertical.TScrollbar",
            troughcolor="#111111",
            background="#333333",
            bordercolor="#111111",
            arrowcolor="#e0e0e0",
        )

        # Тёмные вкладки истории / файлов
        style.configure(
            "TNotebook",
            background="#1e1e1e",
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#333333",
            foreground="#e0e0e0",
            padding=(10, 3),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#444444"), ("active", "#3a3a3a")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )

        # Квадратное окно (например 600x600)
        size = 600
        self.root.geometry(f"{size}x{size}")

        self.files: list[dict] = []
        self._displayed_items: list[dict] = []
        self._selected_index: int | None = None
        self._search_history: list[str] = []
        self._run_history: list[str] = []
        self._sort_map = {"Имя": "name", "Дата изменения": "mtime", "Размер": "size", "Тип": "ext"}

        # Загрузка истории до создания интерфейса
        self._load_search_history()

        self.setup_ui()

    def setup_ui(self):
        # Строка поиска
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame, text="Путь:").pack(side=tk.LEFT, padx=(0, 5))
        self.path_var = tk.StringVar()
        self.entry = ttk.Entry(
            top_frame,
            textvariable=self.path_var,
            width=50,
            style="Dark.TEntry",
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.entry.bind("<Return>", lambda e: self.do_scan())

        ttk.Button(top_frame, text="Сканировать", command=self.do_scan).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(top_frame, text="Обзор...", command=self.browse_folder).pack(
            side=tk.LEFT
        )

        # Строка сортировки
        sort_frame = ttk.Frame(self.root, padding=(10, 0))
        sort_frame.pack(fill=tk.X)
        ttk.Label(sort_frame, text="Сортировка:").pack(side=tk.LEFT, padx=(0, 5))
        self.sort_var = tk.StringVar(value="Имя")
        sort_combo = ttk.Combobox(
            sort_frame,
            textvariable=self.sort_var,
            values=["Имя", "Дата изменения", "Размер", "Тип"],
            state="readonly",
            width=15,
            style="Dark.TCombobox",
        )
        sort_combo.pack(side=tk.LEFT, padx=5)
        sort_combo.bind("<<ComboboxSelected>>", self._on_sort_changed)
        self.sort_reverse_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            sort_frame,
            text="По убыванию",
            variable=self.sort_reverse_var,
            command=self._apply_sort,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(sort_frame, text="Открыть", command=self._open_selected).pack(
            side=tk.LEFT, padx=5
        )

        # Поиск по имени
        search_frame = ttk.Frame(self.root, padding=(10, 0))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Поиск по имени:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(
            search_frame,
            textvariable=self.search_var,
            style="Dark.TEntry",
        )
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        search_entry.bind("<KeyRelease>", lambda e: self._apply_sort())

        # Центр — вкладки
        center_frame = ttk.Frame(self.root, padding=10)
        center_frame.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(center_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Вкладка файлов
        files_tab = ttk.Frame(notebook)
        notebook.add(files_tab, text="Файлы")

        # Скроллбар и список для файлов
        list_frame = ttk.Frame(files_tab)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", style="Dark.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.text = tk.Text(
            list_frame,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 11),
            bg="#1e1e1e",
            fg="#e0e0e0",
            insertbackground="#e0e0e0",
            selectbackground="#444444",
            selectforeground="#e0e0e0",
            borderwidth=0,
            highlightthickness=0,
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.text.yview)
        self.text.config(state="disabled")
        self.text.bind("<Button-1>", self._on_text_click)
        self.text.bind("<Double-Button-1>", self._on_text_double_click)

        # Цветовые теги для отображения путей
        self.text.tag_configure("drive", foreground="#ffd700")   # жёлтый
        self.text.tag_configure("folder", foreground="#7CFC00")  # зелёный
        self.text.tag_configure("sep", foreground="#808080")
        self.text.tag_configure("filename", foreground="#ffffff")
        self.text.tag_configure("size", foreground="#aaaaaa")
        self.text.tag_configure("line", spacing1=2, spacing3=2)
        self.text.tag_configure("selected_line", background="#333333")

        # Вкладка истории поиска
        search_history_tab = ttk.Frame(notebook)
        notebook.add(search_history_tab, text="История поиска")
        self.search_history_text = tk.Text(
            search_history_tab,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#e0e0e0",
            insertbackground="#e0e0e0",
            borderwidth=0,
            highlightthickness=0,
        )
        self.search_history_text.pack(fill=tk.BOTH, expand=True)
        self.search_history_text.config(state="disabled")
        self._update_search_history_view()

        # Вкладка истории запусков
        run_history_tab = ttk.Frame(notebook)
        notebook.add(run_history_tab, text="История запусков")
        self.run_history_text = tk.Text(
            run_history_tab,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#e0e0e0",
            insertbackground="#e0e0e0",
            borderwidth=0,
            highlightthickness=0,
        )
        self.run_history_text.pack(fill=tk.BOTH, expand=True)
        self.run_history_text.config(state="disabled")

        # Статус и подпись внизу
        self.status_var = tk.StringVar(value="Введите путь и нажмите «Сканировать»")
        bottom_frame = ttk.Frame(self.root, padding=(5, 5))
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(
            bottom_frame,
            textvariable=self.status_var,
            anchor=tk.W,
        ).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(
            bottom_frame,
            text="Created by Lenicks",
            foreground="#ffd700",
            anchor=tk.E,
        ).pack(side=tk.RIGHT)

    def _format_size(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value):>5d} {unit}"
                return f"{value:>5.1f} {unit}"
            value /= 1024.0
        return f"{int(size):>5d} B"

    def _add_search_history(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        if path in self._search_history:
            self._search_history.remove(path)
        self._search_history.insert(0, path)
        self._search_history = self._search_history[:50]
        self._update_search_history_view()
        try:
            SEARCH_HISTORY_FILE.write_text(
                "\n".join(self._search_history),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _add_run_history(self, path: str) -> None:
        path = path.strip()
        if not path:
            return
        self._run_history.insert(0, path)
        self._run_history = self._run_history[:100]
        self._update_run_history_view()

    def _load_search_history(self) -> None:
        try:
            if SEARCH_HISTORY_FILE.exists():
                lines = SEARCH_HISTORY_FILE.read_text(encoding="utf-8").splitlines()
                self._search_history = [line.strip() for line in lines if line.strip()]
        except OSError:
            self._search_history = []

    def _update_search_history_view(self) -> None:
        if not hasattr(self, "search_history_text"):
            return
        self.search_history_text.config(state="normal")
        self.search_history_text.delete("1.0", tk.END)
        for item in self._search_history:
            self.search_history_text.insert(tk.END, item + "\n")
        self.search_history_text.config(state="disabled")

    def _update_run_history_view(self) -> None:
        if not hasattr(self, "run_history_text"):
            return
        self.run_history_text.config(state="normal")
        self.run_history_text.delete("1.0", tk.END)
        for item in self._run_history:
            self.run_history_text.insert(tk.END, item + "\n")
        self.run_history_text.config(state="disabled")

    def _on_sort_changed(self, event=None):
        self._apply_sort()

    def _render_files(self, files: list[dict]) -> None:
        self._displayed_items = list(files)
        self._selected_index = None
        self.text.config(state="normal")
        self.text.delete("1.0", tk.END)
        for item in self._displayed_items:
            self._insert_colored_path(item)
        self.text.tag_remove("selected_line", "1.0", tk.END)
        self.text.config(state="disabled")

    def _insert_colored_path(self, item: dict) -> None:
        # Раскрашиваем путь: диск (жёлтый), папки (зелёный), разделители (серый), файл (светлый)
        path = item["path"]
        drive, rest = os.path.splitdrive(path)
        if drive:
            self.text.insert(tk.END, drive, ("drive", "line"))
            self.text.insert(tk.END, "\\", ("sep", "line"))
            rest = rest.lstrip("\\/")
        else:
            rest = path.lstrip("\\/")
        parts = [p for p in re.split(r"[\\/]", rest) if p]
        for i, part in enumerate(parts):
            tag = "filename" if i == len(parts) - 1 else "folder"
            self.text.insert(tk.END, part, (tag, "line"))
            if i != len(parts) - 1:
                self.text.insert(tk.END, "\\", ("sep", "line"))
        # Добавляем размер файла справа
        size_str = self._format_size(item.get("size", 0))
        self.text.insert(tk.END, "   ", ("line",))
        self.text.insert(tk.END, size_str, ("size", "line"))
        self.text.insert(tk.END, "\n", ("line",))

    def _on_text_click(self, event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        line = int(index.split(".")[0]) - 1
        self._highlight_line(line)

    def _on_text_double_click(self, event) -> None:
        index = self.text.index(f"@{event.x},{event.y}")
        line = int(index.split(".")[0]) - 1
        self._highlight_line(line)
        self._open_by_line(line)

    def _highlight_line(self, line: int) -> None:
        self.text.tag_remove("selected_line", "1.0", tk.END)
        if line < 0 or line >= len(self._displayed_items):
            self._selected_index = None
            return
        self._selected_index = line
        start = f"{line + 1}.0"
        end = f"{line + 1}.end"
        self.text.tag_add("selected_line", start, end)

    def _open_by_line(self, line: int) -> None:
        if line < 0 or line >= len(self._displayed_items):
            return
        path = self._displayed_items[line]["path"]
        try:
            open_file(path)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл:\n{e}")
        else:
            self._add_run_history(path)

    def _apply_sort(self):
        key = self._sort_map.get(self.sort_var.get(), "name")
        reverse = self.sort_reverse_var.get()
        if not self.files:
            self._render_files([])
            self.status_var.set("Показано файлов: 0 из 0")
            return
        # Фильтрация по подстроке имени (без учёта регистра)
        query = ""
        if hasattr(self, "search_var"):
            query = self.search_var.get().strip().lower()
        if query:
            filtered = [f for f in self.files if query in f["name"].lower()]
        else:
            filtered = list(self.files)
        if not filtered:
            self._render_files([])
            self.status_var.set(f"Показано файлов: 0 из {len(self.files)}")
            return
        if key == "name":
            sort_key = lambda f: f["name"].lower()
        elif key == "mtime":
            sort_key = lambda f: f["mtime"]
        elif key == "size":
            sort_key = lambda f: f["size"]
        else:  # ext
            sort_key = lambda f: (f["ext"] or "\uffff", f["name"].lower())
        sorted_files = sorted(filtered, key=sort_key, reverse=reverse)
        self._render_files(sorted_files)
        self.status_var.set(f"Показано файлов: {len(sorted_files)} из {len(self.files)}")

    def _open_selected(self):
        if not self._displayed_items:
            messagebox.showinfo("Подсказка", "Сначала отсканируйте файлы.")
            return
        if self._selected_index is not None:
            line = self._selected_index
        else:
            index = self.text.index("insert")
            line = int(index.split(".")[0]) - 1
        if line < 0 or line >= len(self._displayed_items):
            messagebox.showinfo(
                "Подсказка",
                "Щёлкните по файлу в списке и повторите попытку.",
            )
            return
        self._open_by_line(line)

    def browse_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder:
            self.path_var.set(folder)
            self.do_scan()

    def do_scan(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning("Внимание", "Введите путь к папке.")
            return

        self._add_search_history(path)
        self._render_files([])
        self.status_var.set("Сканирование...")
        self.root.update()

        try:
            self.files = scan_directory(path)
            self._apply_sort()
            self.status_var.set(f"Найдено файлов: {len(self.files)}")
        except PermissionError:
            messagebox.showerror(
                "Ошибка",
                "Нет доступа к указанной папке.",
            )
            self.status_var.set("Ошибка доступа")
        except OSError as e:
            messagebox.showerror("Ошибка", str(e))
            self.status_var.set("Ошибка")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            self.status_var.set("Ошибка")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = FileScannerApp()
    app.run()
