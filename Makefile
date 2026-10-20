PREFIX ?= $(HOME)/.local
APP_ID = io.normal.MdReader

install:
	install -Dm755 mdreader.py $(DESTDIR)$(PREFIX)/bin/mdreader
	install -Dm644 $(APP_ID).desktop $(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	install -Dm644 $(APP_ID).svg $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
	@if [ -z "$(DESTDIR)" ]; then update-desktop-database -q $(PREFIX)/share/applications || true; fi

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/mdreader
	rm -f $(DESTDIR)$(PREFIX)/share/applications/$(APP_ID).desktop
	rm -f $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg

default:
	xdg-mime default $(APP_ID).desktop text/markdown text/x-markdown

.PHONY: install uninstall default
