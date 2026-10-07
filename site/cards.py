"""Read the data cards into ``site/hub/cards.json``, with a figure for each.

The cards come from ``huggingface/OpenH-RF``, the clone of the Hub repo's documents (see
``huggingface/README.md``).
Every folder with a README.md and no deeper one is a dataset, and that README is its data
card. From each card this keeps the frontmatter (pretty name, license, tags) and the card
template sections the page shows or matches the vocabulary against. It also renders a
thumbnail and a preview of the card's leading figure into ``site/hub/images/``, or of
``site/figures/<id>.png`` for a card whose figure is not on the Hub. The clone leaves the
figures out, so they are downloaded from the Hub at its revision.
``update.py`` runs this.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import subprocess
import urllib.parse
from pathlib import Path

import yaml
from huggingface_hub import hf_hub_download
from PIL import Image

SITE = Path(__file__).resolve().parent
DOCS = SITE.parent / "huggingface" / "OpenH-RF"
CARDS = SITE / "hub" / "cards.json"
IMAGES = SITE / "hub" / "images"
FIGURES = SITE / "figures"
CATALOG = SITE / "catalog.yaml"
REPO = "nvidia/OpenH-RF"

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
# Thumbnails are square crops, sharp on a high-density screen in the widest gallery tile.
THUMB_SIDE = 640
PREVIEW_SIZE = (1200, 900)

# Card template sections, and how their headings start (a few cards use other names).
SECTIONS = {
    "description": "dataset (description|summary)",
    "contributors": "(dataset )?contributor",
    "created": "dataset creation",
    "intended_usage": "intended usage|suggested tasks",
    "characterization": "dataset characteri[sz]ation",
    "subject_metadata": "subject metadata",
    "known_issues": "known issues|limitations",
}
# "Concordia University", "University of Colorado Boulder", "NVIDIA Corporation", ...
ORGANISATION = re.compile(
    r"(?:[A-Z][\w.'&-]*\s+)*"
    r"(?:Universit\w+|Institutes?|College|Hospital|Politecnico|Polytechnique)"
    r"(?:\s+(?:of|at|di|de|for)(?:\s+[A-Z][\w.'-]*)+)?"
    r"|(?:[A-Z][\w.'&-]*\s+)+(?:Corporation|Inc|Ltd)\b"
)


def split_card(text: str) -> tuple[dict, dict[str, str]]:
    """The frontmatter and the template sections of a card, plus its ``#`` title."""
    front = {}
    match = re.match(r"---\s*\n(.*?)\n---\s*\n", text, re.S)
    if match:
        front = yaml.safe_load(match.group(1)) or {}
        text = text[match.end() :]
    title = re.search(r"^# (.+)$", text, re.M)
    sections = {"title": title.group(1).strip() if title else None}
    for heading, body in re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        name = next((n for n, start in SECTIONS.items() if re.match(start, heading, re.I)), None)
        if name:
            sections.setdefault(name, body.strip())
    return front, sections


def plain(markdown: str) -> str:
    """Markdown as plain text: no images, tables or markup, links reduced to their text."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)|<[^>]+>|^\|.*$|^#+ ", "", markdown, flags=re.M)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return re.sub(r"\*\*|`", "", text).strip()


def first_paragraph(markdown: str, limit: int) -> str | None:
    """The first paragraph, with its line breaks (a list stays one), cut after a sentence
    if it is longer than ``limit``."""
    paragraph = next((p for p in plain(markdown).split("\n\n") if p.strip()), None)
    if paragraph is None:
        return None
    text = "\n".join(" ".join(line.split()) for line in paragraph.strip().splitlines())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind(".\n"))
    return cut[: end + 1] or cut + "…"


def parse(text: str) -> dict:
    """What the site takes from one data card."""
    front, sections = split_card(text)
    contributors = re.sub(r"\s*<?\S+@\S+", "", sections.get("contributors", ""))
    contributors = re.sub(r"^\|.*\n\|[-:| ]+$", "", contributors, flags=re.M)  # table header
    # One line per contributor, table rows included ("Name | Affiliation").
    lines = [re.sub(r"\s*\|\s*", ", ", line.strip("-*| \t")) for line in contributors.splitlines()]
    issues = first_paragraph(sections.get("known_issues", ""), 600)
    return {
        "pretty_name": front.get("pretty_name") or sections["title"],
        "license": front.get("license"),
        "tags": front.get("tags") or [],
        "summary": first_paragraph(sections.get("description", ""), 600),
        "contributors": [
            plain(line) for line in lines if re.search("[a-z]", line) and not line.endswith(":")
        ],
        "institutions": list(
            dict.fromkeys(m.removeprefix("The ") for m in ORGANISATION.findall(contributors))
        ),
        "created": first_paragraph(sections.get("created", ""), 200),
        # Whether the card asks to be cited, for build.py to check that it has the citation.
        "cites": bool(re.search(r"^#+ .*citation|\bcite\b", text, re.M | re.I)),
        # HDF5 keys the card documents, such as `data/raw_data` or `/tracks/track_N/scan`.
        # File names (`data/a1.hdf5`) have a dot and do not match.
        "keys": sorted(
            {
                re.sub(r"^/?(tracks/track_\w+/)?", "", key)
                for key in re.findall(r"`(/?[a-z_]+(?:/[\w*]+)+)`", text)
                if re.match(
                    r"/?(tracks/track_\w+/|(data|scan|probe|metadata|metrics|custom)/)", key
                )
            }
        ),
        "known_issues": None
        if re.match(r"[-* ]*(none|n/?a|no known)\b", issues or "none", re.I)
        else issues,
        # Plain text that the vocabulary's match words are looked up in.
        "text": {
            name: plain(sections[name])
            for name in ("description", "intended_usage", "characterization", "subject_metadata")
            if name in sections
        },
    }


def pick_image(
    card: str, text: str, files: set[str], sizes: dict[str, int], figure: str | None = None
) -> str | None:
    """A card's figure: assets/main.png, then ``figure`` (a path in the card's folder, from
    catalog.yaml), then assets/hero.png, then the largest other PNG in assets/, then any
    other image: main.* and hero.* first, then the images the card embeds, then the rest
    of assets/. Logos are skipped. ``sizes`` holds the size of each PNG in assets/."""
    folder = posixpath.dirname(card)
    if figure:
        figure = f"{folder}/{figure}"
        if figure not in files:
            raise SystemExit(f"catalog.yaml: {figure} is not in the Hub repo")
    assets = sorted(
        f
        for f in files
        if posixpath.dirname(f) == f"{folder}/assets" and f.lower().endswith(IMAGE_SUFFIXES)
    )
    embedded = [
        posixpath.normpath(f"{folder}/{urllib.parse.unquote(ref)}")
        for pair in re.findall(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)|<img[^>]*\bsrc=[\"']([^\"']+)", text)
        for ref in pair
        if ref and "://" not in ref
    ]
    main = [f for f in assets if posixpath.basename(f).lower().startswith("main.")]
    hero = [f for f in assets if posixpath.basename(f).lower().startswith("hero.")]
    found = [
        path
        for path in main + hero + [figure] + embedded + assets
        if path in files and path.lower().endswith(IMAGE_SUFFIXES) and "logo" not in path.lower()
    ]
    pngs = {path for path in found if path in assets and path.lower().endswith(".png")}
    return min(
        found,
        key=lambda path: (
            path.lower() != f"{folder}/assets/main.png".lower(),
            path != figure,
            path.lower() != f"{folder}/assets/hero.png".lower(),
            path not in pngs,
            -sizes[path] if path in pngs else 0,
        ),
        default=None,
    )


def png_sizes(blobs: dict[str, str]) -> dict[str, int]:
    """The size of each PNG in an assets/ folder, read from its LFS pointer (or from its blob,
    if it is not in LFS), as the checkout leaves the figures out."""
    paths = [
        p
        for p in blobs
        if p.lower().endswith(".png") and posixpath.basename(posixpath.dirname(p)) == "assets"
    ]
    out = subprocess.run(
        ["git", "-C", str(DOCS), "cat-file", "--batch"],
        input="".join(f"{blobs[p]}\n" for p in paths).encode(),
        check=True,
        capture_output=True,
    ).stdout
    sizes = {}
    for path in paths:
        header, _, out = out.partition(b"\n")
        length = int(header.split()[2])
        body, out = out[:length], out[length + 1 :]
        pointer = re.match(rb"version https://git-lfs\S*\noid \S+\nsize (\d+)", body)
        sizes[path] = int(pointer[1]) if pointer else length
    return sizes


def crop_position(position: str | None) -> tuple[float, float]:
    """Where a crop sits along x and y (0 to 1), from a CSS object-position such as
    ``right`` or ``'10% 50%'``; the centre by default."""
    at = [0.5, 0.5]
    keywords = {"left": (0, 0), "right": (0, 1), "top": (1, 0), "bottom": (1, 1)}
    for i, word in enumerate((position or "").split()):
        if word.endswith("%"):
            at[min(i, 1)] = float(word[:-1]) / 100
        elif word in keywords:
            axis, value = keywords[word]
            at[axis] = value
        elif word != "center":
            raise SystemExit(f"catalog.yaml: thumb_position {position!r} is not understood")
    return at[0], at[1]


def render(
    src: Path, dst: Path, size: tuple[int, int], crop: tuple[float, float] | None = None
) -> None:
    """Write the first frame of an image as a JPEG no larger than ``size``. With ``crop``
    (from ``crop_position``), first cut the image to the aspect ratio of ``size``."""
    with Image.open(src) as im:
        frame = im.convert("RGBA")
    flat = Image.new("RGB", frame.size, "white")
    flat.paste(frame, mask=frame.getchannel("A"))
    if crop:
        scale = min(flat.width / size[0], flat.height / size[1])
        width, height = round(size[0] * scale), round(size[1] * scale)
        left = round((flat.width - width) * crop[0])
        top = round((flat.height - height) * crop[1])
        flat = flat.crop((left, top, left + width, top + height))
    flat.thumbnail(size, Image.LANCZOS)
    flat.save(dst, "JPEG", quality=85, optimize=True, progressive=True)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(DOCS), *args], check=True, capture_output=True, text=True
    ).stdout


def update(merge: dict | None = None) -> dict:
    """Rewrite ``cards.json`` and the images from the clone. Returns the cards added,
    changed and removed.

    ``merge`` is what ``preview.merge`` returns, with the clone on that merge: the
    revision is then main's, and a figure from a pull request is downloaded from its commit.
    """
    if not (DOCS / "README.md").is_file():
        raise SystemExit(f"{DOCS} is empty; run ./huggingface/setup.sh")
    revision, date = git("log", "-1", "--format=%H %cs", merge["base"] if merge else "HEAD").split()
    commits = {}
    if merge:
        by_number = {p["number"]: p["commit"] for p in merge["pull_requests"]}
        commits = {path: by_number[n] for path, n in merge["files"].items()}
    # Every file with its blob id, including those the sparse checkout leaves out.
    listing = git("ls-tree", "-rz", "HEAD").split("\0")
    blobs = {e.split("\t", 1)[1]: e.split()[2] for e in listing if e}

    readmes = [p for p in blobs if p.endswith("/README.md")]
    texts = {p: (DOCS / p).read_text("utf-8") for p in readmes}
    folders = [posixpath.dirname(p) for p in readmes]
    leaves = [f for f in folders if not any(o.startswith(f + "/") for o in folders)]
    collections = {
        f: parse(texts[f"{f}/README.md"])["pretty_name"] for f in folders if f not in leaves
    }

    IMAGES.mkdir(parents=True, exist_ok=True)
    sizes = png_sizes(blobs)
    overrides = yaml.safe_load(CATALOG.read_text("utf-8")).get("datasets") or {}
    cards = {}
    for eid in sorted(leaves):
        card = f"{eid}/README.md"
        collection = next((c for c in collections if eid.startswith(c + "/")), None)
        figure = overrides.get(eid, {}).get("figure")
        image = pick_image(card, texts[card], set(blobs), sizes, figure)
        if image is None and collection:
            image = pick_image(
                f"{collection}/README.md", texts[f"{collection}/README.md"], set(blobs), sizes
            )
        cards[eid] = {"sha": blobs[card], "collection": collection, **parse(texts[card])}
        slug = re.sub(r"[^a-z0-9]+", "-", eid.lower())
        if image:
            version = blobs[image][:7]
        elif local := next(FIGURES.glob(f"{slug}.*"), None):
            image = f"site/figures/{local.name}"
            version = hashlib.sha1(local.read_bytes()).hexdigest()[:7]
        if image:
            position = overrides.get(eid, {}).get("thumb_position")
            crop = crop_position(position)
            # The thumbnail's name changes with its size and crop, so a change renders it again.
            key = hashlib.sha1(f"{THUMB_SIDE} {crop}".encode()).hexdigest()[:4]
            thumb, preview = (
                IMAGES / f"{slug}-{version}-{key}.jpg",
                IMAGES / f"{slug}-{version}-preview.jpg",
            )
            if not (thumb.is_file() and preview.is_file()):
                src = SITE.parent / image
                if not image.startswith("site/"):
                    src = hf_hub_download(
                        REPO, image, repo_type="dataset", revision=commits.get(image, revision)
                    )
                render(src, thumb, (THUMB_SIDE, THUMB_SIDE), crop)
                render(src, preview, PREVIEW_SIZE)
            with Image.open(preview) as im:
                size = list(im.size)
            cards[eid]["image"] = {
                "source": image,
                "thumb": f"images/{thumb.name}",
                "preview": f"images/{preview.name}",
                "preview_size": size,
            }

    used = {
        Path(c["image"][k]).name
        for c in cards.values()
        if "image" in c
        for k in ("thumb", "preview")
    }
    for path in IMAGES.glob("*.jpg"):
        if path.name not in used:
            path.unlink()
    before = json.loads(CARDS.read_text())["cards"] if CARDS.is_file() else {}
    out = {
        "revision": revision,
        "date": date,
        "collections": collections,
        "cards": cards,
    }
    if merge:
        out["preview"] = merge
    CARDS.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    return {
        "added": sorted(cards.keys() - before.keys()),
        "changed": sorted(
            e for e in cards.keys() & before.keys() if cards[e]["sha"] != before[e]["sha"]
        ),
        "removed": sorted(before.keys() - cards.keys()),
    }


if __name__ == "__main__":
    for kind, ids in update().items():
        print(f"{kind}: {', '.join(ids) or '-'}")
