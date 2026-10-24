# Monograph PDF for Linux — first release (0.1.0)

The **first Linux build** lives on the [`linux`](https://github.com/aungyemun/monograph-pdf/tree/linux) branch
(tag **`v0.1.0-linux`**). It is versioned separately from Windows (**0.5.0** on `main`).

**Unsigned.** This first Linux release has no code signing; signing will be added later.

## Quick start

```bash
git clone -b linux https://github.com/aungyemun/monograph-pdf.git
cd monograph-pdf
bash scripts/setup_env.sh
bash scripts/vendor_ocr.sh
bash scripts/dev_launch.sh
```

Full notes: [LINUX.md on the linux branch](https://github.com/aungyemun/monograph-pdf/blob/linux/LINUX.md) ·
[Release notes](https://github.com/aungyemun/monograph-pdf/blob/linux/docs/releases/v0.1.0.md).
