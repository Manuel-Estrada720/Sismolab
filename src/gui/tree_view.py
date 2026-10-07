"""Drawing of the AVL and the BST on a Tkinter Canvas.

Layout: x = position of the node in the inorder traversal, y = depth.
In a search tree the inorder is sorted, so two nodes never overlap.
"""

import tkinter as tk
from tkinter import ttk

from .common import (COSTLY_COLOR, MOVED_COLOR, PRIORITY_COLORS, UNBALANCED_COLOR,
                     one_decimal, sis)

X_GAP = 40      # horizontal space between two inorder positions
Y_GAP = 74      # vertical space between two levels
RADIUS = 16     # node circle size
MARGIN = 40
TITLE_SPACE = 34


def lighter(color):
    """Mix a colour with white: reviewed events are drawn lighter."""
    red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return "#%02x%02x%02x" % ((red + 255 * 2) // 3, (green + 255 * 2) // 3, (blue + 255 * 2) // 3)


class TreeView(ttk.Frame):

    def __init__(self, parent, on_select):
        super().__init__(parent)
        self.on_select = on_select      # function(event_id) called on a click
        self.view = None                # last state_view()
        self.selected = None
        self.zoom = 1.0
        self.last_size = -1

        # ---- toolbar ----
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 4))
        ttk.Label(bar, text="Árbol:").pack(side="left")
        self.choice = tk.StringVar(value="AVL")
        selector = ttk.Combobox(bar, textvariable=self.choice, values=["AVL", "BST", "Ambos"],
                                width=7, state="readonly")
        selector.pack(side="left", padx=4)
        selector.bind("<<ComboboxSelected>>", lambda e: self.fit())
        ttk.Button(bar, text="-", width=3, command=lambda: self.change_zoom(0.8)).pack(side="left")
        self.zoom_label = ttk.Label(bar, text="100%", width=6, anchor="center")
        self.zoom_label.pack(side="left")
        ttk.Button(bar, text="+", width=3, command=lambda: self.change_zoom(1.25)).pack(side="left")
        ttk.Button(bar, text="Ajustar", command=self.fit).pack(side="left", padx=4)
        ttk.Button(bar, text="100%", command=self.reset_zoom).pack(side="left")
        self.stress_label = ttk.Label(bar, text="", foreground=UNBALANCED_COLOR)
        self.stress_label.pack(side="left", padx=8)

        # ---- canvas with both scrollbars ----
        area = ttk.Frame(self)
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, background="white", highlightthickness=1,
                                highlightbackground="#ddd6c8")
        y_scroll = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        x_scroll = ttk.Scrollbar(area, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="we")
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)

        # Click on a node; wheel = scroll, Ctrl + wheel = zoom
        self.canvas.tag_bind("node", "<Button-1>", self._on_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        self.canvas.bind("<Shift-MouseWheel>",
                         lambda e: self.canvas.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.canvas.bind("<Control-MouseWheel>",
                         lambda e: self.change_zoom(1.25 if e.delta > 0 else 0.8))

        self._legend()

    def _legend(self):
        legend = tk.Canvas(self, height=62, background="#fffdf8", highlightthickness=0)
        legend.pack(fill="x", pady=(4, 0))

        def item(x, y, draw_mark, text):
            # Draw the mark, then the text, and return where the next item starts
            draw_mark(x, y)
            label = legend.create_text(x + 18, y + 6, text=text, anchor="w")
            return legend.bbox(label)[2] + 16

        x = 10
        for priority, name in ((1, "baja"), (2, "media"), (3, "alta")):
            color = PRIORITY_COLORS[priority]
            x = item(x, 6, lambda a, b, c=color: legend.create_oval(a, b, a + 12, b + 12, fill=c, outline=""),
                     "Prioridad " + name)
        item(x, 6, lambda a, b: legend.create_oval(a, b, a + 12, b + 12, outline=COSTLY_COLOR, width=3),
             "Acceso costoso (alta y prof. > L)")
        x = 10
        x = item(x, 24, lambda a, b: legend.create_oval(a, b, a + 12, b + 12, outline="#1f2430", width=2,
                                                         dash=(2, 2)), "Raíz")
        x = item(x, 24, lambda a, b: legend.create_oval(a, b, a + 12, b + 12, outline=MOVED_COLOR, width=3),
                 "Movido en la última acción")
        item(x, 24, lambda a, b: legend.create_rectangle(a, b, a + 14, b + 12, fill=UNBALANCED_COLOR, outline=""),
             "Desbalance (estrés)")
        legend.create_text(10, 50, anchor="w", fill="#6b7180",
                           text="Número = ID · debajo = M · más claro = revisado · clic = detalle · Ctrl + rueda = zoom")

    # ---------------------------------------------------------------- zoom

    def change_zoom(self, factor):
        self.zoom = min(2.5, max(0.05, self.zoom * factor))
        self.draw()

    def reset_zoom(self):
        self.zoom = 1.0
        self.draw()

    def _width_of(self, tree):
        return MARGIN * 2 + max(len(tree["nodes"]) - 1, 0) * X_GAP

    def fit(self):
        """Zoom that makes the whole tree fit in the visible width."""
        if self.view is None:
            return
        tree = self.view["bst"] if self.choice.get() == "BST" else self.view["avl"]
        available = max(self.canvas.winfo_width() - 20, 300)
        self.zoom = min(1.0, max(0.05, available / max(self._width_of(tree), 1)))
        self.draw()

    # ---------------------------------------------------------------- drawing

    def show(self, view, selected):
        self.view = view
        self.selected = selected
        if view["avl"]["size"] != self.last_size:
            # The tree grew or shrank: choose a zoom that shows it whole
            self.last_size = view["avl"]["size"]
            self.update_idletasks()
            self.fit()
        else:
            self.draw()

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        self.zoom_label.configure(text=str(round(self.zoom * 100)) + "%")
        if self.view is None:
            return
        if self.view["mode"] == "STRESS":
            self.stress_label.configure(text="Modo estrés: " + str(self.view["indicators"]["unbalanced"])
                                        + " nodo(s) sin condición AVL")
        else:
            self.stress_label.configure(text="")

        top = 10
        width = 0
        if self.choice.get() != "BST":
            top, used = self._draw_tree("AVL", self.view["avl"], top, True)
            width = max(width, used)
        if self.choice.get() != "AVL":
            top, used = self._draw_tree("BST de comparación", self.view["bst"], top + 20, False)
            width = max(width, used)
        canvas.configure(scrollregion=(0, 0, width + 20, top + 20))

    def _draw_tree(self, title, tree, top, is_avl):
        """Draw one tree starting at y = top. Returns (bottom y, width used)."""
        canvas = self.canvas
        z = self.zoom
        root = sis(tree["root"]) if tree["root"] is not None else "—"
        header = (title + "   tamaño " + str(tree["size"]) + " · altura " + str(tree["height"])
                  + " · hojas " + str(tree["leaves"]) + " · raíz " + root)
        canvas.create_text(10, top + 10, text=header, anchor="w", font=("TkDefaultFont", 10, "bold"))
        if not tree["nodes"]:
            canvas.create_text(10, top + 36, text="El árbol está vacío.", anchor="w", fill="#6b7180")
            return top + 60, 300

        # 1. Where each node goes
        position = {}
        for node in tree["nodes"]:
            x = (MARGIN + node["inorder"] * X_GAP) * z
            y = top + TITLE_SPACE + (MARGIN / 2 + node["depth"] * Y_GAP) * z
            position[node["id"]] = (x, y)

        # 2. Edges first, so the circles are drawn over them
        for node in tree["nodes"]:
            for child in (node["left"], node["right"]):
                if child is not None:
                    x1, y1 = position[node["id"]]
                    x2, y2 = position[child]
                    canvas.create_line(x1, y1, x2, y2, fill="#9b9488")

        # 3. Nodes
        r = RADIUS * z
        show_text = z >= 0.45
        for node in tree["nodes"]:
            x, y = position[node["id"]]
            tags = ("node", "id:" + str(node["id"]))
            color = PRIORITY_COLORS[node["priority"]]
            if node["attention"] == "REVIEWED":
                color = lighter(color)
            if node["moved"]:
                canvas.create_oval(x - r - 7 * z, y - r - 7 * z, x + r + 7 * z, y + r + 7 * z,
                                   outline=MOVED_COLOR, width=max(1, 3 * z), tags=tags)
            if node["id"] == tree["root"]:
                canvas.create_oval(x - r - 4 * z, y - r - 4 * z, x + r + 4 * z, y + r + 4 * z,
                                   outline="#1f2430", width=2, dash=(3, 2), tags=tags)
            outline = "#1f2430" if node["id"] == self.selected else "white"
            width = 3 if node["id"] == self.selected else 1
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=outline, width=width, tags=tags)
            if node["costly"]:
                canvas.create_oval(x - r - 2 * z, y - r - 2 * z, x + r + 2 * z, y + r + 2 * z,
                                   outline=COSTLY_COLOR, width=max(1.5, 3 * z), tags=tags)
                canvas.create_oval(x + r - 8 * z, y - r - 6 * z, x + r + 6 * z, y - r + 8 * z,
                                   fill=COSTLY_COLOR, outline="", tags=tags)
                if show_text:
                    canvas.create_text(x + r - z, y - r + z, text="!", fill="white",
                                       font=("TkDefaultFont", 8, "bold"), tags=tags)
            if is_avl and node["unbalanced"]:
                text = ("+" if node["balance"] > 0 else "") + str(node["balance"])
                canvas.create_rectangle(x - r - 12 * z, y - r - 8 * z, x - r + 10 * z, y - r + 7 * z,
                                        fill=UNBALANCED_COLOR, outline="", tags=tags)
                if show_text:
                    canvas.create_text(x - r - z, y - r, text=text, fill="white",
                                       font=("TkDefaultFont", 7, "bold"), tags=tags)
            if show_text:
                size = max(7, int(9 * z))
                canvas.create_text(x, y, text=str(node["id"]), fill="white",
                                   font=("TkDefaultFont", size, "bold"), tags=tags)
                canvas.create_text(x, y + r + 9 * z, text=one_decimal(node["key"][1]),
                                   font=("TkDefaultFont", max(7, int(8 * z))), fill="#444", tags=tags)

        bottom = max(y for _, y in position.values()) + r + 24
        right = max(x for x, _ in position.values()) + MARGIN * z
        return bottom, max(right, 400)

    # ---------------------------------------------------------------- events

    def _on_click(self, _event):
        for tag in self.canvas.gettags("current"):
            if tag.startswith("id:"):
                self.on_select(int(tag[3:]))
                return

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
