# Markdown Reader

Read-only Markdown viewer for GNOME. GTK4 + libadwaita + WebKitGTK, GitHub-flavored rendering via `cmark-gfm`.

## Install

```sh
makepkg -si          # system-wide, as a pacman package
# or
make install         # ~/.local, no root
make default         # optional: make it the default app for .md
```

## Keys

| Key | Action |
| --- | --- |
| Ctrl+O | Open |
| Ctrl+F | Find (Enter / Shift+Enter: next / previous) |
| F9 | Contents sidebar |
| Alt+Left | Back (after following a link to another `.md`) |
| Ctrl+R, F5 | Reload (also automatic on save) |
| Ctrl+P | Print / PDF |
| Ctrl+= / Ctrl+- / Ctrl+0 | Zoom |
| Ctrl+N / Ctrl+W / Ctrl+Q | New window / close / quit |
