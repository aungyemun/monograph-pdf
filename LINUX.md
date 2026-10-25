# Monograph PDF for Linux — first release (0.1.0)

The **first Linux build** lives on the [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux) branch.
It is versioned separately from Windows (**0.5.0** prepared on `main`; **0.4.0** latest published)
and from macOS (**0.1.0**, tag `v0.1.0-macos-1`).

**No Linux release tag yet.** Do not look for `v0.1.0-linux` on the Releases page until one is
explicitly published. Until then, clone the `linux` branch and build from source.

**Unsigned.** This first Linux line has no code signing; signing will be added later.

## Quick start

```bash
git clone -b linux https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

Full notes on the linux branch:
[LINUX.md](https://github.com/aungyemun/monograph-pdf/blob/linux/LINUX.md) ·
[release notes draft](https://github.com/aungyemun/monograph-pdf/blob/linux/docs/releases/v0.1.0.md).
