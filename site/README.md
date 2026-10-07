# OpenH-RF website

A static site (plain HTML, CSS and JS) with statistics of the whole dataset and an explorer
that filters datasets by their data cards and file contents. Everything it shows comes from
the Hub repo [nvidia/OpenH-RF](https://huggingface.co/datasets/nvidia/OpenH-RF).

## Updating after a pull request is merged on the Hub

The site shows the Hub repo as it was at the last update. After a pull request is merged
into the Hub repo:

1. From the repository root, run:

   ```bash
   uv run --extra site python site/update.py
   ```

   This moves `huggingface/OpenH-RF`, a clone of the Hub repo's documents (see
   `huggingface/README.md`), to the Hub's main branch, lists the files at that revision
   from the clone's git, and scans the HDF5 files that are new or changed into
   `stats/data/`. It then turns the data cards and the scan into `site/hub/`, builds the
   site, and prints the filters of each new or changed dataset. A merge that changed no
   HDF5 file takes seconds; the first run also clones the Hub repo (its history and
   documents, not the HDF5 files). It warns about any file to commit over 50 MB; GitHub
   refuses one over 100 MB. If it is interrupted, run it again: the scan carries on where
   it stopped. If the Hub refused or timed out on some files, it stops before the
   statistics and says how many; run it again to read them (`--allow-partial` builds the
   statistics without them instead). A Hugging Face token in `HF_TOKEN` raises the Hub's
   rate limits, which helps most for `--full`, a scan of every file.
2. (Only when a dataset was added.) Give it a short name: an entry in `DATASETS` in
   `plots/openh_rf_datasets.py`, keyed by the name the page shows and links it by, with its
   Hub folder. Without one the build warns and shows the folder.
   If it is from an institution the site does not list yet, the build fails and names it:
   add a row for it to `institution_filters.csv`, with an empty `affiliation`. If the card
   names a listed institution differently, add an `institution` override to
   `catalog.yaml` instead.
3. Look at the site with `uv run --extra site python site/build.py --serve`. If a filter
   comes out wrong, add an override to `catalog.yaml` (see below).
4. Commit on a branch and open a pull request. The site deploys once it is merged:

   ```bash
   git add stats/data site/hub site/catalog.yaml site/institution_filters.csv \
     plots/openh_rf_datasets.py site/figures
   git commit -m "Update the website to OpenH-RF <revision>"
   ```

After a change to what the scan records (`stats/extract.py`), rescan every file instead:

```bash
uv run --extra site python site/update.py --full
```

This takes about 80 minutes. The previous scan is kept as `stats/data/files.stale/`. If
it is interrupted, run it again without `--full`.

The filters are derived: setting, transmit scheme, probe type, dimensionality and data type
from the files, targets and tasks from the `match` patterns in `catalog.yaml` looked up in
the data card (and a region such as Abdomen & pelvis from the organs it `includes`). Where
one comes out wrong, add an override under `datasets:` in
`catalog.yaml`. The update prints the filters of each new or changed dataset to check.
The explorer's search also finds a dataset by the labels and `aliases` of its values, so
"cardiac" finds the heart datasets whose cards never say it.

A card's figure is `assets/main.png` in its folder, else the `figure` override (a path in
the dataset's folder, such as `assets/reference_bmode.png`), else `assets/hero.png`, else
the largest other PNG in `assets/`, else `main.*` or `hero.*` in another format, the images
the card embeds and the rest of `assets/`, in that order. A card whose figure is not on the
Hub can have one in `figures/<slug>.<ext>`, where the slug is the dataset id in lower case
with runs of other characters replaced by `-` (`oslo/A_cardiac` is `oslo-a-cardiac`).
Thumbnails are square centre crops, cut by `cards.py`; for a figure of several panels, a
`thumb_position` override (a CSS `object-position` such as `right` or `'10% 50%'`) picks the
part shown.

## Showing pull requests before they are merged

Open pull requests on the Hub repo can be shown on the site already, over main:

```bash
uv run --extra site python site/update.py --pr 77 --pr 78 --pr 79
```

This is the update above, except that it merges the pull requests into main locally
(`preview.py`) while it reads the data cards, and downloads each figure a pull request adds
or changes from that pull request's commit. The merge is not on the Hub, so everything else
stays at main: the scan in `stats/data/` and the revision it records, and the revision of
the explorer's download script. That is why a pull request that changes an HDF5 file is
refused, as are pull requests that conflict with each other or with main. The page names the
pull requests under the statistics, and links a dataset they change to its version in the
pull request. Commit as above.

To go back to main, run the update without `--pr`, which is also what to run once they are
merged. To show fewer or other pull requests, run it again with those.

## Build and preview

```bash
uv run --extra site python site/build.py --serve
```

This builds into `site/_site/` (git-ignored) from the committed `site/hub/` and serves it on
port 8000 (all interfaces). `--check` only validates `catalog.yaml`.

## Files

- `update.py` runs, in order: `huggingface/setup.sh --update`, `stats/refresh_data.py`
  (the metadata of every HDF5 file into `stats/data/`), `cards.py` (the data cards in the
  clone, and their figures, into `hub/cards.json` and `hub/images/`), `corpus.py`
  (statistics per dataset into `hub/corpus.json` and, for the explorer's download script,
  what each file is filtered on into `hub/files.json`) and `build.py`.
- The author list under the title: `build.py` writes it into the page from
  `scripts/authors.csv`, an export of the authors sheet, marked as
  `scripts/compile_authors.py` marks the paper's. Export the sheet over that file to update it.
  Each author links to their page in `author_websites.csv` (their Google Scholar profile,
  else their page at their institute, else none: an empty `website`). Each affiliation links
  to the explorer filtered by its institution, named as the datasets name it in
  `institution_filters.csv`. That file also lists, in rows without an affiliation, the
  institutions datasets are from that are no author's affiliation. The build warns about an
  author that is not in `author_websites.csv`, and fails unless every affiliation is a
  dataset's institution and every dataset's institution (from the cards and the
  `institution` overrides in `catalog.yaml`) is in `institution_filters.csv` once, so that
  the page counts the same institutions everywhere.
- `zea_keys.json` (the zea spec): `zea_keys.py`, run with the target zea version installed.
- `citation_suggestions.bib`: the citations the data cards ask for, shown in each dataset's
  details: the card's BibTeX, else an entry written from the citation it suggests. A
  `% dataset:` line names the dataset (or collection) the entries below it are for. The
  build warns about a card that asks to be cited and has no entry.
- `metadata_fixes.md`: where the site corrects the metadata on the Hub (probe names, probe
  types, transmit schemes, institutions), and the fix at the source for each.
- `assets/img/examples*` (the banner: the paper's collages as webp, and the tile frames the
  page fades one at a time) are checked in. The paper's figure scripts made them; they are
  not in this repository.
- `assets/img/logos/` (the plates under the buttons: every affiliation in the author list, in
  its order, then the steering committee's institutions) are checked in, from Wikimedia
  Commons, Wikipedia or the institution's own site, cropped to their content. Add a plate to
  `index.html` for an affiliation added to `scripts/authors.csv`.
- `assets/img/logo/` (the logo as SVG and PNG, with and without the glow, on a
  transparent, black and white background): `logo.py`.

  ```bash
  uv run --no-project --with resvg-py python site/logo.py
  ```
- `assets/img/logo/banner.svg` (the banner of the README, with this logo): `banner.py`.

  ```bash
  uv run --no-project --with resvg-py --with fonttools python site/banner.py
  ```

## Deployment

`.github/workflows/pages.yml` builds the site on pull requests to `main` and on pushes to
`main` that touch its inputs (`site/`, `scripts/authors.csv`, `scripts/compile_authors.py`,
`plots/openh_rf_datasets.py`), and deploys it to GitHub Pages after a push (or on demand).
