"""Form fields for the setup screens. Each field edits one place in the working setup and shows that place's messages right under it.

A field never decides whether a value is acceptable: the shared checker (cellpoc.setup) does that and the messages come from it.
Every field's widget key starts with the form version; when the structure of the setup changes (an item is added, removed, or a
different setup is loaded) the version moves on, so every field is redrawn from the setup.
"""
from __future__ import annotations

import math
from typing import Callable

import streamlit as st

from cellpoc.setup import Problem, field_label, path_text

from . import style

SAFE_INT = 2 ** 50          # larger numbers cannot be shown in a number box
_ABSENT = object()


# ------------------------------------------------------------------ reading and writing one place in the setup
def get_at(root, path: tuple, default=None):
    for part in path:
        try:
            root = root[part]
        except (KeyError, IndexError, TypeError):
            return default
    return root


def set_at(root, path: tuple, value) -> None:
    parent = get_at(root, path[:-1])
    if isinstance(parent, dict) or (isinstance(parent, list) and isinstance(path[-1], int) and -len(parent) <= path[-1] < len(parent)):
        parent[path[-1]] = value


def drop_at(root, path: tuple) -> None:
    parent = get_at(root, path[:-1])
    if isinstance(parent, dict):
        parent.pop(path[-1], None)


def _current() -> dict:
    return st.session_state["setup"]


def _bump() -> None:
    st.session_state["ver"] = st.session_state.get("ver", 0) + 1


# ------------------------------------------------------------------ callbacks (run before the page is redrawn)
def _store(path: tuple, key: str, kind: str, integer: bool = False, optional: bool = False) -> None:
    value = st.session_state.get(key)
    if value is None and optional:
        drop_at(_current(), path)
        return
    if kind == "number" and value is not None and integer and float(value).is_integer():
        value = int(value)
    if kind == "csv":
        value = [part.strip() for part in str(value or "").split(",") if part.strip()]
    elif kind == "list":
        value = list(value or [])
    set_at(_current(), path, value)


def _add_item(path: tuple, item) -> None:
    items = get_at(_current(), path)
    if not isinstance(items, list):
        set_at(_current(), path, [])
        items = get_at(_current(), path)
    items.append(item)
    _bump()


def _remove_item(path: tuple, index: int) -> None:
    items = get_at(_current(), path)
    if isinstance(items, list) and 0 <= index < len(items):
        items.pop(index)
    _bump()


def _rebuild_rows(path: tuple, ver: int, count: int, wrap: bool) -> None:
    """Read the rows of a 'name -> value' table back into the setup."""
    pt = path_text(path)
    rebuilt = {}
    for i in range(count):
        name = st.session_state.get(f"w{ver}|{pt}|k{i}")
        value = st.session_state.get(f"w{ver}|{pt}|v{i}")
        if name is None:
            continue
        rebuilt[name] = {"divide_by": value} if wrap else (value if value is not None else "")
    set_at(_current(), path, rebuilt)


def _add_row(path: tuple, wrap: bool) -> None:
    table = get_at(_current(), path)
    if not isinstance(table, dict):
        set_at(_current(), path, {})
        table = get_at(_current(), path)
    n = len(table) + 1
    while (name := f"new_{n}") in table:
        n += 1
    table[name] = {"divide_by": None} if wrap else ""
    _bump()


def _remove_row(path: tuple, name) -> None:
    drop_at(_current(), path + (name,))
    _bump()


def _goal_changed(path: tuple, key: str) -> None:
    """Switching a target between 'at least / at most' and 'between' swaps which number boxes it needs."""
    goal = st.session_state.get(key)
    item = get_at(_current(), path)
    if isinstance(item, dict):
        item["goal"] = goal
        wanted = ("low", "high") if goal == "between" else ("value",)
        for name in ("value", "low", "high"):
            if name in wanted:
                item.setdefault(name, None)
            else:
                item.pop(name, None)
    _bump()


def _rule_changed(path: tuple, key: str) -> None:
    kind = st.session_state.get(key)
    item = get_at(_current(), path)
    if isinstance(item, dict):
        item["rule"] = kind
        if kind == "sum_to":
            for name in ("items", "limit"):
                item.pop(name, None)
            item.setdefault("total", 100)
            item.setdefault("tolerance", 0.05)
        else:
            for name in ("total", "tolerance"):
                item.pop(name, None)
            item.setdefault("items", [])
            item.setdefault("limit", None)
    _bump()


# ------------------------------------------------------------------ the form
class Form:
    """One drawing of the current screen: the working setup, the checker's problems, and the fields."""

    def __init__(self, setup: dict, problems: list[Problem], layout: dict | None = None):
        self.setup = setup
        self.problems = problems
        self.layout = layout
        self.ver = st.session_state.get("ver", 0)
        self.shown: set[Problem] = set()
        self.by_path: dict[str, list[Problem]] = {}
        for p in problems:
            self.by_path.setdefault(p.path, []).append(p)

    def key(self, path: tuple, extra: str = "") -> str:
        return f"w{self.ver}|{path_text(path)}{extra}"

    def show(self, path: tuple) -> None:
        """The messages that belong to exactly this place, as labelled text."""
        for p in self.by_path.get(path_text(path), []):
            if p not in self.shown:
                self.shown.add(p)
                style.message(p.level, p.text)

    def leftovers(self, screen: str) -> list[Problem]:
        return [p for p in self.problems if p.screen == screen and p not in self.shown]

    # ---- single fields
    def text(self, path: tuple, label: str, help: str | None = None, placeholder: str | None = None) -> None:
        value = get_at(self.setup, path)
        key = self.key(path)
        st.text_input(label, value=value if isinstance(value, str) else "", key=key, help=help, placeholder=placeholder,
                      on_change=_store, args=(path, key, "text"))
        self.show(path)

    def number(self, path: tuple, label: str, integer: bool = False, step: float | None = None, help: str | None = None,
               optional: bool = False) -> None:
        value = get_at(self.setup, path)
        usable = (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(value) < SAFE_INT)
        key = self.key(path)
        if integer and (not usable or float(value).is_integer()):
            shown, step_, fmt = (int(value) if usable else None), 1, "%d"
        else:
            shown, step_, fmt = (float(value) if usable else None), float(step or (1.0 if integer else 0.1)), "%g"
        st.number_input(label, value=shown, step=step_, format=fmt, key=key, help=help,
                        on_change=_store, args=(path, key, "number", integer, optional))
        self.show(path)

    def select(self, path: tuple, label: str, options: list[str], help: str | None = None, optional: bool = False) -> None:
        """A choice list. With optional=True, clearing the choice removes the setting from the setup."""
        value = get_at(self.setup, path)
        key = self.key(path)
        index = options.index(value) if isinstance(value, str) and value in options else None
        st.selectbox(label, options, index=index, placeholder="Choose..." if not optional else "None (not used)", key=key, help=help,
                     on_change=_store, args=(path, key, "text", False, optional))
        self.show(path)

    def multiselect(self, path: tuple, label: str, options: list[str], help: str | None = None) -> None:
        value = get_at(self.setup, path)
        current = [v for v in value if isinstance(v, str)] if isinstance(value, list) else []
        choices = list(options) + [v for v in current if v not in options]      # keep what the setup holds, so its message can say what is wrong
        key = self.key(path)
        st.multiselect(label, choices, default=current, key=key, help=help, on_change=_store, args=(path, key, "list"))
        self.show(path)

    def checkbox(self, path: tuple, label: str, help: str | None = None, missing: bool = False) -> None:
        """A tick box. `missing` is what a setting that is absent from the setup means (shown ticked or not)."""
        value = get_at(self.setup, path, _ABSENT)
        key = self.key(path)
        shown = missing if value is _ABSENT else (value if isinstance(value, bool) else False)
        st.checkbox(label, value=shown, key=key, help=help, on_change=_store, args=(path, key, "text"))
        self.show(path)

    def csv(self, path: tuple, label: str, help: str | None = None) -> None:
        value = get_at(self.setup, path)
        key = self.key(path)
        joined = ", ".join(str(v) for v in value) if isinstance(value, list) else ""
        st.text_input(label, value=joined, key=key, help=help, on_change=_store, args=(path, key, "csv"))
        self.show(path)

    # ---- lists of items (ingredients, steps, faults ...)
    def items(self, path: tuple, title: str, draw_item: Callable[["Form", tuple], None], new_item: Callable[[], dict] | dict,
              add_label: str, hint: str | None = None) -> None:
        st.markdown(f"#### {title}")
        if hint:
            st.caption(hint)
        self.show(path)
        listed = get_at(self.setup, path)
        for index, item in enumerate(listed if isinstance(listed, list) else []):
            item_path = path + (index,)
            with st.container(border=True):
                st.markdown(f"**{field_label(self.setup, item_path)}**")
                if isinstance(item, dict):
                    draw_item(self, item_path)
                else:
                    st.write("This entry is not a group of settings. Remove it and add it again.")
                self.show(item_path)
                st.button("Remove this item", key=self.key(item_path, "|remove"), on_click=_remove_item, args=(path, index))
        st.button(add_label, key=self.key(path, "|add"), on_click=_add_item, args=(path, new_item() if callable(new_item) else new_item))

    # ---- 'name -> value' tables (column mapping, unit conversions)
    def rows(self, path: tuple, title: str, name_label: str, value_label: str, wrap: bool = False, hint: str | None = None) -> None:
        st.markdown(f"#### {title}")
        if hint:
            st.caption(hint)
        self.show(path)
        table = get_at(self.setup, path)
        table = table if isinstance(table, dict) else {}
        count = len(table)
        for index, (name, value) in enumerate(table.items()):
            row_path = path + (name,)
            pt = path_text(path)
            left, right, button = st.columns([3, 3, 1])
            args = (path, self.ver, count, wrap)
            with left:
                st.text_input(name_label, value=str(name), key=f"w{self.ver}|{pt}|k{index}", on_change=_rebuild_rows, args=args)
            with right:
                if wrap:
                    inner = value.get("divide_by") if isinstance(value, dict) else None
                    usable = isinstance(inner, (int, float)) and not isinstance(inner, bool) and math.isfinite(inner)
                    st.number_input(value_label, value=float(inner) if usable else None, step=0.1, format="%g",
                                    key=f"w{self.ver}|{pt}|v{index}", on_change=_rebuild_rows, args=args)
                else:
                    st.text_input(value_label, value=value if isinstance(value, str) else "", key=f"w{self.ver}|{pt}|v{index}",
                                  on_change=_rebuild_rows, args=args)
            with button:
                st.write("")
                st.button("Remove", key=f"w{self.ver}|{pt}|rm{index}", on_click=_remove_row, args=(path, name))
            self.show(row_path)
            if wrap:
                self.show(path + (name, "divide_by"))
        st.button("Add a row", key=self.key(path, "|addrow"), on_click=_add_row, args=(path, wrap))

    # ---- shared pieces of items
    def goal_select(self, path: tuple, label: str, options: list[str]) -> None:
        value = get_at(self.setup, path)
        key = self.key(path)
        index = options.index(value) if isinstance(value, str) and value in options else None
        st.selectbox(label, options, index=index, placeholder="Choose...", key=key, on_change=_goal_changed, args=(path[:-1], key))
        self.show(path)

    def rule_select(self, path: tuple, label: str, options: list[str]) -> None:
        value = get_at(self.setup, path)
        key = self.key(path)
        index = options.index(value) if isinstance(value, str) and value in options else None
        st.selectbox(label, options, index=index, placeholder="Choose...", key=key, on_change=_rule_changed, args=(path[:-1], key))
        self.show(path)
