#!/usr/bin/env python3
"""Markdown Reader: a read-only Markdown viewer for GNOME."""

import html
import json
import os
import re
import shutil
import subprocess
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("WebKit", "6.0")
gi.require_version("JavaScriptCore", "6.0")
gi.require_version("Pango", "1.0")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango, WebKit  # noqa: E402
from pygments import highlight  # noqa: E402
from pygments.formatters import HtmlFormatter  # noqa: E402
from pygments.lexers import get_lexer_by_name  # noqa: E402
from pygments.styles import get_all_styles  # noqa: E402
from pygments.util import ClassNotFound  # noqa: E402

APP_ID = "io.normal.MdReader"
APP_NAME = "Markdown Reader"
VERSION = "0.1.0"
MD_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn", ".mdtxt", ".mdtext")

# --- rendering --------------------------------------------------------------

# Raw HTML is allowed (READMEs rely on it); tagfilter strips <script>, <style>,
# <iframe> and friends, and the web view never runs scripts from markup.
CMARK = ["cmark-gfm", "--unsafe", "--validate-utf8",
         "-e", "table", "-e", "strikethrough", "-e", "autolink",
         "-e", "tasklist", "-e", "tagfilter", "-e", "footnotes"]

FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(?=[\w\"'-][^\r\n]*:)(.*?)^(?:---|\.\.\.)[ \t]*(?:\r?\n|\Z)", re.S | re.M)
CODE_RE = re.compile(r'<pre><code class="language-([^"]+)">(.*?)</code></pre>', re.S)
HEADING_RE = re.compile(r"<h([1-6])(\s[^>]*)?>(.*?)</h\1>", re.S | re.I)
ID_ATTR_RE = re.compile(r'\sid="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")
ALERT_RE = re.compile(r"<blockquote>\s*<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*(</p>)?", re.I)

FORMATTER = HtmlFormatter(cssclass="highlight")


def _style(name, fallback):
    return name if name in set(get_all_styles()) else fallback


PYGMENTS_CSS = (HtmlFormatter(style="default").get_style_defs("html:not(.dark) .highlight") + "\n"
                + HtmlFormatter(style=_style("github-dark", "monokai")).get_style_defs("html.dark .highlight"))


def slugify(text):
    """GitHub-style heading anchor."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _highlight_block(match):
    try:
        lexer = get_lexer_by_name(html.unescape(match.group(1)))
    except ClassNotFound:
        return match.group(0)
    return highlight(html.unescape(match.group(2)), lexer, FORMATTER)


def _alert(match):
    kind = match.group(1).lower()
    head = f'<blockquote class="alert alert-{kind}"><p class="alert-title">{kind.title()}</p>'
    return head if match.group(2) else head + "<p>"


def render(text):
    """Render Markdown to (html, toc), toc being [(level, title, id)]."""
    front = ""
    match = FRONT_MATTER_RE.match(text)
    if match:
        front = ('<details class="front-matter"><summary>Front matter</summary>'
                 + highlight(match.group(1), get_lexer_by_name("yaml"), FORMATTER) + "</details>")
        text = text[match.end():]

    body = subprocess.run(CMARK, input=text.encode(), capture_output=True, check=True).stdout.decode()
    body = CODE_RE.sub(_highlight_block, body)
    body = ALERT_RE.sub(_alert, body)

    toc, used = [], set(ID_ATTR_RE.findall(body))

    def unique(base):
        hid, n = base, 0
        while hid in used:
            n += 1
            hid = f"{base}-{n}"
        used.add(hid)
        return hid

    def heading(m):
        level, attrs, inner = int(m.group(1)), m.group(2) or "", m.group(3)
        title = html.unescape(TAG_RE.sub("", inner)).strip()
        existing = ID_ATTR_RE.search(attrs)
        if existing:
            hid = existing.group(1)
        else:
            hid = unique(slugify(title) or "section")
            attrs += f' id="{hid}"'
        if title:
            toc.append((level, title, hid))
        return f"<h{level}{attrs}>{inner}</h{level}>"

    return front + HEADING_RE.sub(heading, body), toc


def is_markdown(path):
    return path.lower().endswith(MD_SUFFIXES)


def system_fonts():
    sans, mono = "Adwaita Sans", "Adwaita Mono"
    source = Gio.SettingsSchemaSource.get_default()
    if source and source.lookup("org.gnome.desktop.interface", True):
        settings = Gio.Settings.new("org.gnome.desktop.interface")
        sans = Pango.FontDescription.from_string(settings.get_string("document-font-name")).get_family() or sans
        mono = Pango.FontDescription.from_string(settings.get_string("monospace-font-name")).get_family() or mono
    return sans, mono


def theme():
    """(dark, accent hex) following the GNOME style and accent color."""
    manager = Adw.StyleManager.get_default()
    dark = manager.get_dark()
    rgba = Adw.AccentColor.to_standalone_rgba(manager.get_accent_color(), dark)
    return dark, "#%02x%02x%02x" % tuple(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))


PAGE_CSS = """
:root{--fg:#1f2328;--muted:#59636e;--bg:#ffffff;--border:#d1d9e0;--subtle:#f6f8fa;--code:#eff1f3;--mark:#fff8c5;color-scheme:light}
html.dark{--fg:#e8e8ea;--muted:#9a9aa2;--bg:#1d1d20;--border:#3a3a40;--subtle:#26262a;--code:#303035;--mark:#6b5a1e;color-scheme:dark}
html{background:var(--bg);scroll-behavior:smooth;scroll-padding-top:1rem}
body{margin:0;color:var(--fg);background:var(--bg);font-family:var(--sans);font-size:16px;line-height:1.65;text-rendering:optimizeLegibility}
#content{max-width:48rem;margin:0 auto;padding:2.5rem 2rem 6rem;overflow-wrap:break-word}
#content>:first-child,#content>.front-matter+*{margin-top:0}
::selection{background:color-mix(in srgb,var(--accent) 30%,transparent)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3,h4,h5,h6{margin:1.6em 0 .6em;font-weight:700;line-height:1.25}
h1{font-size:2em;padding-bottom:.3em;border-bottom:1px solid var(--border)}
h2{font-size:1.5em;padding-bottom:.3em;border-bottom:1px solid var(--border)}
h3{font-size:1.25em}h4{font-size:1em}h5{font-size:.875em}h6{font-size:.85em;color:var(--muted)}
p,ul,ol,dl,table,blockquote,details,.code-block{margin:0 0 1em}
ul,ol{padding-left:2em}
li+li{margin-top:.25em}
li>ul,li>ol{margin:.25em 0 0}
li>p{margin:.5em 0}
li:has(>input[type=checkbox]){list-style:none}
li>input[type=checkbox]{margin:0 .45em .2em -1.5em;vertical-align:middle;accent-color:var(--accent)}
dt{font-weight:600}dd{margin:0 0 .5em 1.5em}
hr{height:.25em;margin:1.5em 0;padding:0;background:var(--border);border:0}
blockquote{margin-left:0;padding:0 1em;color:var(--muted);border-left:.25em solid var(--border)}
blockquote>:last-child{margin-bottom:0}
img{max-width:100%;height:auto}
table{display:block;width:max-content;max-width:100%;overflow:auto;border-collapse:collapse}
th,td{padding:6px 13px;border:1px solid var(--border)}
th{font-weight:600}
tr:nth-child(2n){background:var(--subtle)}
code,kbd,pre,samp{font-family:var(--mono)}
:not(pre)>code{padding:.2em .4em;font-size:85%;background:var(--code);border-radius:6px}
pre{margin:0;padding:1em;overflow:auto;font-size:85%;line-height:1.45;background:var(--subtle);border-radius:8px}
#content .highlight{margin:0 0 1em;background:none}
#content .highlight .code-block{margin:0}
#content .highlight pre{line-height:1.45}
.code-block{position:relative}
.copy{position:absolute;top:.5em;right:.5em;padding:.25em .6em;font:600 12px var(--sans);color:var(--muted);background:var(--bg);border:1px solid var(--border);border-radius:6px;opacity:0;transition:opacity .15s;cursor:pointer}
.code-block:hover .copy{opacity:1}
.copy:hover{color:var(--fg)}
kbd{display:inline-block;padding:.15em .4em;font-size:80%;line-height:1;background:var(--subtle);border:1px solid var(--border);border-bottom-width:2px;border-radius:5px}
mark{color:inherit;background:var(--mark)}
summary{cursor:pointer}
.front-matter{font-size:.9em;color:var(--muted)}
.front-matter summary{margin-bottom:.5em}
.footnotes{margin-top:2.5em;padding-top:1em;font-size:.875em;color:var(--muted);border-top:1px solid var(--border)}
.alert{padding:.5em 1em;color:inherit;border-left-color:var(--alert)}
.alert-title{margin:0 0 .25em;font-weight:600;color:var(--alert)}
.alert-note{--alert:#0969da}.alert-tip{--alert:#1a7f37}.alert-important{--alert:#8250df}.alert-warning{--alert:#9a6700}.alert-caution{--alert:#cf222e}
html.dark .alert-note{--alert:#4493f8}html.dark .alert-tip{--alert:#3fb950}html.dark .alert-important{--alert:#ab7df8}html.dark .alert-warning{--alert:#d29922}html.dark .alert-caution{--alert:#f85149}
@media print{.copy{display:none}#content{max-width:none;padding:0}}
"""

PAGE_JS = r"""
(() => {
  const post = (msg) => window.webkit.messageHandlers.mdreader.postMessage(msg);
  let current;

  function decorate() {
    for (const pre of document.querySelectorAll("#content pre")) {
      if (pre.parentElement.classList.contains("code-block")) continue;
      const wrap = document.createElement("div");
      wrap.className = "code-block";
      pre.replaceWith(wrap);
      wrap.append(pre);
      const button = document.createElement("button");
      button.className = "copy";
      button.textContent = "Copy";
      button.addEventListener("click", () => post({ copy: pre.innerText }));
      wrap.append(button);
    }
  }

  function spy() {
    const headings = document.querySelectorAll("#content :is(h1,h2,h3,h4,h5,h6)[id]");
    let id = null;
    const scrollable = document.documentElement.scrollHeight > innerHeight + 2;
    if (headings.length && scrollable && innerHeight + scrollY >= document.documentElement.scrollHeight - 2) {
      id = headings[headings.length - 1].id;
    } else {
      for (const h of headings) {
        if (h.getBoundingClientRect().top > 90) break;
        id = h.id;
      }
    }
    if (id !== current) {
      current = id;
      post({ heading: id });
    }
  }

  let queued = false;
  addEventListener("scroll", () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; spy(); });
  }, { passive: true });

  window.mdreader = {
    setContent(html) {
      document.getElementById("content").innerHTML = html;
      decorate();
      current = undefined;
      spy();
    },
    setTheme(dark, accent) {
      document.documentElement.classList.toggle("dark", dark);
      document.documentElement.style.setProperty("--accent", accent);
    },
    scrollToId(id, smooth) {
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: smooth ? "smooth" : "instant", block: "start" });
    },
  };

  decorate();
  spy();
})();
"""


def page(body, dark, accent):
    sans, mono = system_fonts()
    root = f":root{{--accent:{accent};--sans:{json.dumps(sans)},system-ui,sans-serif;--mono:{json.dumps(mono)},monospace}}"
    return ('<!doctype html><html class="' + ("dark" if dark else "") + '"><head><meta charset="utf-8">'
            f"<style>{root}{PYGMENTS_CSS}{PAGE_CSS}</style></head>"
            f'<body><article id="content">{body}</article></body></html>')


# --- UI ---------------------------------------------------------------------

KEPT_MENU_ACTIONS = {
    WebKit.ContextMenuAction.OPEN_LINK,
    WebKit.ContextMenuAction.COPY_LINK_TO_CLIPBOARD,
    WebKit.ContextMenuAction.COPY_IMAGE_TO_CLIPBOARD,
    WebKit.ContextMenuAction.COPY_IMAGE_URL_TO_CLIPBOARD,
    WebKit.ContextMenuAction.COPY,
    WebKit.ContextMenuAction.SELECT_ALL,
}

DOC_ACTIONS = ("open-with", "reload", "find", "print", "zoom-in", "zoom-out", "zoom-reset", "toggle-sidebar")


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME, default_width=980, default_height=900)
        self.set_size_request(360, 320)
        self.file = None
        self.monitor = None
        self.history = []
        self.toc_ids = []
        self.pending_fragment = ""
        self.expect_load = False
        self.reload_source = 0
        self.reload_after_load = False
        self.sidebar_decided = False

        self._build_ui()
        self._build_actions()
        style = Adw.StyleManager.get_default()
        self._theme_handlers = [style.connect("notify::dark", self._apply_theme),
                                style.connect("notify::accent-color-rgba", self._apply_theme)]
        self.connect("close-request", self._on_close)
        self._update_actions()

    # building

    def _build_ui(self):
        self.webview = WebKit.WebView()
        settings = self.webview.get_settings()
        settings.set_enable_javascript_markup(False)
        settings.set_enable_back_forward_navigation_gestures(False)
        manager = self.webview.get_user_content_manager()
        manager.register_script_message_handler("mdreader", None)
        manager.connect("script-message-received::mdreader", self._on_page_message)
        manager.add_script(WebKit.UserScript.new(PAGE_JS, WebKit.UserContentInjectedFrames.TOP_FRAME,
                                                 WebKit.UserScriptInjectionTime.END, None, None))
        self.webview.connect("decide-policy", self._on_decide_policy)
        self.webview.connect("load-changed", self._on_load_changed)
        self.webview.connect("context-menu", self._on_context_menu)

        self.toc_list = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.toc_list.connect("row-activated", self._on_toc_activated)
        self.toc_stack = Gtk.Stack()
        self.toc_stack.add_named(Gtk.ScrolledWindow(child=self.toc_list, hscrollbar_policy=Gtk.PolicyType.NEVER), "list")
        self.toc_stack.add_named(Adw.StatusPage(title="No Headings", icon_name="view-list-symbolic",
                                                css_classes=["compact"]), "empty")

        self.split = Adw.OverlaySplitView(sidebar=self.toc_stack, content=self.webview, show_sidebar=False)

        self.empty_page = Adw.StatusPage(icon_name="text-x-generic-symbolic", title=APP_NAME,
                                         description="Open a Markdown file, or drop one here")
        self.empty_page.set_child(Gtk.Button(label="Open…", action_name="win.open", halign=Gtk.Align.CENTER,
                                             css_classes=["pill", "suggested-action"]))
        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.empty_page.add_controller(drop)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self.empty_page, "empty")
        self.stack.add_named(self.split, "doc")
        self.toasts = Adw.ToastOverlay(child=self.stack)

        self.title_widget = Adw.WindowTitle(title=APP_NAME)
        header = Adw.HeaderBar(title_widget=self.title_widget)
        sidebar_button = Gtk.ToggleButton(icon_name="sidebar-show-symbolic", tooltip_text="Contents (F9)")
        self.split.bind_property("show-sidebar", sidebar_button, "active",
                                 GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.back_button = Gtk.Button(icon_name="go-previous-symbolic", action_name="win.back",
                                      tooltip_text="Back (Alt+Left)")
        header.pack_start(sidebar_button)
        header.pack_start(self.back_button)

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("New Window", "app.new-window")
        section.append("Open…", "win.open")
        section.append("Open With…", "win.open-with")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append("Reload", "win.reload")
        section.append("Find…", "win.find")
        section.append("Print…", "win.print")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append("Zoom In", "win.zoom-in")
        section.append("Zoom Out", "win.zoom-out")
        section.append("Reset Zoom", "win.zoom-reset")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(f"About {APP_NAME}", "app.about")
        menu.append_section(None, section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu, primary=True,
                                       tooltip_text="Main Menu"))
        search_button = Gtk.ToggleButton(icon_name="system-search-symbolic", tooltip_text="Find (Ctrl+F)")
        header.pack_end(search_button)

        self.search_entry = Gtk.SearchEntry(placeholder_text="Find in document", hexpand=True)
        self.match_label = Gtk.Label(css_classes=["dim-label", "numeric"])
        previous = Gtk.Button(icon_name="go-up-symbolic", tooltip_text="Previous Match (Shift+Enter)")
        following = Gtk.Button(icon_name="go-down-symbolic", tooltip_text="Next Match (Enter)")
        previous.connect("clicked", lambda _b: self.finder.search_previous())
        following.connect("clicked", lambda _b: self.finder.search_next())
        arrows = Gtk.Box(css_classes=["linked"])
        arrows.append(previous)
        arrows.append(following)
        row = Gtk.Box(spacing=8)
        row.append(self.search_entry)
        row.append(self.match_label)
        row.append(arrows)
        self.search_bar = Gtk.SearchBar(child=Adw.Clamp(child=row, maximum_size=560))
        self.search_bar.connect_entry(self.search_entry)
        self.search_bar.bind_property("search-mode-enabled", search_button, "active",
                                      GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode)

        self.finder = self.webview.get_find_controller()
        self.finder.connect("found-text", lambda _f, n: self.match_label.set_label(
            f"{n} match" if n == 1 else f"{n} matches"))
        self.finder.connect("failed-to-find-text", lambda _f: self.match_label.set_label("No matches"))
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("activate", lambda _e: self.finder.search_next())
        self.search_entry.connect("next-match", lambda _e: self.finder.search_next())
        self.search_entry.connect("previous-match", lambda _e: self.finder.search_previous())
        self.search_entry.connect("stop-search", lambda _e: self.search_bar.set_search_mode(False))
        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_search_key)
        self.search_entry.add_controller(keys)

        toolbar = Adw.ToolbarView(content=self.toasts)
        toolbar.add_top_bar(header)
        toolbar.add_top_bar(self.search_bar)
        self.set_content(toolbar)

        narrow = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 700sp"))
        narrow.add_setter(self.split, "collapsed", True)
        narrow.add_setter(self.split, "show-sidebar", False)
        self.add_breakpoint(narrow)

        self._apply_theme()

    def _build_actions(self):
        actions = {
            "open": self.choose_file,
            "open-with": self.open_with,
            "reload": self.reload,
            "find": lambda: self.search_bar.set_search_mode(True),
            "print": self.print_document,
            "zoom-in": lambda: self._zoom(1.1),
            "zoom-out": lambda: self._zoom(1 / 1.1),
            "zoom-reset": lambda: self._zoom(0),
            "back": self.go_back,
            "toggle-sidebar": lambda: self.split.set_show_sidebar(not self.split.get_show_sidebar()),
        }
        for name, callback in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)

    # documents

    def open_file(self, file, fragment="", remember=False):
        try:
            body, toc = render(self._read(file))
        except (GLib.Error, OSError, subprocess.CalledProcessError):
            self._toast(f"Couldn’t open “{file.get_basename()}”")
            return False
        if remember and self.file:
            self.history.append(self.file)
        self.file = file
        self.pending_fragment = fragment
        self._watch(file)
        self._set_toc(toc)

        name = file.get_basename()
        parent = file.get_parent()
        folder = parent.get_parse_name() if parent else ""
        home = GLib.get_home_dir()
        if folder == home or folder.startswith(home + os.sep):
            folder = "~" + folder[len(home):]
        self.title_widget.set_title(name)
        self.title_widget.set_subtitle(folder)
        self.set_title(name)

        dark, accent = theme()
        self.expect_load = True
        self.webview.load_html(page(body, dark, accent), file.get_uri())
        self.stack.set_visible_child_name("doc")
        Gtk.RecentManager.get_default().add_item(file.get_uri())
        if not self.sidebar_decided:
            self.sidebar_decided = True
            self.split.set_show_sidebar(len(toc) > 2 and not self.split.get_collapsed())
        self._update_actions()
        return True

    def reload(self):
        if not self.file:
            return
        if self.webview.is_loading():
            self.reload_after_load = True
            return
        try:
            body, toc = render(self._read(self.file))
        except (GLib.Error, OSError, subprocess.CalledProcessError):
            return  # mid-save or gone; keep what is on screen
        self._set_toc(toc)
        self._js(f"mdreader.setContent({json.dumps(body)})")

    def go_back(self):
        if self.history and self.open_file(self.history[-1]):
            self.history.pop()
            self._update_actions()

    def choose_file(self):
        markdown = Gtk.FileFilter(name="Markdown")
        markdown.add_mime_type("text/markdown")
        for suffix in MD_SUFFIXES:
            markdown.add_suffix(suffix[1:])
        everything = Gtk.FileFilter(name="All Files")
        everything.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(markdown)
        filters.append(everything)
        dialog = Gtk.FileDialog(title="Open Markdown File", filters=filters, default_filter=markdown)
        if self.file and self.file.get_parent():
            dialog.set_initial_folder(self.file.get_parent())
        dialog.open(self, None, self._on_file_chosen)

    def _on_file_chosen(self, dialog, result):
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return  # cancelled
        self.open_file(file, remember=True)

    def open_with(self):
        if self.file:
            launcher = Gtk.FileLauncher.new(self.file)
            launcher.set_always_ask(True)
            launcher.launch(self, None, self._on_launched)

    def print_document(self):
        # Print on paper colors, then restore the screen theme.
        self._js("mdreader.setTheme(false, getComputedStyle(document.documentElement).getPropertyValue('--accent'))")
        operation = WebKit.PrintOperation.new(self.webview)
        operation.connect("finished", lambda _o: self._apply_theme())
        if operation.run_dialog(self) == WebKit.PrintOperationResponse.CANCEL:
            self._apply_theme()

    @staticmethod
    def _read(file):
        _ok, data, _etag = file.load_contents(None)
        return data.decode("utf-8", "replace")

    def _watch(self, file):
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        try:
            self.monitor = file.monitor_file(Gio.FileMonitorFlags.NONE, None)
        except GLib.Error:
            return
        self.monitor.connect("changed", self._on_file_changed)

    def _on_file_changed(self, _monitor, _file, _other, event):
        if event in (Gio.FileMonitorEvent.DELETED, Gio.FileMonitorEvent.PRE_UNMOUNT,
                     Gio.FileMonitorEvent.UNMOUNTED):
            return
        # Editors save in bursts (truncate, write, rename); settle first.
        if self.reload_source:
            GLib.source_remove(self.reload_source)
        self.reload_source = GLib.timeout_add(150, self._reload_settled)

    def _reload_settled(self):
        self.reload_source = 0
        self.reload()
        return GLib.SOURCE_REMOVE

    def _follow(self, uri):
        base, _, fragment = uri.partition("#")
        target = Gio.File.new_for_uri(base)
        if self.file and target.equal(self.file):
            self._js(f"mdreader.scrollToId({json.dumps(GLib.Uri.unescape_string(fragment) or '')}, true)")
            return
        if target.has_uri_scheme("file"):
            path = target.get_path()
            if path and is_markdown(path) and os.path.isfile(path):
                self.open_file(target, GLib.Uri.unescape_string(fragment) or "", remember=True)
                return
            Gtk.FileLauncher.new(target).launch(self, None, self._on_launched)
        else:
            Gtk.UriLauncher.new(uri).launch(self, None, self._on_launched)

    def _on_launched(self, launcher, result):
        try:
            launcher.launch_finish(result)
        except GLib.Error as err:
            if not err.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self._toast(err.message)

    # web view

    def _on_decide_policy(self, _view, decision, kind):
        if kind == WebKit.PolicyDecisionType.RESPONSE:
            return False
        action = decision.get_navigation_action()
        nav = action.get_navigation_type()
        uri = action.get_request().get_uri()
        base, _, fragment = uri.partition("#")

        if kind == WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            if nav == WebKit.NavigationType.RELOAD:
                decision.ignore()
                self.reload()
                return True
            if nav == WebKit.NavigationType.BACK_FORWARD:
                decision.ignore()
                self.go_back()
                return True
            if self.file and Gio.File.new_for_uri(base).equal(self.file):
                if fragment or self.expect_load:
                    self.expect_load = False
                    return False  # our own load, or an in-page anchor
                decision.ignore()
                self._js("scrollTo(0, 0)")
                return True

        decision.ignore()
        if action.is_user_gesture():  # never let markup (meta refresh etc.) launch things
            self._follow(uri)
        return True

    def _on_load_changed(self, _view, event):
        if event == WebKit.LoadEvent.COMMITTED:
            self.expect_load = False
        elif event == WebKit.LoadEvent.FINISHED:
            if self.pending_fragment:
                self._js(f"mdreader.scrollToId({json.dumps(self.pending_fragment)}, false)")
                self.pending_fragment = ""
            if self.reload_after_load:
                self.reload_after_load = False
                self.reload()
            if not self.search_bar.get_search_mode():
                self.webview.grab_focus()

    def _on_context_menu(self, _view, menu, _hit):
        for item in list(menu.get_items()):
            if item.get_stock_action() not in KEPT_MENU_ACTIONS:
                menu.remove(item)
        return menu.get_n_items() == 0

    def _on_page_message(self, _manager, value):
        message = json.loads(value.to_json(0))
        if "copy" in message:
            self.get_clipboard().set_content(Gdk.ContentProvider.new_for_value(message["copy"]))
            self._toast("Copied")
        elif "heading" in message:
            heading = message["heading"]
            if heading in self.toc_ids:
                self.toc_list.select_row(self.toc_list.get_row_at_index(self.toc_ids.index(heading)))
            else:
                self.toc_list.unselect_all()

    def _js(self, script):
        self.webview.evaluate_javascript(script, -1, None, None, None, None, None)

    def _apply_theme(self, *_):
        dark, accent = theme()
        background = Gdk.RGBA()
        background.parse("#1d1d20" if dark else "#ffffff")
        self.webview.set_background_color(background)
        self._js(f"window.mdreader && mdreader.setTheme({json.dumps(dark)}, {json.dumps(accent)})")

    def _zoom(self, factor):
        level = 1.0 if factor == 0 else self.webview.get_zoom_level() * factor
        self.webview.set_zoom_level(min(3.0, max(0.5, level)))

    # sidebar

    def _set_toc(self, toc):
        self.toc_list.remove_all()
        self.toc_ids = [hid for _level, _title, hid in toc]
        top = min((level for level, _title, _hid in toc), default=1)
        for level, title, _hid in toc:
            self.toc_list.append(Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                           tooltip_text=title, margin_start=(level - top) * 14))
        self.toc_stack.set_visible_child_name("list" if toc else "empty")

    def _on_toc_activated(self, _list, row):
        self._js(f"mdreader.scrollToId({json.dumps(self.toc_ids[row.get_index()])}, true)")
        if self.split.get_collapsed():
            self.split.set_show_sidebar(False)

    # search

    def _on_search_mode(self, bar, _pspec):
        if bar.get_search_mode():
            self._on_search_changed(self.search_entry)
        else:
            self.finder.search_finish()
            self.match_label.set_label("")
            self.webview.grab_focus()

    def _on_search_changed(self, entry):
        text = entry.get_text()
        if not text:
            self.finder.search_finish()
            self.match_label.set_label("")
            return
        options = WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND
        self.finder.search(text, options, 9999)

    def _on_search_key(self, _controller, keyval, _keycode, state):
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and state & Gdk.ModifierType.SHIFT_MASK:
            self.finder.search_previous()
            return True
        return False

    # misc

    def _on_drop(self, _target, value, _x, _y):
        files = value.get_files()
        if not files:
            return False
        self.open_file(files[0])
        return True

    def _toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=2))

    def _update_actions(self):
        for name in DOC_ACTIONS:
            self.lookup_action(name).set_enabled(self.file is not None)
        self.lookup_action("back").set_enabled(bool(self.history))
        self.back_button.set_visible(bool(self.history))

    def _on_close(self, _window):
        if self.monitor:
            self.monitor.cancel()
        if self.reload_source:
            GLib.source_remove(self.reload_source)
            self.reload_source = 0
        style = Adw.StyleManager.get_default()
        for handler in self._theme_handlers:
            style.disconnect(handler)
        return False


class App(Adw.Application):
    def __init__(self, application_id=APP_ID):
        super().__init__(application_id=application_id, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        GLib.set_application_name(APP_NAME)

    def do_startup(self):
        Adw.Application.do_startup(self)
        for name, callback in (("new-window", lambda: Window(self).present()),
                               ("about", self._about),
                               ("quit", self.quit)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, cb=callback: cb())
            self.add_action(action)
        accels = {
            "app.new-window": ["<Control>n"],
            "app.quit": ["<Control>q"],
            "window.close": ["<Control>w"],
            "win.open": ["<Control>o"],
            "win.reload": ["<Control>r", "F5"],
            "win.find": ["<Control>f"],
            "win.print": ["<Control>p"],
            "win.zoom-in": ["<Control>plus", "<Control>equal", "<Control>KP_Add"],
            "win.zoom-out": ["<Control>minus", "<Control>KP_Subtract"],
            "win.zoom-reset": ["<Control>0", "<Control>KP_0"],
            "win.back": ["<Alt>Left"],
            "win.toggle-sidebar": ["F9"],
        }
        for action, keys in accels.items():
            self.set_accels_for_action(action, keys)

    def do_activate(self):
        (self.get_active_window() or Window(self)).present()

    def do_open(self, files, _n_files, _hint):
        windows = [w for w in self.get_windows() if isinstance(w, Window)]
        for file in files:
            window = next((w for w in windows if w.file and w.file.equal(file)), None)
            if window is None:
                window = next((w for w in windows if w.file is None), None) or Window(self)
                window.open_file(file)
                windows.append(window)
            window.present()

    def _about(self):
        Adw.AboutDialog(application_name=APP_NAME, application_icon=APP_ID, version=VERSION,
                        comments="Reads Markdown. Does not edit it.").present(self.get_active_window())


def main():
    if not shutil.which("cmark-gfm"):
        sys.exit("mdreader: cmark-gfm not found (pacman -S cmark-gfm)")
    return App().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
