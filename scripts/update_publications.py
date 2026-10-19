#!/usr/bin/env python3
"""Sync the Research page's paper list with Google Scholar.

Scrapes the profile's publication table, updates per-paper citation
counts in scripts/papers.json, appends any papers not yet in the data
(with a bare auto-generated card until a description is added), then
re-renders the paper cards between the PUBLICATIONS markers in
research.html using the site's existing design.

Run weekly by .github/workflows/scholar-stats.yml; safe to run by hand:
    python3 scripts/update_publications.py
"""
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

USER_ID = "9smPY8wAAAAJ"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "scripts" / "papers.json"
PAGE = ROOT / "research.html"
START = "<!-- PUBLICATIONS:START -->"
END = "<!-- PUBLICATIONS:END -->"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def norm(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def fetch_rows():
    """Return deduplicated [{title, cites, year, venue}] from the profile."""
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    url = (f"https://scholar.google.com/citations?user={USER_ID}"
           "&hl=en&cstart=0&pagesize=100")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    page = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8", "replace")
    rows = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', page, re.S)
    out = {}
    for r in rows:
        m = re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', r, re.S)
        if not m:
            continue
        title = strip_tags(m.group(1))
        cites_m = re.search(r'class="gsc_a_ac[^"]*"[^>]*>(\d*)<', r)
        year_m = re.search(r'class="gsc_a_h[^"]*"[^>]*>(\d{4})<', r)
        grays = re.findall(r'<div class="gs_gray">(.*?)</div>', r, re.S)
        row = {
            "title": title,
            "cites": int(cites_m.group(1)) if cites_m and cites_m.group(1) else 0,
            "year": int(year_m.group(1)) if year_m else None,
            "venue": strip_tags(grays[1]) if len(grays) > 1 else "",
        }
        key = norm(title)
        # Scholar sometimes lists near-duplicate records; keep the best-cited one.
        if key not in out or row["cites"] > out[key]["cites"]:
            out[key] = row
    if not out:
        raise ValueError("no publication rows parsed (blocked or layout change)")
    return out


def merge(papers, rows):
    known = {}
    for p in papers:
        known[norm(p["title"])] = p
        for a in p.get("aliases", []):
            known[norm(a)] = p
    for key, row in rows.items():
        p = known.get(key)
        if p is None:
            papers.append({
                "title": row["title"],
                "year": row["year"] or 2026,
                "url": None,
                "meta": "NEW",
                "citations": row["cites"],
                "abstract": "",
                "tags": [["New", False]],
                "venue": [row["venue"], str(row["year"] or "")],
                "auto": True,
            })
            print(f"added new paper from Scholar: {row['title'][:70]}")
        elif row["cites"] > p.get("citations", 0):
            print(f"citations {p.get('citations', 0)} -> {row['cites']}: {p['title'][:60]}")
            p["citations"] = row["cites"]


def render_item(p):
    n = p.get("citations", 0)
    meta = p["meta"]
    if n > 0:
        meta += f" · {n} CITATION" + ("S" if n != 1 else "")
    if p.get("url"):
        title = (f'<a href="{p["url"]}" target="_blank" rel="noopener" '
                 f'style="color:inherit;text-decoration:none">{p["title"]}</a>')
    else:
        title = p["title"]
    abstract = (f'\n        <p class="paper-abstract">{p["abstract"]}</p>'
                if p.get("abstract") else "")
    tags = "".join(
        f'<span class="ptag{" highlight" if hl else ""}">{t}</span>'
        for t, hl in p.get("tags", []))
    if p.get("press"):
        tags += (f'<a class="ptag highlight" href="{p["press"]["url"]}" target="_blank" '
                 f'rel="noopener" style="text-decoration:none">{p["press"]["label"]} ↗</a>')
    venue = "<br>".join(line for line in p.get("venue", []) if line)
    return f"""
    <div class="paper-item reveal">
      <div class="paper-year">{p["year"]}</div>
      <div class="paper-body">
        <div class="paper-meta">{meta}</div>
        <div class="paper-title">{title}</div>{abstract}
        <div class="paper-tags">{tags}</div>
      </div>
      <div class="paper-venue">{venue}</div>
    </div>
"""


def render(papers):
    papers = sorted(papers, key=lambda p: (-p["year"], -p.get("citations", 0), p["title"]))
    block = START + "\n" + "".join(render_item(p) for p in papers) + "\n  " + END
    text = PAGE.read_text()
    if START not in text or END not in text:
        raise SystemExit("PUBLICATIONS markers missing from research.html")
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, flags=re.S)
    PAGE.write_text(new)
    print(f"rendered {len(papers)} papers")


def main():
    papers = json.loads(DATA.read_text())
    try:
        rows = fetch_rows()
    except Exception as exc:
        print(f"::warning::could not reach Google Scholar ({exc}); "
              "re-rendering from stored data only")
        rows = {}
    if rows:
        merge(papers, rows)
        DATA.write_text(json.dumps(papers, indent=2, ensure_ascii=False) + "\n")
    render(papers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
