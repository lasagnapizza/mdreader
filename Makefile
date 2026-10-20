PREFIX ?= $(HOME)/.local
APP_ID = io.normal.MdReader
VERSION := $(shell sed -n 's/^VERSION = "\(.*\)"/\1/p' mdreader.py)
DIST = normal-md-reader-$(VERSION)
DIST_FILES = mdreader.py $(APP_ID).desktop $(APP_ID).svg Makefile PKGBUILD README.md $(wildcard LICENSE)
SOURCE_DATE_EPOCH ?= $(shell git log -1 --format=%ct 2>/dev/null || echo 0)

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

check:
	ruff check mdreader.py tests
	python3 -m unittest discover -s tests -v
	desktop-file-validate $(APP_ID).desktop
	@grep -qx 'pkgver=$(VERSION)' PKGBUILD || { echo "PKGBUILD pkgver does not match VERSION $(VERSION)"; exit 1; }

dist:
	mkdir -p dist
	tar --create --sort=name --mtime=@$(SOURCE_DATE_EPOCH) --owner=0 --group=0 --numeric-owner \
	    --transform 's,^,$(DIST)/,' $(DIST_FILES) | gzip -n > dist/$(DIST).tar.gz

.PHONY: install uninstall default check dist
