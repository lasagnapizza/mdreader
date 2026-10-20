pkgname=mdreader
pkgver=0.1.0
pkgrel=1
pkgdesc="Read-only Markdown viewer for GNOME"
arch=(any)
license=(MIT)
depends=(python python-gobject gtk4 libadwaita webkitgtk-6.0 python-pygments cmark-gfm)
source=(mdreader.py io.normal.MdReader.desktop io.normal.MdReader.svg Makefile)
sha256sums=(SKIP SKIP SKIP SKIP)

package() {
  make DESTDIR="$pkgdir" PREFIX=/usr install
}
