# How to cite Monograph PDF

If you used Monograph PDF in research, teaching material or a publication, please cite it. Give the
**platform** (Windows, macOS or Linux) and the **version** you used, because each platform has its
own version numbers. The version is shown in **Help ▸ About Monograph PDF**.

The citation data is kept in
[`CITATION.cff`](https://github.com/aungyemun/monograph-pdf/blob/main/CITATION.cff). On GitHub, the
**Cite this repository** button on the project page produces APA and BibTeX entries from it.

## APA style

> Mun, A. Y. (YEAR). *Monograph PDF* (Version X.Y.Z, PLATFORM) [Computer software].
> https://github.com/aungyemun/monograph-pdf

Example for the Windows release 0.5.1:

> Mun, A. Y. (2026). *Monograph PDF* (Version 0.5.1, Windows) [Computer software].
> https://github.com/aungyemun/monograph-pdf

## BibTeX

```bibtex
@software{mun_monograph_pdf_2026,
  author  = {Mun, Aung Ye},
  title   = {Monograph PDF},
  version = {0.5.1},
  year    = {2026},
  note    = {Windows release v0.5.1},
  url     = {https://github.com/aungyemun/monograph-pdf},
  license = {AGPL-3.0-or-later}
}
```

Replace the version, year and note with the release you used. Release tags are `vX.Y.Z` for
Windows, `vX.Y.Z-macos` for macOS and `vX.Y.Z-linux` for Linux.

## Exact reproducibility

For methods sections, you can also name the exact source: every release has a Git tag, and
**Help ▸ About** shows the commit the installed program was built from. The release's
`MonographPDF_X.Y.Z_Source.zip` contains the complete source of that build.
