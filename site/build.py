"""Build the OpenH-RF website into a static directory.

The site is plain HTML/CSS/JS (``site/index.html`` + ``site/assets/``) that renders
``data/datasets.json`` client-side. This script writes that JSON from

* ``site/hub/cards.json``: the data cards, as ``cards.py`` reads them from the clone;
* ``site/hub/corpus.json``: statistics of every HDF5 file, condensed by ``corpus.py``
  from the scan in ``stats/data/``, and ``site/hub/files.json``, what each file is
  filtered on, for the explorer's download script;
* ``site/catalog.yaml``: the filters' vocabulary, and overrides for the few values
  derived here that are wrong;
* ``site/zea_keys.json``: the zea file-format key tree, from ``zea_keys.py``;
* ``site/citation_suggestions.bib``: the citations in the data cards;
* ``plots/openh_rf_datasets.py``: each dataset's short name, which the page shows and
  links it by.

It writes the author list into the page from ``scripts/authors.csv``, marked as
``scripts/compile_authors.py`` marks it in the paper. Each author links to their page in
``site/author_websites.csv``, and each affiliation to the explorer filtered by its
institution, as ``site/institution_filters.csv`` names it. That file also lists the
institutions datasets are from that are no author's affiliation.

``update.py`` refreshes the ``site/hub/`` files and then runs this. The build
itself needs only PyYAML, and no network. Usage (from the repository root)::

    uv run python site/build.py            # build into site/_site
    uv run python site/build.py --serve    # build, then serve on port 8000
    uv run python site/build.py --check    # only validate catalog.yaml
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import functools
import hashlib
import html
import http.server
import importlib.util
import json
import re
import shutil
import urllib.parse
from pathlib import Path

import yaml

SITE = Path(__file__).resolve().parent
HUB = SITE / "hub"
CATALOG = SITE / "catalog.yaml"
ZEA_KEYS = SITE / "zea_keys.json"
DATASET_NAMES = SITE.parent / "plots" / "openh_rf_datasets.py"
COMPILE_AUTHORS = SITE.parent / "scripts" / "compile_authors.py"
AUTHOR_WEBSITES = SITE / "author_websites.csv"
INSTITUTION_FILTERS = SITE / "institution_filters.csv"
CITATIONS = SITE / "citation_suggestions.bib"
# Where index.html takes the author list.
AUTHORS_MARK = "<!-- authors -->"

HF_REPO = "nvidia/OpenH-RF"
HF_URL = f"https://huggingface.co/datasets/{HF_REPO}"


FACETS = ("setting", "targets", "acquisition", "probe_types", "data_type", "tasks")
# The card sections a facet's match words are looked up in.
MATCH_IN = {
    "targets": ("description", "characterization", "subject_metadata"),
    "tasks": ("description", "intended_usage"),
}


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) if path.suffix == ".yaml" else json.loads(text)


def dataset_names() -> dict[str, str]:
    """The short name of each dataset, by its folder in the Hub repo."""
    spec = importlib.util.spec_from_file_location("openh_rf_datasets", DATASET_NAMES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = module.HF_ROOT + "/"
    return {entry["hf"].removeprefix(root): short for short, entry in module.DATASETS.items()}


def authors_html(institutions: set[str]) -> str:
    """The author list: the core team, the contributors and the senior authors, each with
    the numbers of their affiliations and the paper's marks, then the affiliations. The
    names are abbreviated as in the paper. Each affiliation links to the explorer filtered
    by its institution, as ``institution_filters.csv`` names it; that file must list each
    of ``institutions`` (the datasets' institutions) exactly once, and no other.

    An author with several affiliations has their numbers comma-separated in "Affiliation
    order" and the names, in the same order, in "Affiliation".
    """
    spec = importlib.util.spec_from_file_location("compile_authors", COMPILE_AUTHORS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = str(module.DEFAULT_CSV)
    rows = sorted(module.read_rows(source), key=lambda row: module.sort_key(row, source))

    affiliations: dict[int, str] = {}
    numbers = []
    for row in rows:
        own = [int(n) for n in row["Affiliation order"].split(",")]
        names = [row["Affiliation"]] if len(own) == 1 else row["Affiliation"].split(",")
        if len(names) != len(own):
            raise SystemExit(
                f"{source}: {row['Author']} has affiliations {own} but {row['Affiliation']!r}"
            )
        for n, name in zip(own, names):
            name = " ".join(name.split())
            if affiliations.setdefault(n, name) != name:
                raise SystemExit(
                    f"{source}: affiliation {n} is both {affiliations[n]!r} and {name!r}"
                )
        numbers.append(own)
    if sorted(affiliations) != list(range(1, len(affiliations) + 1)):
        raise SystemExit(f"{source}: the affiliations are not numbered 1 to {len(affiliations)}")

    count = len(rows)
    marks = [[] for _ in rows]
    for i in range(module.EQUAL_FIRST):
        marks[i].append("*")
    for i in range(count - module.EQUAL_SENIOR, count):
        marks[i].append("†")
    for i in [*range(module.CORE_TEAM_FIRST), *range(count - module.CORE_TEAM_LAST, count)]:
        marks[i].append("§")

    with open(AUTHOR_WEBSITES, newline="", encoding="utf-8") as f:
        pages = {row["author"]: row["website"] for row in csv.DictReader(f)}
    abbreviated = [module.normalise(row["Abbreviation"]) for row in rows]
    names = []
    for row, name, own, mark in zip(rows, module.disambiguate(abbreviated, rows), numbers, marks):
        sup = ",".join([*map(str, own), *mark])
        label = html.escape(name)
        author = " ".join((row["Author"] or row["Abbreviation"]).split())
        if author not in pages:
            print(f"warning: {AUTHOR_WEBSITES.name} has no row for {author!r}")
        elif pages[author]:
            label = f'<a href="{html.escape(pages[author])}">{label}</a>'
        names.append(f'<span class="author">{label}<sup>{sup}</sup></span>')
    groups = [
        names[: module.CORE],
        names[module.CORE : count - module.SENIOR],
        names[count - module.SENIOR :],
    ]
    listed = "".join(f'<p class="authors-names">{", ".join(group)}</p>' for group in groups)
    with open(INSTITUTION_FILTERS, newline="", encoding="utf-8") as f:
        entries = list(csv.DictReader(f))
    filters = {row["affiliation"]: row["institution"] for row in entries if row["affiliation"]}
    # Each institution exactly once.
    problems = []
    named: dict[str, str] = {}
    places = []
    for n, name in sorted(affiliations.items()):
        institution = filters.get(name)
        if institution is None:
            problems.append(f"{INSTITUTION_FILTERS.name} has no row for {name!r}")
        elif not institution:
            problems.append(f"{INSTITUTION_FILTERS.name} names no institution for {name!r}")
        elif institution in named:
            problems.append(f"{name!r} and {named[institution]!r} are both {institution!r}")
        elif institution not in institutions:
            problems.append(f"no dataset is from {institution!r}, the affiliation {name!r}")
        if institution:
            named.setdefault(institution, name)
        href = "#explorer?" + urllib.parse.urlencode({"institution": institution})
        label = f'<a href="{html.escape(href)}">{html.escape(name)}</a>'
        places.append(f'<span class="affiliation"><sup>{n}</sup>{label}</span>')
    # The institutions datasets are from that are no author's affiliation.
    for institution in (row["institution"] for row in entries if not row["affiliation"]):
        if not institution:
            problems.append(f"{INSTITUTION_FILTERS.name} has a row with neither name")
        elif institution in named:
            problems.append(f"{institution!r} is in {INSTITUTION_FILTERS.name} twice")
        elif institution not in institutions:
            problems.append(f"no dataset is from {institution!r}, in {INSTITUTION_FILTERS.name}")
        named.setdefault(institution, "")
    problems += [
        f"{i!r}, a dataset's institution, is not in {INSTITUTION_FILTERS.name}; add a row for"
        " it with an empty affiliation or, if it is a listed one named differently, an"
        " `institution` override in catalog.yaml"
        for i in sorted(institutions - set(named))
    ]
    if problems:
        raise SystemExit("institution problems:\n  " + "\n  ".join(problems))
    places = ", ".join(places)
    return f'{listed}<p class="authors-affiliations">{places}</p>'


@functools.cache
def citations() -> dict[str, list[dict]]:
    """The BibTeX in citation_suggestions.bib for each dataset or collection."""
    text = CITATIONS.read_text(encoding="utf-8")
    found = {}
    for names, block in re.findall(
        r"^% dataset: ([^\n]+)\n(.*?)(?=^% dataset:|\Z)", text, re.M | re.S
    ):
        entries = [citation(e.strip()) for e in re.split(r"^(?=@)", block, flags=re.M)[1:]]
        for name in names.split():
            found[name] = entries
    return found


def citation(entry: str) -> dict:
    fields = bib_fields(entry)

    def get(name: str) -> str:
        return latex(fields.get(name, ""))

    # split on "and" outside braces
    names = re.split(r"\s+and\s+(?![^{]*\})", fields.get("author", ""))
    authors = [bib_name(n) for n in names if n != "others"]
    shown = f"{authors[0]} et al." if len(authors) > 2 or "others" in names else "; ".join(authors)
    venue = get("journal") or get("booktitle") or get("publisher") or get("archiveprefix")
    if "school" in fields:
        venue = f"PhD thesis, {get('school')}"
    volume = get("volume")
    if "number" in fields:
        volume += f" ({get('number')})"
    pages = get("pages").replace("-", "–")
    details = ": ".join(part for part in (volume, pages) if part)
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", fields.get("doi", ""))
    return {
        "authors": shown,
        "year": get("year"),
        "title": get("title"),
        "venue": venue,
        "details": details or get("eprint"),
        "link": f"https://doi.org/{doi}" if doi else fields.get("url"),
        "bibtex": entry,
    }


def bib_fields(entry: str) -> dict[str, str]:
    """The fields of a BibTeX entry by lower-case name."""
    fields = {}
    for line in entry.rstrip().removesuffix("}").splitlines()[1:]:
        if not line.strip():
            continue
        m = re.fullmatch(r"\s*(\w+)\s*=\s*\{?(.*?)\}?,?\s*", line)
        if not m:
            raise SystemExit(f"{CITATIONS.name}: put each field on one line: {line!r}")
        fields[m[1].lower()] = m[2]
    return fields


def bib_name(name: str) -> str:
    split = re.fullmatch(r"(.+?)\s+(\{[^}]*\}|\S+)", name)
    if "," in name or name.startswith("{") or not split:
        return latex(name)
    return f"{latex(split[2])}, {latex(split[1])}"


def latex(text: str) -> str:
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)
    text = text.replace(r"{\o}", "ø").replace(r"\&", "&").replace("--", "–")
    text = " ".join(text.replace("{", "").replace("}", "").split())
    if "\\" in text:
        raise SystemExit(f"{CITATIONS.name}: add the LaTeX in {text!r} to build.latex()")
    return text


def validate(catalog: dict) -> list[str]:
    """Problems with catalog.yaml: overrides outside the vocabulary, bad match patterns."""
    problems = []
    vocab = catalog["vocabulary"]
    for facet, values in vocab.items():
        for value, term in values.items():
            try:
                re.compile(term.get("match", ""))
            except re.error as exc:
                problems.append(f"vocabulary {facet}.{value}: bad match ({exc})")
            for other in term.get("includes", []):
                if other not in values:
                    problems.append(
                        f"vocabulary {facet}.{value}: includes {other!r}, not in {facet}"
                    )
    for eid, fields in (catalog.get("datasets") or {}).items():
        others = fields.get("collaborating_institutions", [])
        if not isinstance(others, list) or not all(isinstance(i, str) for i in others):
            problems.append(f"{eid}: collaborating_institutions is not a list of names")
        for facet in FACETS + ("dimensionality",):
            values = fields.get(facet, [])
            for value in [values] if isinstance(values, str) else values:
                if value not in vocab[facet]:
                    problems.append(f"{eid}: {facet} value {value!r} not in vocabulary")
    return problems


def classify(card: dict, measured: dict, vocab: dict) -> dict:
    """The facets of a dataset: most from its files, targets and tasks from its card."""
    probes = [p for p in measured["probe_class"] if p != "unspecified"]
    dims = {"3d" if p in ("matrix", "row_column") else "2d" for p in probes}
    acquisition = list(measured["transmit_kinds"]) + ["tomographic"] * ("ring" in probes)
    anatomy = measured["layout"]["keys"].get("metadata/annotations/anatomy", {})

    def matching(facet: str) -> list[str]:
        text = [card["pretty_name"] or "", *anatomy.get("values", [])]
        text += [card["text"].get(name, "") for name in MATCH_IN[facet]]
        return [
            value
            for value, term in vocab[facet].items()
            if "match" in term and re.search(term["match"], " ".join(" ".join(text).split()), re.I)
        ]

    setting = [m for m in measured["medium"] if m in vocab["setting"]]
    setting += [f"in_vivo_{s}" for s in measured["species"]]
    targets = matching("targets")
    targets = [
        v
        for v, term in vocab["targets"].items()
        if v in targets or set(term.get("includes", [])) & set(targets)
    ]
    if "simulation" in setting and "numerical_medium" not in targets:
        targets.append("numerical_medium")
    return {
        "setting": setting,
        "acquisition": acquisition or ["unspecified"],
        "probe_types": probes,
        "dimensionality": "mixed" if len(dims) > 1 else next(iter(dims), "2d"),
        "data_type": [s for s, n in measured["signal"].items() if n],
        "targets": targets,
        "tasks": matching("tasks"),
    }


def key_product(key: str) -> str | None:
    """The browsable unit a key belongs to: a data product (``data/image``), a metadata
    group (``metadata/ecg``, ``metadata/annotations/view``) or ``custom``. Scan, probe
    and track-level keys describe the acquisition and are not faceted."""
    parts = key.split("/")
    if parts[0] == "custom":
        return "custom"
    if parts[0] in ("data", "metrics") and len(parts) > 1:
        return "/".join(parts[:2])
    if parts[0] == "metadata" and len(parts) > 1:
        depth = 3 if parts[1] == "annotations" else 2
        return "/".join(parts[:depth])
    return None


def is_standard_key(key: str, zea_keys: dict) -> bool:
    """Whether zea defines ``key``; ``custom/`` is zea's extension point for keys of one's own."""
    if key.startswith("custom/") or key == "custom":
        return True
    return key.removesuffix("/*") in zea_keys


def covers(card_key: str, key: str) -> bool:
    """Whether a key listed on a data card (a field, a group or a glob) covers a file key."""
    return key == card_key or key.startswith(card_key + "/") or fnmatch.fnmatchcase(key, card_key)


def name_axes(key: str, shape: list[list], zea_keys: dict) -> list[list]:
    """Pair each axis with its name in the zea spec: ``[[[1, 25, 40], "n_frames"], ...]``."""
    for names in zea_keys.get(key, {}).get("shapes", []):
        if len(names) == len(shape) and "..." not in names:
            return [
                [size, name if isinstance(name, str) else None] for size, name in zip(shape, names)
            ]
    return [[size, None] for size in shape]


def file_layout(layout: dict, card_keys: list[str], zea_keys: dict) -> dict:
    """What the files hold, and how it compares with the keys on the data card."""
    keys = [
        {
            "key": key,
            **entry,
            "shapes": [name_axes(key, shape, zea_keys) for shape in entry["shapes"]],
            "on_card": any(covers(c, key) for c in card_keys),
        }
        for key, entry in layout["keys"].items()
    ]
    return {
        "tracks": layout["tracks"],
        "attrs": layout["attrs"],
        "keys": keys,
        "card_only": [c for c in card_keys if not any(covers(c, k) for k in layout["keys"])],
    }


def build_records(catalog: dict, cards: dict, corpus: dict, zea: dict) -> list[dict]:
    overrides = catalog.get("datasets") or {}
    names = dataset_names()
    previewed = (cards.get("preview") or {}).get("files", {})
    records = []
    for eid, card in cards["cards"].items():
        measured = corpus["datasets"].get(eid)
        if measured is None:
            print(f"warning: {eid} has a data card but no HDF5 files; left out")
            continue
        if eid not in names:
            print(f"warning: {eid} has no short name in {DATASET_NAMES.name}; shown as its folder")
        derived = classify(card, measured, catalog["vocabulary"])
        name = names.get(eid, eid)
        # A dataset that a previewed pull request changes links to that pull request.
        pull = previewed.get(f"{eid}/README.md") or next(
            (n for path, n in previewed.items() if path.startswith(eid + "/")), None
        )
        ref = f"refs%2Fpr%2F{pull}" if pull else "main"
        record = {
            "id": eid,
            "name": name,
            "title": name,
            "pretty_name": card["pretty_name"] or eid,
            "institution": " & ".join(card["institutions"]) or None,
            "collaborating_institutions": [],
            "collection": card["collection"],
            "collection_title": cards["collections"].get(card["collection"]),
            **{k: card[k] for k in ("summary", "contributors", "license", "created")},
            "known_issues": card["known_issues"],
            "hf_tags": card["tags"],
            **derived,
            "species": list(measured["species"]),
            "probes": list(measured["probes"]),
            "probe_models": list(measured["probe_models"]),
            "systems": list(measured["scanners"]),
            "keys": card["keys"],
            "hub_url": f"{HF_URL}/tree/{ref}/{eid}",
            "card_url": f"{HF_URL}/blob/{ref}/{eid}/README.md",
            "image_source": card.get("image", {}).get("source"),
            **{k: v for k, v in card.get("image", {}).items() if k != "source"},
        }
        # `figure` and `thumb_position` are for cards.py, which renders the figure.
        record.update(
            {
                k: v
                for k, v in overrides.get(eid, {}).items()
                if k not in ("figure", "thumb_position")
            }
        )
        # The main institutions, which the page shows, then the collaborating ones, which only
        # search and the institution filter use.
        main = record["institution"].split(" & ") if record["institution"] else []
        record["institutions"] = main + record["collaborating_institutions"]
        record["citations"] = citations().get(eid) or citations().get(card["collection"]) or []
        if card["cites"] and not record["citations"]:
            print(f"warning: {eid} asks to be cited, but has no entry in {CITATIONS.name}")
        layout = measured.pop("layout")
        record["measured"] = measured
        record["files"] = file_layout(layout, record["keys"], zea["keys"])
        keys = record["keys"] + [k for k in layout["keys"] if k not in record["keys"]]
        record["key_products"] = list(dict.fromkeys(filter(None, map(key_product, keys))))
        record["nonstandard_keys"] = [k for k in keys if not is_standard_key(k, zea["keys"])]
        records.append(record)
    unknown = citations().keys() - {r["id"] for r in records} - set(cards["collections"])
    if unknown:
        raise SystemExit(f"{CITATIONS.name}: no dataset {', '.join(sorted(unknown))}")
    return records


def file_profiles(
    record: dict, profiles: list[dict], overridden: set[str], vocab: dict
) -> list[dict]:
    """The facets of each kind of file in a dataset, for the explorer's download script."""
    # classify() reads the card for targets and tasks; a file gets its targets below instead.
    classified = [classify({"pretty_name": "", "text": {}}, p, vocab) for p in profiles]
    live = {"in_vivo_human", "in_vivo_animal", "ex_vivo"}
    tissue = [bool(live & set(v["setting"])) for v in classified]
    mixed = len(set(tissue)) > 1  # tissue next to phantoms or simulations
    simulated = ["simulation" in v["setting"] for v in classified]
    anatomy = [t for t in record["targets"] if vocab["targets"][t].get("group") == "Anatomy"]

    def named(values: dict) -> list[str]:
        return [t for t in record["targets"] if t in values["targets"] and t != "numerical_medium"]

    # A file keeps the dataset targets its own anatomy names. The anatomies no file names go
    # to the files that name none, or to every file when they all name one; the phantoms and
    # simulations of a mixed dataset only get what they name.
    claimed = {t for v in classified for t in named(v)}
    unclaimed = [t for t in anatomy if t not in claimed]
    all_named = all(named(v) for v in classified)
    out = []
    for i, (p, values) in enumerate(zip(profiles, classified)):
        targets = named(values)
        if (not targets or all_named) and (tissue[i] or not mixed):
            targets += unclaimed
        # Phantoms and media apply to every file, except that in a mixed dataset tissue files
        # only get microbubbles, and only simulated files are a numerical medium.
        media = [t for t in record["targets"] if t not in anatomy]
        if mixed and tissue[i]:
            media = [t for t in media if t == "microbubbles"]
        if any(simulated) and not simulated[i]:
            media = [t for t in media if t != "numerical_medium"]
        values["targets"] = [t for t in record["targets"] if t in targets or t in media]
        del values["tasks"]
        values["dimensionality"] = [values["dimensionality"]]
        if record["dimensionality"] == "mixed":
            values["dimensionality"].append("mixed")  # selecting "2D + 3D" keeps all of its files
        values.update({k: record[k] for k in overridden if k in values})
        values["key_products"] = list(dict.fromkeys(filter(None, map(key_product, p["keys"]))))
        values["measured"] = {k: p[k] for k in ("dtype", "coverage", "range")}
        out.append(values)
    return out


def build(out: Path) -> dict:
    catalog = load(CATALOG)
    problems = validate(catalog)
    if problems:
        raise SystemExit("catalog.yaml problems:\n  " + "\n  ".join(problems))
    cards, corpus, zea = load(HUB / "cards.json"), load(HUB / "corpus.json"), load(ZEA_KEYS)
    files = load(HUB / "files.json")
    if files["revision"] != cards["revision"]:
        raise SystemExit(
            "hub/files.json and hub/cards.json are of different revisions; run site/update.py"
        )

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    records = build_records(catalog, cards, corpus, zea)
    page = versioned(SITE / "index.html")
    if AUTHORS_MARK not in page:
        raise SystemExit(f"index.html has no {AUTHORS_MARK} for the author list")
    institutions = {i for r in records for i in r["institutions"]}
    page = page.replace(AUTHORS_MARK, authors_html(institutions))
    (out / "index.html").write_text(page, encoding="utf-8")
    shutil.copytree(SITE / "assets", out / "assets")
    shutil.copytree(HUB / "images", out / "images")
    (out / ".nojekyll").touch()
    index = {
        "schema_version": 3,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "measured": {k: v for k, v in corpus.items() if k != "datasets"},
        "vocabulary": catalog["vocabulary"],
        "zea": {"version": zea["zea_version"], "keys": zea["keys"]},
        "dataset_count": len(records),
        # The authors' affiliations and the other institutions the datasets are from.
        "institution_count": len(institutions),
        "datasets": records,
    }
    (out / "data").mkdir()
    text = compact_lists(json.dumps(index, indent=1, ensure_ascii=False))
    (out / "data" / "datasets.json").write_text(text + "\n")
    # Per dataset, its files as [path in its folder, kind, size] and the facets of each kind,
    # for the explorer's download script.
    overrides = catalog.get("datasets") or {}
    by_file = {"revision": files["revision"], "datasets": {}}
    for r in records:
        entry = files["datasets"][r["id"]]
        profiles = file_profiles(
            r, entry["profiles"], set(overrides.get(r["id"], {})), catalog["vocabulary"]
        )
        by_file["datasets"][r["id"]] = {"profiles": profiles, "files": entry["files"]}
    (out / "data" / "files.json").write_text(
        json.dumps(by_file, separators=(",", ":"), ensure_ascii=False) + "\n"
    )
    return index


def versioned(page: Path) -> str:
    """Prevent browsers from showing an old version."""
    return re.sub(
        r'((?:href|src)=")(assets/[^"?]+\.(?:css|js))"',
        lambda m: f'{m[1]}{m[2]}?v={hashlib.sha1((SITE / m[2]).read_bytes()).hexdigest()[:8]}"',
        page.read_text(encoding="utf-8"),
    )


def compact_lists(text: str) -> str:
    """Put arrays of numbers on one line; ``indent=1`` would give each number its own."""
    return re.sub(
        r"\[\s*(-?[\d.e+-]+(?:,\s*-?[\d.e+-]+)*)\s*\]",
        lambda m: "[" + " ".join(m.group(1).split()) + "]",
        text,
    )


def serve(out: Path, port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
        print(f"Serving {out} at http://0.0.0.0:{port}/ (Ctrl+C to stop)")
        httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=SITE / "_site", help="output directory")
    parser.add_argument("--check", action="store_true", help="validate catalog.yaml and exit")
    parser.add_argument("--serve", action="store_true", help="serve the build afterwards")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.check:
        problems = validate(load(CATALOG))
        print("\n".join(problems) or "catalog.yaml is valid")
        raise SystemExit(1 if problems else 0)

    index = build(args.out.resolve())
    print(f"Built {index['dataset_count']} datasets into {args.out}")
    if args.serve:
        serve(args.out.resolve(), args.port)


if __name__ == "__main__":
    main()
