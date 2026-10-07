/* OpenH-RF site: renders data/datasets.json, written by build.py. Routes: # (overview),
   #explorer?<filters>, #stats/<section> and #dataset/<name>, which opens a drawer over the view
   behind it.
   Each dataset's "measured" object is what the scan read from its HDF5 files; the other
   fields come from its data card and catalog.yaml. */
(() => {
  "use strict";

  // Explorer filters: dataset field, URL parameter, label. Each value can be included or
  // excluded. File groups match by the ranges a dataset's files span; bucket i covers
  // [min_i, min_i+1).
  const CARD_GROUPS = [
    { key: "setting", param: "setting", label: "Setting", open: true },
    { key: "acquisition", param: "acquisition", label: "Acquisition", open: true },
    { key: "targets", param: "targets", label: "Target" },
    { key: "probe_types", param: "probe", label: "Probe type" },
    { key: "probe_models", param: "probe_model", label: "Probe" },
    { key: "data_type", param: "data_type", label: "Data type" },
    { key: "dimensionality", param: "dim", label: "Dimensionality" },
    { key: "tasks", param: "tasks", label: "Tasks" },
    { key: "institutions", param: "institution", label: "Institution" },
    // A dataset must have every selected key.
    { key: "key_products", param: "keys", label: "Contains keys", all: true },
  ];
  const FILE_GROUPS = [
    { key: "fc_mhz", param: "fc", label: "Center frequency", buckets: [["lt2", "<2 MHz", 0], ["2-5", "2-5 MHz", 2], ["5-10", "5-10 MHz", 5], ["10-20", "10-20 MHz", 10], ["gt20", "≥20 MHz", 20]] },
    { key: "n_el", param: "elements", label: "Elements", buckets: [["le64", "≤64", 0], ["65-128", "65-128", 65], ["129-256", "129-256", 129], ["gt256", ">256", 257]] },
    { key: "frames", param: "frames", label: "Frames per track", buckets: [["1", "1", 0], ["2-10", "2-10", 2], ["11-100", "11-100", 11], ["101-1000", "101-1000", 101], ["gt1000", ">1000", 1001]] },
    { key: "file_bytes", param: "file_size", label: "File size", buckets: [["lt10mb", "<10 MB", 0], ["10mb-100mb", "10-100 MB", 1e7], ["100mb-1gb", "100 MB-1 GB", 1e8], ["1gb-10gb", "1-10 GB", 1e9], ["gt10gb", "≥10 GB", 1e10]] },
    { key: "dtype", param: "dtype", label: "dtype" },
    { key: "coverage", param: "field", label: "Metadata fields" },
  ].map((g) => ({ ...g, files: true }));
  const GROUPS = [...CARD_GROUPS, ...FILE_GROUPS];
  const GROUP = Object.fromEntries(GROUPS.map((g) => [g.key, g]));

  // The scan's classes, and the card filter each maps to.
  const FIELD_FACET = { medium: "setting", medium_bytes: "setting", species: "setting", scheme: "acquisition", probe_class: "probe_types", signal: "data_type", signal_bytes: "data_type" };

  const state = {
    index: null,
    datasets: [],
    vocab: {},
    zea: {},
    // Per scanned field, the classes with a card filter, in colour order.
    palette: {},
    measure: "count",
    expanded: {},
    filters: {},
    q: "",
    terms: [],
    sort: "bytes:desc",
    view: "table",
    page: null,
    // The explorer's query, and the one its list shows.
    query: "",
    rendered: null,
    rows: [],
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs || {})) {
      if (value == null || value === false) continue;
      if (name === "class") node.className = value;
      else if (name === "text") node.textContent = value;
      else if (name.startsWith("on")) node.addEventListener(name.slice(2), value);
      else node.setAttribute(name, value);
    }
    node.append(...children.flat().filter((c) => c != null && c !== false));
    return node;
  }

  // Ids and keys may wrap after these characters and nowhere else.
  const breakable = (text, after = "/_-") => text.split(new RegExp(`(?<=[${after}])`)).flatMap((part, i) => (i ? [el("wbr"), part] : [part]));

  // Formatting

  const NBSP = " ";
  const DOT = `${NBSP}· `;
  const fmtInt = (n) => n.toLocaleString("en-US");
  const fmt3 = (x) => x.toLocaleString("en-US", { maximumSignificantDigits: 3 });

  // Exact below 100 k, else 241 k, 25.1 M, 23 T.
  function fmtNum(n) {
    if (n < 1e5) return fmtInt(n);
    let i = 0;
    for (n /= 1000; n >= 1000 && i < 3; i++) n /= 1000;
    return `${+n.toFixed(n < 100 ? 1 : 0)}${NBSP}${"kMBT"[i]}`;
  }

  function fmtBytes(n, decimals = 1) {
    let i = 0;
    for (; n >= 1000 && i < 5; i++) n /= 1000;
    return `${+n.toFixed(n < 100 && i ? decimals : 0)}${NBSP}${["B", "KB", "MB", "GB", "TB", "PB"][i]}`;
  }

  const plural = (n, word) => `${fmtNum(n)}${NBSP}${word}${n === 1 ? "" : "s"}`;
  const sum = (items, f) => items.reduce((s, x) => s + f(x), 0);
  // A word joiner after the dash keeps a range on one line.
  // "1.2-⁠21 GB": a unit both ends share is written once.
  const span = (r, f) => {
    const lo = f(r.min);
    const hi = f(r.max);
    const [n, unit] = lo.split(NBSP);
    return lo === hi ? lo : `${unit && hi.endsWith(NBSP + unit) ? n : lo}-⁠${hi}`;
  };
  const median = (r, f) => (f(r.min) === f(r.max) ? f(r.min) : `${f(r.median)} median (${span(r, f)})`);
  const capital = (s) => s[0].toUpperCase() + s.slice(1).replace(/_/g, " ");

  // "Linear (80 files), Phased (20)"
  const countList = (counts, unit, label = (k) => k) =>
    Object.entries(counts)
      .filter(([, n]) => n)
      .sort((a, b) => b[1] - a[1])
      .map(([k, n], i) => `${label(k)}${NBSP}(${i ? fmtInt(n) : plural(n, unit)})`)
      .join(", ");

  const labelOf = (key, value) => GROUP[key].labels.get(value) ?? value;
  const labels = (d, key) => [d[key]].flat().map((v) => labelOf(key, v)).join(", ");
  const classLabel = (field, id) => state.vocab[FIELD_FACET[field]][id]?.label || capital(id);
  const fieldName = (f) => ({ us_machine: "ultrasound machine", probe_fc: "probe center frequency", ecg: "ECG" })[f] || f.replace(/_/g, " ");

  // The card filter for a class the scan found. The scan's "other" and "unspecified" are
  // catch-alls, unlike the vocabulary's values of the same name. A species is an in-vivo setting.
  function classLink(field, id) {
    const facet = FIELD_FACET[field];
    const ids = { in_vivo: ["in_vivo_human", "in_vivo_animal"], human: ["in_vivo_human"], animal: ["in_vivo_animal"] }[id] || [id];
    if (id === "other" || id === "unspecified" || !ids.every((v) => v in state.vocab[facet])) return null;
    return { facet, ids };
  }

  // Classes keep their colour in every chart; those without a card filter are grey.
  function classColor(field, id) {
    const i = state.palette[field].indexOf(id);
    return i < 0 ? "var(--mixed)" : `var(--series-${(i % 6) + 1})`;
  }

  const pretty = (params) => params.toString().replace(/%2F/g, "/").replace(/%21/g, "!").replace(/%3A/g, ":");
  const explorerHref = (key, ids) => `#explorer?${pretty(new URLSearchParams(ids.map((v) => [GROUP[key].param, v])))}`;
  // In the explorer a link keeps the selection, with one group set to these values.
  const filterHash = (key, ids) =>
    state.page === "explorer" ? `#explorer${explorerQuery({ ...state.filters, [key]: new Map(ids.map((v) => [v, "include"])) })}` : explorerHref(key, ids);

  // zea streams a file from the Hub: only the bytes read are fetched.
  const HF = "hf://nvidia/OpenH-RF";
  const multiTrack = (d) => d.measured.tracks !== d.measured.files;
  const copyCommand = (folder = "") => `$ zea data copy ${HF}${folder && "/"}${folder} ./OpenH-RF${folder && "/"}${folder} --key all`;
  // Copied code gets plain spaces in place of the formatters' non-breaking ones.
  const code = (lines) => lines.join("\n").replaceAll(NBSP, " ");
  // The app lists a folder's files itself, so no file name has to be known.
  const appSteps = (d) => {
    const folder = `${HF}/${d.id}`;
    const path = (text) => el("code", { text });
    return [
      codeBlock('$ pip install "zea[jax,app]"'),
      codeBlock("$ zea app"),
      el(
        "p",
        { class: "steps" },
        `Taking the ${d.id} dataset as an example, paste `,
        path(folder),
        " as the dataset and ",
        path(`${folder}/pipeline.yaml`),
        " as the config, pick a file to see its contents, and press Run to beamform it. You can also stream the data directly in Python:",
      ),
    ];
  };
  // Beamform the dataset's first file with its own pipeline, once the Hub has one.
  const processBlock = (d) =>
    d.measured.pipeline
      ? [
          el("p", { class: "note", text: "Or beamform the first frame of one file with the dataset's pipeline:" }),
          codeBlock(`$ zea process -d ${HF}/${d.measured.first_file} -c ${HF}/${d.id}/pipeline.yaml${multiTrack(d) ? " --track 0" : ""} --n-frames 1`),
        ]
      : [];
  // One command per block, so the copy button copies a command and nothing else.
  const copyBlock = (d) => codeBlock(copyCommand(d.id));
  const copyText = (d) => `the whole ${d.id} subset to disk (${fmtBytes(d.measured.bytes)} / ${fmtBytes(state.index.measured.corpus.bytes)}):`;
  const pythonBlock = (d) => codeBlock(zeaSnippet(d));
  // Indexes by folder, file and frame, so no file name needs to be known.
  const zeaSnippet = (d) =>
    code([
      "import zea",
      "",
      `with zea.Dataset("${HF}/${d.id}") as dataset:`,
      "    print(dataset.file_paths[:3])  # print the first 3 filenames",
      "",
      "    file = dataset[0]            # streamed (only the bytes you read are downloaded)",
      "    file.summary()               # print the contents of the file",
      `    raw = file.${multiTrack(d) ? "tracks[0]." : ""}data.raw_data[0]  # data for the first frame`,
    ]);
  // Where the files are on the Hub, each folder linked to its listing there.
  const folders = (d) => {
    const all = d.measured.folders;
    const shown = all.length > 6 ? all.slice(0, 5) : all;
    const rest = all.slice(shown.length);
    const size = (list) => `${plural(sum(list, (f) => f.files), "file")}, ${fmtBytes(sum(list, (f) => f.bytes))}`;
    return el(
      "ul",
      { class: "folders" },
      shown.map((f) => el("li", null, el("a", { href: `${d.hub_url}${f.path.slice(d.id.length)}`, target: "_blank", rel: "noopener", text: `${f.path}/` }), el("span", { class: "muted", text: size([f]) }))),
      rest.length > 0 && el("li", { class: "muted", text: `and ${plural(rest.length, "more folder")}: ${size(rest)}` }),
    );
  };

  // Download script

  // Each dataset's files as [path in its folder, kind, size], with the facets of each kind.
  // Fetched the first time a script is generated, and again next time if that failed.
  let fileIndex = null;
  const loadFiles = () =>
    (fileIndex ||= fetch("data/files.json", { cache: "no-cache" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .catch((err) => {
        fileIndex = null;
        throw err;
      }));

  // The files of the matching datasets that pass the filters. A kind only holds what differs
  // between a dataset's files; the rest of its values are the dataset's.
  function matchingFiles(index) {
    // values() buckets a range, so hand it one of a single size.
    const size = (bytes) => values({ measured: { range: { file_bytes: { min: bytes, max: bytes } } } }, GROUP.file_bytes);
    return state.datasets
      .filter((d) => matches(d))
      .map((d) => {
        const { profiles, files } = index.datasets[d.id];
        const kinds = profiles.map((p) => Object.fromEntries(GROUPS.map((g) => [g.key, values({ ...d, ...p }, g)])));
        const kept = files.filter(([, kind, bytes]) => matches({ _hay: d._hay, _values: { ...kinds[kind], file_bytes: size(bytes) } }));
        return { d, files, kept };
      })
      .filter((m) => m.kept.length);
  }

  // Hub paths of the kept files: a folder whose files are all kept is one path.
  function hubPaths(id, files, kept) {
    const ancestors = (path) => path.split("/").map((_, i, parts) => parts.slice(0, i).join("/"));
    const keep = new Set(kept.map(([path]) => path));
    const total = new Map();
    const hits = new Map();
    for (const [path] of files) {
      for (const dir of ancestors(path)) {
        total.set(dir, (total.get(dir) || 0) + 1);
        if (keep.has(path)) hits.set(dir, (hits.get(dir) || 0) + 1);
      }
    }
    const out = new Set();
    for (const path of keep) {
      const dir = ancestors(path).find((a) => hits.get(a) === total.get(a));
      out.add([HF, id, dir === undefined ? path : dir].filter(Boolean).join("/"));
    }
    return [...out];
  }

  // A folder named after the selection, such as openhrf_invivohuman_carotid.
  function folderName() {
    const slug = (text) => text.toLowerCase().replace(/[^a-z0-9-]+/g, "");
    const parts = GROUPS.flatMap((g) => [...state.filters[g.key]].map(([v, mode]) => (mode === "exclude" ? "no" : "") + slug(v)));
    const name = ["openhrf", ...parts, ...state.terms.map(slug)].filter(Boolean).join("_");
    return name.length <= 60 ? name : "openhrf_selection";
  }

  // A Python script that downloads, or streams, the files that match the selection.
  function downloadScript(index) {
    const picked = matchingFiles(index);
    const n = sum(picked, (m) => m.kept.length);
    const bytes = sum(picked, (m) => sum(m.kept, ([, , size]) => size));
    return code([
      `"""`,
      `${location.origin}${location.pathname}#explorer${explorerQuery()} : ${plural(n, "file")} from ${plural(picked.length, "subset")}, ${fmtBytes(bytes)}.`,
      "Install zea: zea.readthedocs.io/en/latest/installation.html",
      `"""`,
      "",
      "import zea",
      "",
      `dataset_version = "${index.revision}"`,
      "paths = [",
      ...picked.flatMap((m) => [
        `    # ${m.d.id}: ${fmtInt(m.kept.length)} of ${plural(m.files.length, "file")}`,
        ...hubPaths(m.d.id, m.files, m.kept).map((path) => `    ${JSON.stringify(path)},`),
      ]),
      "]",
      "",
      "# Use zea.Dataset(..., lazy=False) to download all files in the selected datasets to cache upfront.",
      "# By default, only accessed parts of the data are downloaded and cached. (~/.cache/zea, or $ZEA_CACHE_DIR)",
      "with zea.Dataset(paths, revision=dataset_version) as dataset:",
      "    print(dataset.file_paths[:3])  # print the first 3 filenames",
      "",
      "    file = dataset[0]            # streamed (only the bytes you read are downloaded)",
      "    file.summary()               # print the contents of the file",
    ]);
  }

  function showScript(open) {
    $("#x-script-panel").hidden = !open;
    $("#x-script").setAttribute("aria-expanded", open);
    if (open) {
      renderScript();
      scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  async function renderScript() {
    const code = $("#x-script-code");
    const save = $("#x-script-save");
    save.removeAttribute("href");
    save.setAttribute("aria-disabled", "true");
    let text;
    try {
      text = downloadScript(await loadFiles());
    } catch (err) {
      code.replaceChildren(`Could not load the list of files (${err.message}). Close and reopen the script to try again.`);
      return;
    }
    code.replaceChildren(...highlight(text));
    save.href = `data:text/x-python;charset=utf-8,${encodeURIComponent(text)}`;
    save.download = `${folderName()}.py`;
    save.removeAttribute("aria-disabled");
  }

  // Tooltips and the toast go inside an open modal dialog, which would cover them otherwise.
  function lift(node) {
    const host = $("dialog[open]") || document.body;
    if (node.parentNode !== host) host.append(node);
  }

  let toastTimer = 0;
  async function copy(text, message) {
    // Without the prompt markers, so the lines paste into a shell.
    await navigator.clipboard.writeText(text.replace(/^\$ /gm, ""));
    const toast = $("#toast");
    lift(toast);
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast.hidden = true), 2500);
  }

  const tooltip = $("#tooltip");
  const hideTip = () => (tooltip.hidden = true);

  // Any element with a data-tip attribute shows it next to the pointer. A line "name\tvalue"
  // has its value right-aligned.
  function showTip(e) {
    const target = e.target.closest?.("[data-tip]");
    if (!target) return hideTip();
    lift(tooltip);
    tooltip.replaceChildren(
      ...target.dataset.tip.split("\n").map((line) => {
        const [name, value] = line.split("\t");
        return value === undefined ? el("div", { text: line }) : el("div", { class: "tip-row" }, el("span", { text: name }), el("span", { text: value }));
      }),
    );
    tooltip.hidden = false;
    const { width, height } = tooltip.getBoundingClientRect();
    tooltip.style.left = `${Math.max(8, Math.min(e.clientX + 14, innerWidth - width - 8))}px`;
    tooltip.style.top = `${e.clientY + 16 + height < innerHeight ? e.clientY + 16 : Math.max(8, e.clientY - height - 8)}px`;
  }

  // Aggregation

  // A filter group's values for a dataset: the card's, or those its files hold.
  function values(d, g) {
    if (!g.files) return [d[g.key]].flat();
    const m = d.measured;
    if (!g.buckets) return Object.keys(m[g.key]).filter((k) => m[g.key][k]);
    const r = m.range[g.key];
    if (!r) return [];
    return g.buckets.filter(([, , min], i) => r.max >= min && !(r.min >= g.buckets[i + 1]?.[2])).map(([id]) => id);
  }

  // A dataset counts fully under each value it has.
  function tally(datasets, g) {
    const out = new Map();
    for (const d of datasets) {
      for (const value of d._values[g.key]) {
        const a = out.get(value) || { value, count: 0, acquisitions: 0, bytes: 0 };
        a.count += 1;
        a.acquisitions += d.measured.acquisitions;
        a.bytes += d.measured.bytes;
        out.set(value, a);
      }
    }
    return out;
  }

  function options(g) {
    if (g.buckets) return g.buckets.map(([value, label]) => ({ value, label }));
    const counts = tally(state.datasets, g);
    const vocab = state.vocab[g.key];
    if (vocab) {
      return Object.keys(vocab)
        .filter((v) => counts.has(v))
        .map((v) => ({ value: v, label: vocab[v].label, group: vocab[v].group, title: vocab[v].description }));
    }
    return [...counts.values()]
      .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
      .map(({ value }) => ({ value, label: g.key === "coverage" ? fieldName(value) : value === "custom" ? "custom/*" : value, title: state.zea[value]?.description }));
  }

  // [class, total] in the records' files, largest first.
  function sumCounts(records, field) {
    const sums = {};
    for (const d of records) for (const [k, n] of Object.entries(d.measured[field])) sums[k] = (sums[k] || 0) + n;
    return Object.entries(sums).sort((a, b) => b[1] - a[1]);
  }

  // Charts shared by the overview, the explorer and the drawer

  const STRIPS = [
    ["medium_bytes", "Medium", "by size", fmtBytes],
    ["scheme", "Transmit scheme", "by tracks", fmtInt],
    ["probe_class", "Probe type", "by files", fmtInt],
  ];
  const whole = (v) => fmtNum(Math.round(v));
  // rules: values that statHist marks on the statistics page's chart.
  const HISTS = [
    { key: "fc_mhz", title: "Center frequency (MHz)", format: fmt3 },
    { key: "fs_over_fc", title: "Sampling over center frequency", format: fmt3, rules: [[2, "2fc"], [4, "4fc"]] },
    { key: "depth_cm", title: "Imaging depth (cm)", format: fmt3 },
    { key: "frames", title: "Frames per track", format: whole, integer: true },
    { key: "n_tx", title: "Transmits per frame", format: whole, integer: true },
    { key: "n_ax", title: "Samples per line", format: whole, integer: true },
    { key: "n_el", title: "Receive elements", format: whole, integer: true },
    { key: "file_bytes", title: "File size", format: fmtBytes },
    { key: "compression", title: "Compression ratio", format: fmt3 },
  ];
  const HIST = Object.fromEntries(HISTS.map((h) => [h.key, h]));
  const SHAPE_HISTS = ["fc_mhz", "n_el", "frames", "file_bytes"].map((key) => HIST[key]);

  // A segment or bar per class, linking to its card filter, which may select more datasets
  // than hold the files.
  function segments(records, field, format) {
    const all = state.index.measured.corpus[field];
    return sumCounts(records, field).map(([id, value]) => {
      const link = classLink(field, id);
      return {
        id,
        label: classLabel(field, id),
        value,
        color: classColor(field, id),
        href: link && filterHash(link.facet, link.ids),
        note: `all datasets: ${format(all[id])}`,
      };
    });
  }

  // The datasets behind each segment, largest first, in its tooltip.
  function contributors(records, field, parts, format) {
    return parts.map((p) => {
      const rows = records.filter((d) => d.measured[field][p.id]).sort((a, b) => b.measured[field][p.id] - a.measured[field][p.id]);
      return { ...p, tip: ["Contributing datasets:", ...rows.map((d) => `${d.id}\t${format(d.measured[field][p.id])}`)].join("\n") };
    });
  }

  function stripBlock(title, per, parts, format) {
    const total = format(sum(parts, (p) => p.value));
    return el("div", null, el("h3", null, `${title} `, el("span", { class: "muted", text: `${per}, ${total}` })), svg.strip(parts, { format }));
  }
  const shapeStrips = (records) =>
    el("div", { class: "strips" }, STRIPS.map(([field, title, per, format]) => stripBlock(title, per, contributors(records, field, segments(records, field, format), format), format)));

  // Bins of whole numbers are named by the values they hold (4-5, not 3.16-5.62), and open
  // bins by their one edge. np.histogram closes only the last bin at its top. The axis marks
  // each bin by the median of all datasets' values in it.
  function histChart(h, records, marks) {
    const { bins, bin_medians, corpus, quantities } = state.index.measured;
    const edges = bins[h.key];
    const open = quantities[h.key].open || [];
    const last = edges.length - 2;
    const names = edges.slice(1).map((hi, i) => {
      const lo = edges[i];
      if (i === 0 && open.includes("below")) return `<${h.format(hi)}`;
      if (i === last && open.includes("above")) return `${h.format(lo)}+`;
      if (!h.integer) return `${h.format(lo)}-${h.format(hi)}`;
      const [a, b] = [Math.ceil(lo), i === last ? Math.floor(hi) : Math.ceil(hi) - 1];
      return a === b ? fmtInt(a) : `${fmtInt(a)}-${fmtInt(b)}`;
    });
    const labels = bin_medians[h.key].map((m) => (m === null ? "" : h.format(m)));
    const counts = corpus.hist[h.key].map((_, i) => sum(records, (d) => d.measured.hist[h.key][i]));
    return svg.hist(counts, { corpus: corpus.hist[h.key], labels, names, marks });
  }

  const shapeHists = (records) =>
    el(
      "div",
      { class: "hists" },
      SHAPE_HISTS.map((h) => {
        const ranges = records.map((d) => d.measured.range[h.key]).filter(Boolean);
        const range = ranges.length && { min: Math.min(...ranges.map((r) => r.min)), max: Math.max(...ranges.map((r) => r.max)) };
        return el("div", { class: "hist" }, el("h3", { text: h.title }), el("p", { class: "muted", text: range ? span(range, h.format) : "not recorded" }), histChart(h, records));
      }),
    );

  function image(d) {
    if (d.thumb) return el("img", { src: d.thumb, alt: "", loading: "lazy", width: 320, height: 320 });
    return el("span", { class: "placeholder", text: "No preview" });
  }

  const galleryCard = (d) =>
    el(
      "a",
      { class: "g-card", href: `#dataset/${d.name}` },
      el("span", { class: "g-img" }, image(d)),
      el("span", { class: "g-body" }, el("span", { class: "g-title", text: d.title }), el("span", { class: "g-long", text: d.pretty_name }), el("span", { class: "muted", text: [d.institution, fmtBytes(d.measured.bytes)].filter(Boolean).join(DOT) })),
    );

  // Overview

  const kpi = (value, label, sub) => el("div", { class: "kpi" }, el("b", { text: value }), el("span", { text: label }), el("small", null, sub));
  // "tracks", linked to where zea explains files with several tracks.
  const tracks = (n) => [`${fmtInt(n)}${NBSP}`, el("a", { class: "quiet-link", href: "https://zea.readthedocs.io/en/latest/data-acquisition.html#multi-track-files", target: "_blank", rel: "noopener", text: n === 1 ? "track" : "tracks" })];

  // The authors' affiliations and the other institutions the datasets are from.
  const datasetsKpi = (ds) => kpi(fmtInt(ds.length), "Datasets", plural(state.index.institution_count, "institution"));

  function renderOverview() {
    const { measured, generated_at } = state.index;
    const { corpus, source } = measured;
    const ds = state.datasets;
    $("#kpis").replaceChildren(
      kpi(fmtBytes(corpus.bytes), "Size", `uncompressed raw: ${fmtBytes(corpus.raw_bytes)}`),
      kpi(fmtInt(corpus.files), "Acquisitions", ["with ", ...tracks(corpus.tracks)]),
      kpi(fmtNum(corpus.frames), "Frames", `${fmtInt(Math.floor(corpus.frames / 30 / 3600 / 10) * 10)}+${NBSP}hours at 30${NBSP}fps`),
      kpi(fmtNum(corpus.transmits), "Transmits", `from ${plural(Object.keys(corpus.probes).length, "probe type")}`),
      datasetsKpi(ds),
    );
    $("#corpus-shape").replaceChildren(shapeStrips(ds));
    renderBrowse();
    oneColumn.addEventListener("change", () => renderBars("key_products"));
    $("#gallery").replaceChildren(...[...ds].sort((a, b) => !!b.thumb - !!a.thumb || a.title.localeCompare(b.title)).map(galleryCard));
    $("#institutions").replaceChildren(
      ...[...tally(ds, GROUP.institutions).values()]
        .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
        .map((a) => el("li", null, el("a", { href: explorerHref("institutions", [a.value]), text: a.value }), el("span", { class: "muted", title: plural(a.count, "dataset"), text: a.count }))),
    );
    const example = ds.find((d) => d.id === "tue-carotid") || ds[0];
    $("#get-data").replaceChildren(...appSteps(example), pythonBlock(example), el("p", { class: "steps", text: `Alternatively, copy ${copyText(example)}` }), copyBlock(example));
    // A preview (site/update.py --pr) shows the data cards of open pull requests too.
    const pulls = (source.pull_requests || []).map((p) => `#${p.number}`);
    const previewed = pulls.length ? `; data cards include the open pull request${pulls.length > 1 ? "s" : ""} ${pulls.length > 1 ? `${pulls.slice(0, -1).join(", ")} and ${pulls.at(-1)}` : pulls[0]}` : "";
    $("#generated-at").textContent = `Index generated ${generated_at.slice(0, 10)}; statistics read from the files at Hub revision ${source.revision.slice(0, 7)} (${source.date})${previewed}.`;
  }

  // Where site.css sets the keys chart in one column instead of two.
  const oneColumn = matchMedia("(max-width: 860px)");

  function renderBars(key) {
    const measure = state.measure;
    const format = { count: fmtInt, acquisitions: fmtNum, bytes: fmtBytes }[measure];
    const items = [...tally(state.datasets, GROUP[key]).values()]
      .filter((a) => a.value !== "data/raw_data")
      .sort((a, b) => b[measure] - a[measure] || b.count - a.count);
    const limit = key === "key_products" && !oneColumn.matches ? 16 : 8;
    const expanded = state.expanded[key];
    const shown = expanded || items.length <= limit + 2 ? items : items.slice(0, limit);
    const rows = shown.map((a) => {
      const label = labelOf(key, a.value);
      const description = (key === "key_products" ? state.zea : state.vocab[key])[a.value]?.description;
      const tip = [label, [plural(a.count, "dataset"), plural(a.acquisitions, "acquisition"), fmtBytes(a.bytes)].join(DOT), description].filter(Boolean).join("\n");
      return el(
        "a",
        { class: "bar-row", href: explorerHref(key, [a.value]), "data-tip": tip },
        el("span", { class: "bar-label" }, key === "key_products" ? el("code", { text: label }) : label),
        el("span", { class: "bar-track" }, el("span", { class: "bar-fill", style: `width:${(a[measure] / items[0][measure]) * 100}%` })),
        el("span", { class: "bar-value", text: format(a[measure]) }),
      );
    });
    const toggle = () => {
      state.expanded[key] = !expanded;
      renderBars(key);
    };
    const more = (expanded || shown.length < items.length) && el("button", { type: "button", class: "more", text: expanded ? "Show fewer" : `Show all ${items.length}`, onclick: toggle });
    $(`#bars-${key}`).replaceChildren(...rows, more || "");
  }

  function renderBrowse() {
    for (const key of ["acquisition", "targets", "key_products"]) renderBars(key);
  }

  // Explorer

  function buildGroup(g) {
    const body = el("div", { class: "group-body" });
    let heading;
    for (const opt of g.options) {
      if (opt.group && opt.group !== heading) body.append(el("p", { class: "group-sub", text: (heading = opt.group) }));
      const box = (mode, verb) =>
        el("button", { type: "button", class: `box ${mode}`, "aria-label": `${verb} ${opt.label}`, onclick: () => setMode(g, opt.value, mode) }, el("span", { class: mode === "include" ? "check" : "cross" }));
      opt.count = el("span", { class: "opt-count" });
      // A click on the row steps through include, exclude and neither.
      opt.row = el(
        "div",
        { class: "opt", title: opt.title, onclick: (e) => e.target.closest(".box") || cycle(g, opt.value) },
        el("span", { class: "boxes" }, box("include", "Include"), box("exclude", "Exclude")),
        el("span", { class: "opt-label" }, g.key === "key_products" ? el("code", null, breakable(opt.label)) : opt.label),
        opt.count,
      );
      body.append(opt.row);
    }
    g.selected = el("span", { class: "group-selected" });
    g.details = el("details", { class: "facet-group", open: g.open }, el("summary", null, g.label, g.selected), body);
    return g.details;
  }

  function matches(d, skip) {
    if (!state.terms.every((t) => d._hay.includes(t))) return false;
    return GROUPS.every((g) => {
      const sel = [...state.filters[g.key]];
      if (g === skip || !sel.length) return true;
      const has = (v) => d._values[g.key].includes(v);
      const include = sel.filter(([, mode]) => mode === "include").map(([v]) => v);
      if (sel.some(([v, mode]) => mode === "exclude" && has(v))) return false;
      return !include.length || (g.all ? include.every(has) : include.some(has));
    });
  }

  function cycle(g, value) {
    const mode = state.filters[g.key].get(value);
    setMode(g, value, !mode ? "include" : mode === "include" ? "exclude" : mode);
  }

  function setMode(g, value, mode) {
    const sel = state.filters[g.key];
    if (sel.get(value) === mode) sel.delete(value);
    else sel.set(value, mode);
    update();
  }

  // Each count is of the datasets the other groups let through; a group where every
  // selected value must match also applies its own selection.
  function updateFacets() {
    let selected = 0;
    for (const g of GROUPS) {
      const sel = state.filters[g.key];
      const counts = tally(
        state.datasets.filter((d) => matches(d, g.all ? null : g)),
        g,
      );
      for (const opt of g.options) {
        const mode = sel.get(opt.value);
        const n = counts.get(opt.value)?.count || 0;
        opt.row.classList.toggle("zero", !n && !mode);
        opt.row.classList.toggle("excluded", mode === "exclude");
        for (const box of $$(".box", opt.row)) box.setAttribute("aria-pressed", box.classList.contains(mode));
        opt.count.textContent = fmtInt(n);
      }
      g.selected.textContent = sel.size ? `${sel.size} selected` : "";
      selected += sel.size;
    }
    $("#x-filters-open").textContent = `Filters (${selected})`;
  }

  function explorerQuery(filters = state.filters) {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    for (const g of GROUPS) for (const [v, mode] of filters[g.key]) params.append(g.param, (mode === "exclude" ? "!" : "") + v);
    if (state.sort !== "bytes:desc") params.set("sort", state.sort);
    if (state.view !== "table") params.set("view", state.view);
    const query = pretty(params);
    return query && `?${query}`;
  }

  function applyQuery(query) {
    const params = new URLSearchParams(query);
    for (const g of GROUPS) {
      const known = g.labels;
      const pairs = params.getAll(g.param).map((raw) => (raw[0] === "!" ? [raw.slice(1), "exclude"] : [raw, "include"]));
      state.filters[g.key] = new Map(pairs.filter(([v]) => known.has(v)));
      if (state.filters[g.key].size) g.details.open = true;
    }
    setSearch(params.get("q") || "");
    $("#x-search").value = state.q;
    const sort = params.get("sort");
    state.sort = /^(bytes|frames|title):(asc|desc)$/.test(sort) ? sort : "bytes:desc";
    state.view = ["gallery", "charts"].includes(params.get("view")) ? params.get("view") : "table";
  }

  function setSearch(q) {
    state.q = q.trim();
    state.terms = state.q.toLowerCase().split(/\s+/).filter(Boolean);
  }

  // The address follows the selection, without a history entry per click.
  function update() {
    state.query = explorerQuery();
    history.replaceState(history.state, "", `#explorer${state.query}`);
    render();
  }

  function resetFilters() {
    for (const g of GROUPS) state.filters[g.key].clear();
    setSearch("");
    $("#x-search").value = "";
    update();
  }

  function render() {
    const [key, dir] = state.sort.split(":");
    const rows = state.datasets
      .filter((d) => matches(d))
      .sort((a, b) => {
        const c = key === "title" ? a.title.localeCompare(b.title) : a.measured[key] - b.measured[key];
        return (dir === "asc" ? c : -c) || a.title.localeCompare(b.title);
      });
    state.rows = rows;
    state.rendered = state.query;
    hideTip();
    updateFacets();

    const n = rows.length;
    const all = state.datasets.length;
    $("#x-summary").replaceChildren(
      el("strong", { text: !n ? "No datasets match" : n === all ? plural(n, "dataset") : `${n} of ${plural(all, "dataset")}` }),
      n ? `${DOT}${plural(sum(rows, (d) => d.measured.files), "file")}${DOT}${fmtBytes(sum(rows, (d) => d.measured.bytes))}${DOT}${plural(sum(rows, (d) => d.measured.frames), "frame")}` : "",
    );
    // The script is for a selection: with nothing selected it would fetch every file.
    const chosen = state.terms.length > 0 || GROUPS.some((g) => state.filters[g.key].size > 0);
    const button = $("#x-script");
    button.disabled = !n;
    button.classList.toggle("btn-primary", chosen);
    button.classList.toggle("btn-ghost", !chosen);
    button.setAttribute("aria-disabled", !chosen);
    if (chosen) delete button.dataset.tip;
    else button.dataset.tip = "Select a filter before downloading";
    if (!n || !chosen) showScript(false);
    else if (!$("#x-script-panel").hidden) renderScript();
    $("#x-sheet-done").textContent = `Show ${plural(n, "dataset")}`;
    renderActive();
    $("#x-shape-body").replaceChildren(n ? shapeStrips(rows) : el("p", { class: "muted", text: "No datasets are selected." }));
    $("#x-shape-hists").replaceChildren(n ? shapeHists(rows) : "");
    $("#x-shape-key").hidden = !n;

    for (const view of ["table", "gallery", "charts"]) $(`#x-view-${view}`).hidden = view !== state.view;
    for (const b of $$("[data-view]")) b.setAttribute("aria-pressed", b.dataset.view === state.view);
    $("#x-sort-controls").hidden = state.view === "charts";
    $("#x-sort").value = key;
    $("#x-sort-dir").textContent = dir === "asc" ? "↑ Ascending" : "↓ Descending";
    const none = () => el("p", { class: "empty" }, "No datasets match these filters. ", el("button", { type: "button", class: "linklike", text: "Reset filters", onclick: resetFilters }));
    if (state.view === "table") $("#x-tbody").replaceChildren(...(n ? rows.map(tableRow) : [el("tr", null, el("td", { colspan: 4 }, none()))]));
    else if (state.view === "gallery") $("#x-view-gallery").replaceChildren(...(n ? rows.map(galleryCard) : [none()]));
    else $("#x-view-charts").replaceChildren(...(n ? charts(rows) : [none()]));
  }

  function renderActive() {
    const chip = (text, excluded, remove) =>
      el(
        "button",
        {
          type: "button",
          class: `chip removable${excluded ? " excluded" : ""}`,
          "aria-label": `Remove filter ${text}`,
          onclick: () => {
            remove();
            update();
            $("#x-active").focus();
          },
        },
        text,
        el("span", { "aria-hidden": "true", text: "×" }),
      );
    const chips = state.q ? [chip(`Search: ${state.q}`, false, () => setSearch(($("#x-search").value = "")))] : [];
    for (const g of GROUPS) {
      for (const [v, mode] of state.filters[g.key]) {
        chips.push(chip(`${g.label}: ${mode === "exclude" ? "not " : ""}${labelOf(g.key, v)}`, mode === "exclude", () => state.filters[g.key].delete(v)));
      }
    }
    $("#x-active").replaceChildren(chips.length ? el("div", { class: "chips" }, chips) : el("span", { class: "muted", text: "No filters: every dataset in OpenH-RF." }));
  }

  const chips = (d, key, link) => [d[key]].flat().map((v) => el(link ? "a" : "span", { class: `chip ${key}`, href: link && filterHash(key, [v]) }, labelOf(key, v)));

  function keyChips(d) {
    const rank = (k) => ["data/", "metadata/annotations/", "metrics/", "metadata/", "custom"].findIndex((p) => k.startsWith(p));
    const keys = d.key_products.filter((k) => k !== "data/raw_data").sort((a, b) => rank(a) - rank(b));
    if (!keys.length) return el("span", { class: "muted", text: "raw data only" });
    const shown = keys.length > 6 ? keys.slice(0, 5) : keys;
    return el(
      "div",
      { class: "chips" },
      shown.map((k) => el("span", { class: "chip key", title: state.zea[k]?.description }, breakable(labelOf("key_products", k)))),
      shown.length < keys.length && el("a", { class: "chip more", href: `#dataset/${d.name}`, text: `+${keys.length - shown.length} more` }),
    );
  }

  function tableRow(d) {
    const m = d.measured;
    return el(
      "tr",
      { "data-id": d.id, "data-name": d.name },
      el(
        "td",
        null,
        el(
          "div",
          { class: "ds-cell" },
          el("span", { class: "thumb" }, image(d)),
          el("div", null, el("a", { class: "ds-name", href: `#dataset/${d.name}`, text: d.title }), el("div", { class: "muted", text: d.institution }), el("div", { class: "ds-path" }, breakable(d.id))),
        ),
      ),
      el("td", null, el("div", { class: "chips" }, chips(d, "setting"), chips(d, "targets"), chips(d, "acquisition"))),
      el("td", { class: "scale" }, el("b", { text: fmtBytes(m.bytes) }), el("span", { text: plural(m.files, "file") }), el("span", { text: plural(m.frames, "frame") })),
      el("td", null, keyChips(d)),
    );
  }

  const showAll = (text, onclick) => el("button", { type: "button", class: "btn btn-ghost btn-small show-all", text, onclick });

  function chartCard(title, note, ...body) {
    return el("section", { class: "chart-card" }, el("h3", { text: title }), note && el("p", { class: "muted", text: note }), ...body);
  }

  // The 10 largest by value(d), fading out, or every dataset on request; a log axis if they
  // span two decades. parts(d) splits a bar into coloured segments, detail(d) goes in its tooltip.
  function largest(rows, title, value, format, { note, parts, detail, legend, names } = {}) {
    const sorted = [...rows].sort((a, b) => value(b) - value(a));
    const values = sorted.map(value);
    const scale = values[0] >= 100 * values.at(-1) ? "log" : "linear";
    const body = el("div");
    const render = (all) => {
      const folded = !all && sorted.length > 10;
      const bars = (folded ? sorted.slice(0, 10) : sorted).map((d, i) => ({
        label: d.title,
        value: values[i],
        note: detail && detail(d),
        href: `#dataset/${d.name}`,
        parts: parts && parts(d),
      }));
      body.replaceChildren(svg.bars(bars, { format, scale, fade: folded, legend, names, nameRows: 10 }));
      if (sorted.length > 10) body.append(showAll(all ? "Show fewer" : `Show all ${sorted.length}`, () => render(!all)));
    };
    render(false);
    return chartCard(title, note, body);
  }

  function charts(rows) {
    const byClass = (title, text, field, format) => chartCard(title, text, svg.bars(segments(rows, field, format), { format }));
    return [
      largest(rows, "Size per dataset", (d) => d.measured.bytes, fmtBytes),
      largest(rows, "Files per dataset", (d) => d.measured.files, fmtInt),
      byClass("Transmit scheme, by tracks", "As classified from the files. A bar selects the datasets whose card lists that scheme.", "scheme", fmtInt),
      byClass("Medium, by size", "Per file. A bar selects the datasets whose card lists that setting.", "medium_bytes", fmtBytes),
    ];
  }

  // Statistics page

  const percent = (s) => `${Math.round(100 * s)}%`;

  // A value's place along a histogram's axis, in bins: linear within the fixed bins (the
  // ones with an open end), else logarithmic.
  function binAt(key, value) {
    const { bins, quantities } = state.index.measured;
    const edges = bins[key];
    let i = edges.findIndex((e, j) => j < edges.length - 1 && value < edges[j + 1]);
    if (i < 0) i = edges.length - 2;
    const lo = edges[i];
    const hi = edges[i + 1];
    const f = quantities[key].open ? (value - lo) / (hi - lo) : Math.log(value / lo) / Math.log(hi / lo);
    return i + Math.max(0, Math.min(1, f));
  }

  function statHist(key) {
    const { corpus, quantities } = state.index.measured;
    const h = HIST[key];
    const range = corpus.range[key];
    const marks = (h.rules || []).map(([value, text]) => ({ at: binAt(key, value), text }));
    const n = sum(corpus.hist[key], (x) => x);
    const unit = quantities[key].per === "files" ? "file" : "track";
    return chartCard(h.title, `${plural(n, unit)}, ${span(range, h.format)}.`, histChart(h, state.datasets, marks));
  }

  function renderStats() {
    const { corpus } = state.index.measured;
    const ds = state.datasets;
    const geometries = Object.keys(corpus.probe_class).filter((c) => c !== "unspecified").length;
    const hz = (v) => (v ? `${fmt3(v)} Hz` : "unknown");
    const radius = (n) => 3 + 2 * Math.log10(n); // a decade more, 2px more
    const rates = corpus.prf_frame_rate.map(([prf, rate, n]) => ({
      x: prf,
      y: rate,
      r: radius(n),
      n,
      color: "var(--bar)",
      label: `PRF ${hz(prf)}, frame rate ${hz(rate)}`,
    }));
    const thousands = (n) => (n < 1000 ? String(n) : `${+(n / 1000).toFixed(1)}k`);
    const tracks = (test) => thousands(sum(rates.filter(test), (p) => p.n));
    $("#stats-kpis").replaceChildren(
      kpi(fmtBytes(corpus.bytes), "Size", `uncompressed raw: ${fmtBytes(corpus.raw_bytes)}`),
      kpi(fmtNum(corpus.frames), "Frames", `${fmt3(corpus.frames / 30 / 3600)}${NBSP}hours when viewed at 30${NBSP}fps`),
      kpi(fmtNum(corpus.samples), "Samples", `from ${plural(corpus.transmits, "transmit")}`),
      datasetsKpi(ds),
      kpi(fmtInt(Object.keys(corpus.probes).length), "Probe types", `in ${geometries}${NBSP}geometries`),
    );
    $("#stats-strips").replaceChildren(
      ...[
        ["Medium", "by files", "medium", fmtInt],
        ["Medium", "by size", "medium_bytes", fmtBytes],
        ["Species", "in-vivo files", "species", fmtInt],
        ["Signal", "by files", "signal", fmtInt],
        ["Signal", "by size", "signal_bytes", fmtBytes],
      ].map(([title, per, field, format]) => stripBlock(title, per, contributors(ds, field, segments(ds, field, format), format), format)),
      stripBlock("Sample type", "by tracks", contributors(ds, "dtype", Object.entries(corpus.dtype).map(([id, value], i) => ({ id, label: id, value, color: `var(--series-${i + 1})`, href: filterHash("dtype", [id]) })), fmtInt), fmtInt),
    );
    // The colours of a class, for a chart that uses them without naming them.
    const key = (field) => Object.keys(corpus[field]).map((id) => ({ label: classLabel(field, id), color: classColor(field, id) }));

    const mediumParts = (d) =>
      Object.keys(corpus.medium_bytes)
        .filter((id) => d.measured.medium_bytes[id])
        .map((id) => ({ value: d.measured.medium_bytes[id], color: classColor("medium_bytes", id) }));
    const fileBytes = (d) => d.measured.range.file_bytes;
    $("#datasets-charts").replaceChildren(
      largest(ds, "Size per dataset", (d) => d.measured.bytes, fmtBytes, { parts: mediumParts, legend: key("medium_bytes") }),
      largest(ds.filter((d) => d.measured.subjects_in_vivo), "In-vivo subjects per dataset", (d) => d.measured.subjects_in_vivo, fmtInt, { note: "Distinct subject ids in the files." }),
    );
    $("#files-charts").replaceChildren(
      largest(ds, "Median file size per dataset", (d) => fileBytes(d).median, fmtBytes, { detail: (d) => `range: ${span(fileBytes(d), (v) => fmtBytes(v, 0))}`, names: 1 / 3 }),
      largest(ds, "Files per dataset", (d) => d.measured.files, fmtInt),
    );

    $("#acquisition-charts").replaceChildren(
      chartCard("Transmit scheme", "By tracks, from the focus distances and apodizations. A bar selects the datasets whose card lists that scheme.", svg.bars(segments(ds, "scheme", fmtInt), { format: fmtInt })),
      chartCard("Probe geometry", "By files, from the stated probe type and the element positions.", svg.bars(segments(ds, "probe_class", fmtInt), { format: fmtInt })),
    );
    $("#frequency-charts").replaceChildren(...["fc_mhz", "fs_over_fc", "depth_cm"].map(statHist));
    // The n most used, or all of them on request.
    const top = (title, counts, what, n) => {
      const entries = Object.entries(counts);
      const files = plural(sum(entries, (e) => e[1]), "file");
      const body = el("div");
      const render = (all) => {
        const rows = (all ? entries : entries.slice(0, n)).map(([label, value]) => ({ label, value }));
        body.replaceChildren(
          el("p", { class: "muted", text: `${rows.length === entries.length ? `All ${entries.length}` : `The ${n} most used of ${entries.length}`}. ${files} report their ${what}.` }),
          svg.bars(rows, { format: fmtInt, nameRows: n }),
        );
        if (entries.length > n) body.append(showAll(all ? "Show fewer" : `Show all ${entries.length}`, () => render(!all)));
      };
      render(false);
      return chartCard(title, null, body);
    };
    // The n probes the most datasets use, their bars split into the datasets with real data
    // of it and those with only simulations. Either legend entry toggles the simulated ones;
    // a bar opens the datasets with that probe.
    const probesChart = (counts, n) => {
      const kinds = [
        { id: "real", label: "Real", color: "var(--series-1)", value: (p) => counts[p].real },
        { id: "simulated", label: "Simulated", color: "var(--series-2)", value: (p) => counts[p].simulated },
      ];
      let realOnly = false;
      let all = false;
      const body = el("div");
      const toggles = kinds.map((k) =>
        el("button", { type: "button", class: "key-toggle", onclick: () => ((realOnly = !realOnly), render()) }, el("span", { class: "key-swatch", style: `background:${k.color}` }), k.label),
      );
      const render = () => {
        const shown = kinds.filter((k) => !realOnly || k.id === "real");
        toggles.forEach((b, i) => b.setAttribute("aria-pressed", realOnly && kinds[i].id === "real"));
        const entries = Object.keys(counts)
          .map((p) => [p, shown.map((k) => ({ value: k.value(p), color: k.color }))])
          .map(([p, parts]) => [p, parts, sum(parts, (q) => q.value)])
          .filter(([, , value]) => value)
          .sort((a, b) => b[2] - a[2] || a[0].localeCompare(b[0]));
        const rows = (all ? entries : entries.slice(0, n)).map(([label, parts, value]) => ({
          label,
          value,
          parts,
          href: filterHash("probe_models", [label]),
          note: shown.length > 1 ? kinds.map((k) => `${fmtInt(k.value(label))} ${k.id}`).join(", ") : null,
        }));
        body.replaceChildren(
          el("p", { class: "muted", text: `${rows.length === entries.length ? `All ${entries.length}` : `The ${n} most used of ${entries.length}`}, by datasets. Click the legend to ${realOnly ? "show simulated probes too" : "show only real probes"}.` }),
          svg.bars(rows, { format: fmtInt, nameRows: n, allNames: entries.map(([label]) => label) }),
        );
        if (entries.length > n) body.append(showAll(all ? "Show fewer" : `Show all ${entries.length}`, () => ((all = !all), render())));
      };
      render();
      const card = chartCard("Most used probes", null, el("p", { class: "bar-key" }, toggles), body);
      card.classList.add("keyed");
      return card;
    };
    // The paper's probe classes, in the page's colours where the page has the class.
    const PROBE_CLASS = { curved: "curvilinear", IVUS: "ivus" };
    const probeColor = (c) => classColor("probe_class", PROBE_CLASS[c] || c);
    const titles = Object.fromEntries(ds.map((d) => [d.id, d.title]));
    // A dot opens the explorer on the frequency and element ranges that hold it.
    const range = (key, v) => [GROUP[key].param, GROUP[key].buckets.findLast(([, , min]) => v >= min)[0]];
    const settings = corpus.probe_settings.map((s) => ({
      x: s.fc_mhz,
      y: s.n_el,
      n: s.acquisitions,
      cls: s.class,
      color: probeColor(s.class),
      href: `#explorer?${pretty(new URLSearchParams([range("fc_mhz", s.fc_mhz), range("n_el", s.n_el)]))}`,
      tip: [
        `${capital(s.class)}, ${fmt3(s.fc_mhz)}${NBSP}MHz, ${fmtInt(s.n_el)}${NBSP}elements: ${fmtInt(s.acquisitions)}${NBSP}acquisition${s.acquisitions === 1 ? "" : "s"}`,
        ...Object.entries(s.datasets).map(([id, n]) => `${titles[id] || id}\t${fmtInt(n)}`),
      ].join("\n"),
    }));
    const probeClasses = Object.entries(corpus.probe_classes).map(([id, n]) => ({ id, label: capital(id), color: probeColor(id), n }));
    const plotted = sum(settings, (s) => s.n);
    $("#timing-charts").replaceChildren(
      chartCard(
        "Frame rate against pulse repetition frequency",
        `Plotted for ${tracks((p) => p.x && p.y)} / ${thousands(corpus.tracks)} tracks that report both, ${tracks((p) => p.x || p.y)} that report either.`,
        svg.dots(rates, {
          xTicks: [10, 100, 1000, 10000],
          yTicks: [1, 10, 100, 1000, 10000],
          xTick: fmtInt,
          yTick: fmtInt,
          xLabel: "Pulse repetition frequency (Hz)",
          yLabel: "Frame rate (Hz)",
          format: (p) => plural(p.n, "track"),
          diagonal: "one transmit per frame",
          fill: true, // as tall as the probes chart beside it
        }),
      ),
      chartCard(
        "Elements against center frequency",
        `A dot per probe setting, for the ${fmtInt(plotted)} / ${fmtInt(sum(probeClasses, (c) => c.n))} acquisitions that report both, with their histograms per decade. Hover over a probe type or a dot for its histograms; a dot opens the datasets in its frequency and element ranges.`,
        svg.probes(settings, probeClasses, {
          xLabel: "Probe center frequency (MHz)",
          yLabel: "Elements",
          sizeLabel: "Acquisitions per probe",
          format: String,
        }),
      ),
    );
    $("#hardware-charts").replaceChildren(
      probesChart(corpus.probe_datasets, 6),
      top("Scanners", corpus.scanners, "scanner; simulations are excluded", 7),
    );
    $("#shape-charts").replaceChildren(...["frames", "n_tx", "n_ax", "n_el"].map(statHist));

    // Sample types in their own colours. A dataset with several is mixed.
    const dtypes = [...Object.keys(corpus.dtype), "mixed"];
    const dtypeColor = (t) => (t === "mixed" ? "var(--mixed)" : `var(--series-${dtypes.indexOf(t) + 1})`);
    const perDataset = ds.map((d) => {
      const used = Object.keys(d.measured.dtype);
      const dtype = used.length > 1 ? "mixed" : used[0];
      return { x: d.measured.raw_bytes, y: d.measured.files, r: 5, dtype, color: dtypeColor(dtype), label: d.title, href: `#dataset/${d.name}` };
    });
    const legend = dtypes.filter((t) => perDataset.some((p) => p.dtype === t)).map((t) => ({ label: t === "mixed" ? "Mixed" : t, color: dtypeColor(t) }));
    $("#storage-charts").replaceChildren(
      chartCard(
        "Files against raw data size",
        "One dot per dataset, by the uncompressed size of its raw data. A dot opens its dataset.",
        svg.dots(perDataset, {
          xTicks: [1e9, 1e11, 1e13],
          yTicks: [1, 10, 100, 1000],
          xTick: fmtBytes,
          legend,
          format: (p) => `${p.dtype}, ${fmtBytes(p.x)}, ${plural(p.y, "file")}`,
        }),
      ),
      el("div", { class: "stack" }, statHist("file_bytes"), statHist("compression")),
    );

    const cols = Object.keys(corpus.coverage)
      .filter((c) => corpus.coverage[c])
      .sort((a, b) => corpus.coverage[b] - corpus.coverage[a]);
    const rows = [...ds]
      .sort((a, b) => b.measured.bytes - a.measured.bytes)
      .map((d) => ({ label: d.title, href: `#dataset/${d.name}`, cells: cols.map((c) => d.measured.coverage[c] / d.measured.files) }));
    // A cell opens the explorer on the datasets that have the field.
    const fields = cols.map((c) => ({ label: capital(fieldName(c)), href: filterHash("coverage", [c]) }));
    $("#metadata-charts").replaceChildren(chartCard("Metadata coverage", null, svg.heat(rows, fields, { format: percent })));
  }

  // A backdrop click lands on the dialog itself. A text selection dragged out of the dialog
  // ends there too, but started inside it.
  function closeOnBackdrop(dialog) {
    let down = null;
    dialog.addEventListener("pointerdown", (e) => (down = e.target));
    dialog.addEventListener("click", (e) => down === dialog && e.target === dialog && dialog.close());
  }

  function initExplorer() {
    $("#x-groups").replaceChildren(...GROUPS.map(buildGroup));
    // On narrow screens the filters move into a bottom sheet while it is open.
    const sheet = $("#x-sheet");
    $("#x-filters-open").onclick = () => {
      $("#x-sheet-body").append($("#x-facets"));
      sheet.showModal();
    };
    sheet.addEventListener("close", () => $("#x-sidebar").append($("#x-facets")));
    closeOnBackdrop(sheet);
    $("#x-shape").open = !matchMedia("(max-width: 560px)").matches;
    $("#x-search").oninput = (e) => {
      setSearch(e.target.value);
      update();
    };
    $("#x-reset").onclick = resetFilters;
    $("#x-script").onclick = (e) => {
      if (e.currentTarget.getAttribute("aria-disabled") !== "true") showScript($("#x-script-panel").hidden);
    };
    $("#x-script-hide").onclick = () => showScript(false);
    for (const b of $$("[data-view]")) {
      b.onclick = () => {
        state.view = b.dataset.view;
        update();
      };
    }
    $("#x-sort").onchange = (e) => {
      state.sort = `${e.target.value}:${e.target.value === "title" ? "asc" : "desc"}`;
      update();
    };
    $("#x-sort-dir").onclick = () => {
      const [key, dir] = state.sort.split(":");
      state.sort = `${key}:${dir === "asc" ? "desc" : "asc"}`;
      update();
    };
    $("#x-tbody").onclick = (e) => {
      const tr = e.target.closest("tr[data-id]");
      if (!tr || e.target.closest("a, button")) return;
      // The dialog gives focus back to the row's link when it closes.
      $(".ds-name", tr).focus();
      location.hash = `#dataset/${tr.dataset.name}`;
    };
  }

  // Dataset drawer

  function stats(d) {
    const m = d.measured;
    const tile = (label, value) => el("div", { class: "stat" }, el("div", { class: "muted", text: label }), el("div", { class: "stat-value" }, value));
    const range = (r, f, unit = "") => (r ? median(r, f) + unit : "not recorded");
    const present = (counts) => Object.keys(counts).filter((k) => counts[k]).join("/");
    // What the site files the dataset under.
    const classes = (label, key) => tile(label, labels(d, key) || "not stated");
    return [
      tile("Size", fmtBytes(m.bytes)),
      tile("Uncompressed", fmtBytes(m.raw_bytes)),
      tile("Acquisitions", fmtInt(m.acquisitions)),
      tile("Frames", fmtInt(m.frames)),
      tile("Subjects", m.coverage.subject_id ? fmtInt(m.subjects) : "not recorded"),
      tile("Center frequency", range(m.range.fc_mhz, fmt3, `${NBSP}MHz`)),
      tile("Elements", range(m.range.n_el, fmtInt)),
      tile("Data type", `${present(m.signal).toUpperCase()} ${present(m.dtype)}`),
      classes("Transmit scheme", "acquisition"),
      classes("Probe type", "probe_types"),
    ];
  }

  // Optional fields are in every file of a dataset or in none, bar the odd one in between.
  function coverage(d) {
    const { coverage: counts, files } = d.measured;
    return el(
      "ul",
      { class: "coverage" },
      Object.entries(counts).map(([f, n]) =>
        el("li", { class: n ? null : "absent" }, el("span", { class: n ? "check" : "cross" }), fieldName(f), n > 0 && n < files && el("span", { class: "muted", text: `${fmtInt(n)} of ${fmtInt(files)} files` })),
      ),
    );
  }

  function details(d) {
    const m = d.measured;
    const { frame_rate: rate, prf, depth_cm: depth } = m.range;
    const hz = (v) => (v >= 1000 ? `${fmt3(v / 1000)}${NBSP}kHz` : `${fmt3(v)}${NBSP}Hz`);
    const versions = Object.keys(m.zea_version);
    const rows = [
      ["Probes", d.probes.join(", ")],
      ["Ultrasound machine", d.systems.join(", ")],
      ["Species", d.species.join(", ")],
      ["Contributors", d.contributors.join("; ")],
      ["Created", d.created],
      ["Known issues", d.known_issues],
      ["License", d.license?.toUpperCase()],
      ["Frame rate", [rate && median(rate, hz), prf && `PRF ${median(prf, hz)}`].filter(Boolean).join("; ")],
      ["Imaging depth", depth && `${median(depth, fmt3)}${NBSP}cm`],
      ["zea version", versions.length === 1 ? versions[0] : countList(m.zea_version, "file")],
    ];
    return el("dl", null, rows.filter(([, v]) => v).flatMap(([k, v]) => [el("dt", { text: k }), el("dd", null, cardText(v))]));
  }

  // Scalars show their values; arrays their shapes, with the zea spec's axis names below.
  // A number that varies across the files shows as its median (min–max).
  function shapeCell(row) {
    const value = (v) => (typeof v === "number" ? v.toLocaleString("en-US", { maximumSignificantDigits: 6 }) : String(v));
    const spread = ([lo, mid, hi]) => (lo === hi ? value(lo) : `${value(mid)} (${value(lo)}–${value(hi)})`);
    if (row.range || row.values) {
      const text = row.values && [...row.values.map(value), row.distinct > row.values.length && `… (${fmtInt(row.distinct)} values)`].filter(Boolean);
      return el("td", { class: "mono" }, row.range && el("div", { text: spread(row.range) }), text && el("div", {}, breakable(text.join(", "), "_")));
    }
    const shapes = row.shapes || [];
    const names = (shapes[0] || []).map(([, name]) => name || "·");
    return el(
      "td",
      { class: "mono" },
      shapes.map((axes) => el("div", { text: axes.map(([size]) => spread(size)).join(" × ") || "scalar" })),
      names.some((n) => n !== "·") && el("div", { class: "muted", text: names.join(" × ") }),
    );
  }

  function keysSection(d) {
    const files = d.measured.files;
    const nonstandard = new Set(d.nonstandard_keys);
    const rows = [...d.files.keys, ...d.files.card_only.map((key) => ({ key, in: 0, cardOnly: true }))];
    const sections = [["data/", "Data"], ["scan/", "Scan"], ["probe/", "Probe"], ["metadata/", "Metadata"], ["metrics/", "Metrics"], ["custom/", "Custom (dataset-specific)"], ["", "Track and file"]];
    const sectionOf = (key) => sections.find(([prefix]) => key.startsWith(prefix))[1];
    const keyRow = (r) => {
      const info = state.zea[r.key.replace(/\/\*$/, "")];
      return el(
        "tr",
        null,
        el("td", { class: "mono" }, breakable(r.key), nonstandard.has(r.key) && el("span", { class: "tag nonstd", text: "not in zea spec" }), r.cardOnly && el("span", { class: "tag", text: "card only" })),
        el("td", { class: r.in < files ? "count partial" : "count", text: `${fmtInt(r.in)} of ${fmtInt(files)}` }),
        shapeCell(r),
        el("td", { class: "mono", text: r.dtype || "" }),
        el("td", { text: info?.description || (r.key.startsWith("custom/") ? "Dataset-specific field; see the data card." : "") }),
        el("td", { text: info?.unit && info.unit !== "–" ? info.unit : "" }),
      );
    };
    const head = ["Key", "In files", "Shape or value", "Type", `Description (zea ${state.index.zea.version})`, "Unit"];
    const table = el("table", { class: "keys" });
    // Each group of keys, with the column headings, is folded under its heading until it is opened.
    for (const [, title] of sections) {
      const group = rows.filter((r) => sectionOf(r.key) === title);
      if (!group.length) continue;
      const keys = el("tbody", { hidden: "" }, el("tr", null, head.map((h) => el("th", { scope: "col", text: h }))), group.map(keyRow));
      const toggle = el("button", {
        class: "group-toggle",
        "aria-expanded": "false",
        text: `${title} (${group.length})`,
        onclick: () => {
          keys.hidden = !keys.hidden;
          toggle.setAttribute("aria-expanded", String(!keys.hidden));
        },
      });
      table.append(el("tbody", null, el("tr", { class: "group" }, el("td", { colspan: 6 }, toggle))), keys);
    }
    return section(`HDF5 keys (${rows.length})`, null, el("div", { class: "scroll" }, table));
  }

  const section = (title, note, ...body) => el("section", null, el("h3", { text: title }), note && el("p", { class: "note", text: note }), ...body);
  // Minimal highlighting of the shell and Python snippets: comments, strings, the prompt,
  // flags and the Python keywords they use.
  const TOKENS = /(?<comment>#.*)|(?<string>"""[^]*?"""|"[^"]*"|'[^']*')|(?<prompt>^\$ )|(?<flag>(?<= )--?[\w-]+)|(?<keyword>\b(?:import|from|def|for|in|if|not|with|as|yield|return|print)\b)/gm;
  function highlight(text) {
    const parts = [];
    let end = 0;
    for (const m of text.matchAll(TOKENS)) {
      const kind = Object.keys(m.groups).find((k) => m.groups[k] !== undefined);
      parts.push(text.slice(end, m.index), el("span", { class: `tok-${kind}`, text: m[0] }));
      end = m.index + m[0].length;
    }
    return [...parts, text.slice(end)];
  }
  const codeBlock = (text) => el("div", { class: "code-block" }, el("button", { type: "button", class: "copy-btn", text: "Copy" }), el("pre", null, el("code", null, highlight(text))));
  // A card's text: lines starting with "- " or "* " form a list.
  function cardText(text) {
    const [lead, ...items] = (text || "").split(/^[-*] /m);
    return [lead.trim(), items.length > 0 && el("ul", { class: "card-list" }, items.map((i) => el("li", { text: i.trim() })))];
  }

  function drawerHead(d) {
    const facets = [["Setting", "setting"], ["Target", "targets"], ["Acquisition", "acquisition"], ["Probe", "probe_types"], ["Data", "data_type"], ["Dimensions", "dimensionality"], ["Tasks", "tasks"]];
    const link = (href, text) => el("a", { class: "btn btn-small btn-ghost", href, target: "_blank", rel: "noopener", text });
    return el(
      "div",
      { class: "drawer-head" },
      el(
        "div",
        null,
        el("p", { class: "kicker", text: [d.institution, d.collection_title].filter(Boolean).join(DOT) }),
        el("h2", { id: "drawer-title", text: d.title }),
        el("p", { class: "drawer-long", text: d.pretty_name }),
        el("div", { class: "card-summary" }, cardText(d.summary)),
        el(
          "div",
          { class: "facets" },
          facets.map(([label, key]) => {
            const list = chips(d, key, true);
            return list.length > 0 && el("div", null, el("span", { text: label }), el("span", { class: "chips" }, list));
          }),
        ),
        el("div", { class: "links" }, link(d.hub_url, "Files on Hugging Face"), link(d.card_url, "Data card")),
      ),
      el(
        "figure",
        null,
        d.preview ? el("img", { src: d.preview, alt: `Reference image for ${d.title}`, width: d.preview_size[0], height: d.preview_size[1] }) : el("div", { class: "placeholder", text: "No preview in the data card" }),
        d.image_source && el("figcaption", { text: `From ${d.image_source}` }),
      ),
    );
  }

  // Datasets are linked by their short name. Their folder in the Hub repo (the banner's
  // tiles link by that) works too, and a collection's folder opens its first dataset.
  function openDrawer(id) {
    const d = state.datasets.find((x) => x.name === id) || state.datasets.find((x) => x.id === id) || state.datasets.find((x) => x.collection === id);
    if (d && id !== d.name) history.replaceState(history.state, "", `#dataset/${d.name}`);
    if (d) id = d.id;
    const drawer = $("#drawer");
    $("#drawer-path").textContent = id;
    $("#drawer-body").replaceChildren(
      ...(d
        ? [
            drawerHead(d),
            section("Get the data", null, folders(d), el("p", { class: "note", text: `Copy ${copyText(d)}` }), copyBlock(d), ...processBlock(d), el("p", { class: "note", text: "Or stream the data in Python:" }), pythonBlock(d)),
            section("In the files", null, el("div", { class: "stats" }, stats(d))),
            section("Contents", null, shapeStrips([d])),
            section("Metadata coverage", "Optional fields, in every file or in none.", coverage(d)),
            section("Distributions", "Counted per track; file size per file.", shapeHists([d])),
            section("Details", null, details(d)),
            keysSection(d),
          ]
        : [el("h2", { id: "drawer-title", text: "Dataset not found" })]),
    );
    document.title = `${d ? d.title : "Not found"} | OpenH-RF`;
    if (!drawer.open) drawer.showModal();
    drawer.scrollTop = 0;
  }

  function initDrawer() {
    const drawer = $("#drawer");
    closeOnBackdrop(drawer);
    drawer.addEventListener("close", () => {
      if (!parseHash().path.startsWith("dataset/")) return;
      if (!history.state?.landed) return history.back();
      // The page opened at this dataset, so there is no entry of its own to go back to.
      history.replaceState(null, "", `#explorer${state.query}`);
      route();
    });
  }

  // Routing

  function showPage(name) {
    if (state.page !== name) scrollTo(0, 0);
    state.page = name;
    for (const v of ["home", "explorer", "stats"]) $(`#view-${v}`).hidden = v !== name;
    for (const a of $$("[data-nav]")) {
      if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    document.title = { home: "OpenH-RF | Open ultrasound channel data", explorer: "Explore datasets | OpenH-RF", stats: "Statistics | OpenH-RF" }[name];
  }

  function parseHash() {
    const hash = location.hash.slice(1);
    const at = hash.includes("?") ? hash.indexOf("?") : hash.length;
    return { path: hash.slice(0, at), query: hash.slice(at + 1) };
  }

  // A dataset opens over the view that is showing; a page opened at one shows the explorer.
  function route() {
    const { path, query } = parseHash();
    hideTip();
    if (path !== "explorer") $("#x-sheet").close();
    if (path.startsWith("dataset/")) {
      if (!state.page) {
        showPage("explorer");
        render();
      }
      openDrawer(path.slice("dataset/".length));
      return;
    }
    $("#drawer").close();
    if (path === "stats" || path.startsWith("stats/")) {
      showPage("stats");
      const section = $(`#stats-${path.slice("stats/".length)}`);
      if (section) section.scrollIntoView();
      return;
    }
    if (path !== "explorer") return showPage("home");
    showPage("explorer");
    applyQuery(query);
    state.query = explorerQuery();
    // Parameters the page does not know drop out of the address.
    if (query !== state.query.slice(1)) history.replaceState(history.state, "", `#explorer${state.query}`);
    // Closing the drawer comes back to the list as it was, with the focus in it.
    if (state.query !== state.rendered) render();
  }

  // Boot

  function haystack(d) {
    const vocab = Object.keys(state.vocab).flatMap((key) => [d[key]].flat().flatMap((v) => [state.vocab[key][v]?.label, ...(state.vocab[key][v]?.aliases || [])]));
    const keys = d.files.keys.map((k) => k.key);
    const parts = [d.id, d.name, d.pretty_name, ...d.institutions, d.summary, d.collection_title, ...d.probes, ...d.systems, ...d.keys, ...d.contributors, ...d.species, ...vocab, ...keys, ...Object.values(d.files.attrs).flat()];
    return parts.filter(Boolean).join("\n").toLowerCase();
  }

  // Follow the browser's theme, unless the switch in the top bar picks light or dark.
  function initTheme() {
    const root = document.documentElement;
    const tint = () => {
      const background = getComputedStyle(document.body).backgroundColor;
      for (const meta of $$('meta[name="theme-color"]')) meta.content = background;
    };
    for (const input of $$(".theme-switch input")) {
      input.checked = input.value === (root.dataset.theme || "auto");
      input.onchange = () => {
        if (input.value === "auto") delete root.dataset.theme;
        else root.dataset.theme = input.value;
        try {
          localStorage.setItem("theme", input.value);
        } catch {
          // Blocked storage: the choice lasts for this page view.
        }
        tint();
      };
    }
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", tint);
    tint();
  }

  // Show RF image on mouse-over/touch. If not mousing over, show 4 random RF images, fading randomly.
  function initBanner() {
    const SLOTS = 4, FADE = 500, MIN_HOLD = 1000, MAX_HOLD = 3500;
    const banner = $(".hero-examples"), track = $(".hero-track", banner), drawer = $("#drawer");
    const buttons = $$("[data-banner]", banner);
    for (const b of buttons) {
      b.onclick = () => {
        banner.classList.toggle("rf-first", b.dataset.banner === "rf");
        for (const other of buttons) other.setAttribute("aria-pressed", other === b);
      };
    }

    // First load the small version, then the big one after everything has loaded.
    const fullRf = () => {
      const full = new Image();
      full.src = "assets/img/examples-rf@2x.webp";
      full.decode().then(() => {
        for (const img of $$("img.rf", track)) img.src = full.src;
        banner.classList.add("rf-full");
      }, () => {});
    };
    if (document.readyState === "complete") fullRf();
    else addEventListener("load", fullRf, { once: true });

    // A tile and its twin in the other copy change together; a tile shown as the scroll wraps then stays in view.
    const twins = new Map();
    fetch("assets/img/examples.json", { cache: "no-cache" })
      .then((resp) => resp.json())
      .then(({ size: [W, H], tiles }) => {
        const sets = $$(".hero-set", track).map((set) =>
          tiles.map(([name, x, y, w, h]) => {
            const style = `left: ${(100 * x) / W}%; top: ${(100 * y) / H}%; width: ${(100 * w) / W}%; height: ${(100 * h) / H}%;` +
              ` background-size: ${(100 * W) / w}% ${(100 * H) / h}%; background-position: ${(100 * x) / (W - w)}% ${(100 * y) / (H - h)}%`;
            return set.appendChild(el("a", { class: "hero-tile", href: `#dataset/${name}`, tabindex: "-1", "aria-hidden": "true", style }));
          }),
        );
        for (let i = 0; i < tiles.length; i++) {
          const pair = [sets[0][i], sets[1][i]];
          for (const t of pair) twins.set(t, pair);
        }
        // The page opens with the tiles already shown, so skip their fade in.
        for (const slot of slots) next(slot, 0);
        for (const a of track.getAnimations({ subtree: true })) if (a instanceof CSSTransition) a.finish();
      });
    const setClass = (tile, cls, on) => {
      if (tile) for (const t of twins.get(tile)) t.classList.toggle(cls, on);
    };
    const primary = (tile) => (tile ? twins.get(tile)[0] : null);

    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    const slots = Array.from({ length: SLOTS }, () => ({ shown: null, fading: null, timer: 0 }));
    let held = null, hovering = false, touching = false;
    const idle = () => !reduce.matches && !hovering && !touching && !drawer.open;
    const randomHold = () => MIN_HOLD + Math.random() * (MAX_HOLD - MIN_HOLD);
    // Tiles in full view that stay in view for `ms` if the banner scrolls.
    const visible = (ms) => {
      const box = banner.getBoundingClientRect();
      const { animationName, animationDuration } = getComputedStyle(track);
      const pxPerSec = animationName === "none" ? 0 : track.offsetWidth / 2 / parseFloat(animationDuration);
      return $$(".hero-tile", track).filter((t) => {
        const r = t.getBoundingClientRect();
        return r.width && r.left >= box.left + (pxPerSec * ms) / 1000 && r.right <= box.right;
      });
    };
    function next(slot, fadeIn = FADE) {
      clearTimeout(slot.timer);
      setClass(slot.fading, "auto", false);
      setClass(slot.shown, "on", false);
      slot.fading = slot.shown;
      slot.shown = null;
      if (!idle()) return;
      const hold = randomHold();
      const taken = slots.flatMap((s) => [s.shown, s.fading]);
      const pool = visible(fadeIn + hold + FADE).map(primary).filter((t) => !taken.includes(t));
      if (pool.length === 0) {
        // Try again shortly; on a phone, new tiles scroll in.
        slot.timer = setTimeout(() => next(slot), 500);
        return;
      }
      slot.shown = pool[Math.floor(Math.random() * pool.length)];
      setClass(slot.shown, "auto", true);
      setClass(slot.shown, "on", true);
      slot.timer = setTimeout(() => next(slot), fadeIn + hold);
    }
    reduce.addEventListener("change", () => {
      for (const slot of slots) next(slot);
    });
    const pause = () => {
      for (const slot of slots) clearTimeout(slot.timer);
    };
    // The tile the pointer was on, if shown, gets a new hold before fading back slowly; the
    // empty slots fill up again.
    const resume = () => {
      if (!idle()) return;
      for (const slot of slots) {
        if (slot.shown) {
          setClass(slot.shown, "auto", true);
          slot.timer = setTimeout(() => next(slot), randomHold());
        } else {
          next(slot);
        }
      }
    };
    // Fade the shown tiles back at once, except the pointed one, which now fades quickly.
    const pointAt = (tile) => {
      tile = primary(tile);
      if (!tile) return null;
      for (const slot of slots) {
        for (const t of [slot.shown, slot.fading]) {
          if (t && t !== tile) {
            setClass(t, "auto", false);
            setClass(t, "on", false);
          }
        }
        if (slot.shown !== tile) slot.shown = null;
        slot.fading = null;
      }
      setClass(tile, "auto", false);
      return tile;
    };

    track.addEventListener("pointerenter", (e) => {
      if (e.pointerType !== "mouse") return;
      hovering = true;
      pause();
    });
    track.addEventListener("pointerleave", (e) => {
      if (e.pointerType !== "mouse") return;
      hovering = false;
      resume();
    });
    track.addEventListener("pointerover", (e) => {
      if (e.pointerType === "mouse") pointAt(e.target.closest(".hero-tile"));
    });
    // The dialog fires no event as it opens.
    new MutationObserver(() => {
      banner.classList.toggle("paused", drawer.open);
      if (drawer.open) pause();
      else resume();
    }).observe(drawer, { attributes: true, attributeFilter: ["open"] });

    const touch = (e) => {
      touching = e.touches.length > 0;
      banner.classList.toggle("touching", touching);
      if (e.type === "touchstart" && e.touches.length === 1) pause();
      const p = e.touches[0], box = banner.getBoundingClientRect();
      const inside = p && p.clientX >= box.left && p.clientX < box.right && p.clientY >= box.top && p.clientY < box.bottom;
      const tile = inside ? pointAt(document.elementFromPoint(p.clientX, p.clientY)?.closest(".hero-tile")) : null;
      if (tile !== held) {
        setClass(held, "held", false);
        held = tile;
        setClass(held, "held", true);
      }
      if (!touching) resume();
    };
    for (const type of ["touchstart", "touchmove", "touchend", "touchcancel"]) document.addEventListener(type, touch, { passive: true });
    // A long press would open the link's menu.
    banner.addEventListener("contextmenu", (e) => {
      if (held) e.preventDefault();
    });
  }

  function initAuthors() {
    const authors = $(".hero-authors");
    // The title and logo toggle the list, as its summary does.
    $(".hero-title a").onclick = (e) => {
      e.preventDefault();
      authors.open = !authors.open;
    };
    $(".authors-close", authors).onclick = () => {
      authors.open = false;
      $("summary", authors).scrollIntoView({ block: "nearest" });
      $("summary", authors).focus();
    };
  }

  async function boot() {
    initTheme();
    initBanner();
    initAuthors();
    document.addEventListener("pointermove", showTip);
    document.addEventListener("scroll", hideTip, { capture: true, passive: true });
    document.addEventListener("click", (e) => {
      const button = e.target.closest(".copy-btn");
      if (button) copy(button.nextElementSibling.textContent, "Copied to clipboard");
    });
    $(".skip-link").onclick = (e) => {
      e.preventDefault();
      $("#main").focus();
    };
    for (const b of $$("[data-measure]")) {
      b.onclick = () => {
        state.measure = b.dataset.measure;
        for (const other of $$("[data-measure]")) other.setAttribute("aria-pressed", other === b);
        renderBrowse();
      };
    }

    try {
      const resp = await fetch("data/datasets.json", { cache: "no-cache" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      state.index = await resp.json();
    } catch (err) {
      $("#main").prepend(el("p", { class: "load-error", text: `Could not load data/datasets.json (${err.message}). Serve the site with python site/build.py --serve.` }));
      return;
    }
    const index = state.index;
    state.vocab = index.vocabulary;
    state.zea = index.zea.keys;
    state.datasets = index.datasets;
    for (const d of state.datasets) {
      d._hay = haystack(d);
      d._values = Object.fromEntries(GROUPS.map((g) => [g.key, values(d, g)]));
    }
    for (const g of GROUPS) {
      g.options = options(g);
      g.labels = new Map(g.options.map((o) => [o.value, o.label]));
      state.filters[g.key] = new Map();
    }
    for (const field in FIELD_FACET) state.palette[field] = Object.keys(index.measured.corpus[field]).filter((id) => classLink(field, id));
    // The same colours by files and by size.
    state.palette.medium = state.palette.medium_bytes;
    renderOverview();
    renderStats();
    initExplorer();
    initDrawer();
    if (parseHash().path.startsWith("dataset/")) history.replaceState({ landed: true }, "");
    addEventListener("hashchange", route);
    route();
  }

  boot();
})();
