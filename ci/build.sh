#!/bin/sh
# Test, then build release artifacts into dist/. Runs as root in an archlinux
# container: on GitHub Actions, or locally with
#   docker run --rm -v "$PWD:/src" -w /src archlinux:latest sh ci/build.sh
set -eu

pacman -Syu --noconfirm --needed base-devel git ruff desktop-file-utils \
    python python-gobject gtk4 libadwaita webkitgtk-6.0 python-pygments cmark-gfm

version=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' mdreader.py)
if [ "${GITHUB_REF_TYPE:-}" = tag ] && [ "$GITHUB_REF_NAME" != "v$version" ]; then
    echo "tag $GITHUB_REF_NAME does not match VERSION $version in mdreader.py" >&2
    exit 1
fi

make check
rm -rf dist
make dist

name=normal-md-reader-$version
tarball=$PWD/dist/$name.tar.gz
id builder >/dev/null 2>&1 || useradd -m builder
work=$(mktemp -d)
chown builder "$work"

# Arch package, built from the release tarball so a file missing from it fails here.
su builder -c "cd '$work' && tar xzf '$tarball' && cd '$name' && makepkg -f"
cp "$work/$name"/*.pkg.tar.zst dist/

# AUR PKGBUILD for the release tarball. makepkg finds the tarball already in
# place, so building it here also verifies the checksum.
mkdir "$work/aur"
sed -e "s|@VERSION@|$version|" \
    -e "s|@REPO@|${GITHUB_REPOSITORY:-OWNER/normal-md-reader}|" \
    -e "s|@SHA256@|$(sha256sum "$tarball" | cut -d' ' -f1)|" \
    packaging/aur/PKGBUILD.in > "$work/aur/PKGBUILD"
cp "$tarball" "$work/aur/"
chown -R builder "$work/aur"
su builder -c "cd '$work/aur' && makepkg -f && makepkg --printsrcinfo > .SRCINFO"
mkdir dist/aur
cp "$work/aur/PKGBUILD" "$work/aur/.SRCINFO" dist/aur/

cd dist
sha256sum "$name.tar.gz" ./*.pkg.tar.zst | sed 's| \./| |' > SHA256SUMS
cat SHA256SUMS
