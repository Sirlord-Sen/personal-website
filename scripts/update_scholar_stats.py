#!/usr/bin/env python3
"""Refresh citation/publication counts from Google Scholar.

Fetches the profile for USER_ID and rewrites the numbers wherever the
HTML carries a gs-cites / gs-pubs / gs-hindex marker span, plus the
"N publications, N+ citations" phrases in the meta descriptions.

Run weekly by .github/workflows/scholar-stats.yml; safe to run by hand:
    python3 scripts/update_scholar_stats.py
"""
import re
import sys
import urllib.request
from pathlib import Path

USER_ID = "9smPY8wAAAAJ"
ROOT = Path(__file__).resolve().parent.parent
FILES = ["index.html", "research.html", "about.html", "skills.html", "interactive.html"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def fetch_with_scholarly():
    from scholarly import scholarly
    author = scholarly.fill(scholarly.search_author_id(USER_ID),
                            sections=["basics", "indices", "publications"])
    return {"cites": int(author["citedby"]),
            "hindex": int(author["hindex"]),
            "pubs": len(author["publications"])}


def fetch_with_urllib():
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    url = (f"https://scholar.google.com/citations?user={USER_ID}"
           "&hl=en&cstart=0&pagesize=100")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    html = urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8", "replace")
    # Sidebar table cells: citations(all), citations(recent), h(all), h(recent), i10(all), i10(recent)
    cells = re.findall(r'<td class="gsc_rsb_std">(\d+)</td>', html)
    pubs = len(re.findall(r'<tr class="gsc_a_tr"', html))
    if len(cells) < 3 or pubs == 0:
        raise ValueError("profile page did not parse (blocked or layout change)")
    return {"cites": int(cells[0]), "hindex": int(cells[2]), "pubs": pubs}


def current_value(marker):
    text = (ROOT / "index.html").read_text()
    m = re.search(rf'class="{marker}"[^>]*>(\d+)<', text)
    return int(m.group(1)) if m else None


def main():
    stats = None
    for fetch in (fetch_with_scholarly, fetch_with_urllib):
        try:
            stats = fetch()
            break
        except Exception as exc:
            print(f"note: {fetch.__name__} failed: {exc}")
    if stats is None:
        # Leave the site untouched rather than failing the workflow: the
        # worst case is numbers a week staler than intended.
        print("::warning::could not reach Google Scholar; site left unchanged")
        return 0

    print(f"fetched: {stats}")

    # Citation and publication counts only ever grow; a smaller value
    # means we parsed garbage (consent page, layout change), so bail out.
    old_cites = current_value("gs-cites")
    if old_cites is not None and stats["cites"] < old_cites:
        print(f"::warning::fetched citations {stats['cites']} < current "
              f"{old_cites}; refusing to update")
        return 0

    for name in FILES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text()
        text = re.sub(r'(class="gs-cites"[^>]*>)\d+(<)', rf'\g<1>{stats["cites"]}\g<2>', text)
        text = re.sub(r'(class="gs-pubs"[^>]*>)\d+(<)', rf'\g<1>{stats["pubs"]}\g<2>', text)
        text = re.sub(r'(class="gs-hindex"[^>]*>)\d+(<)', rf'\g<1>{stats["hindex"]}\g<2>', text)
        text = re.sub(r'\d+ publications, \d+\+ citations',
                      f'{stats["pubs"]} publications, {stats["cites"]}+ citations', text)
        text = re.sub(r'\d+ peer-reviewed papers', f'{stats["pubs"]} peer-reviewed papers', text)
        text = re.sub(r'\d+\+ citations, h-index \d+',
                      f'{stats["cites"]}+ citations, h-index {stats["hindex"]}', text)
        path.write_text(text)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
