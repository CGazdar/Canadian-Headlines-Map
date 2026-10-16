"""Turn province boundaries into docs/map.js (the shapes the website draws).

Step 1, download the boundaries once (in the terminal, from the project folder):
  curl -L -o ne_admin1.geojson https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_1_states_provinces.geojson
Step 2:  python make_map.py
Natural Earth is public domain. Needs no extra packages.
"""
import json
import math
import sys

from db import HERE

SRC = HERE / "ne_admin1.geojson"
OUT = HERE / "docs" / "map.js"
WIDTH = 640           # map width in drawing units
TOLERANCE = 0.5       # simplification, in drawing units (higher = rougher, smaller file)
MIN_AREA = 1.5        # drop islands smaller than this (square drawing units)
NAME_TO_CODE = {"Alberta": "AB", "British Columbia": "BC", "Manitoba": "MB", "New Brunswick": "NB",
                "Newfoundland and Labrador": "NL", "Nova Scotia": "NS", "Northwest Territories": "NT",
                "Nunavut": "NU", "Ontario": "ON", "Prince Edward Island": "PE", "Quebec": "QC",
                "Québec": "QC", "Saskatchewan": "SK", "Yukon": "YT", "Yukon Territory": "YT"}


def lcc(lon, lat, lat1=49.0, lat2=77.0, lat0=63.390675, lon0=-91.866667):
    """Lambert conformal conic (the projection Statistics Canada uses for Canada)."""
    r = math.radians
    p1, p2, p0 = r(lat1), r(lat2), r(lat0)
    n = math.log(math.cos(p1) / math.cos(p2)) / math.log(
        math.tan(math.pi / 4 + p2 / 2) / math.tan(math.pi / 4 + p1 / 2))
    F = math.cos(p1) * math.tan(math.pi / 4 + p1 / 2) ** n / n
    rho0 = F / math.tan(math.pi / 4 + p0 / 2) ** n
    rho = F / math.tan(math.pi / 4 + r(lat) / 2) ** n
    th = n * r(lon - lon0)
    return rho * math.sin(th), rho0 - rho * math.cos(th)


def code_of(props):
    for key in ("postal", "iso_3166_2"):
        v = (props.get(key) or "")
        if v:
            return v[-2:].upper()
    return NAME_TO_CODE.get(props.get("name") or props.get("NAME") or "")


def is_canada(props):
    adm = props.get("admin") or props.get("ADMIN") or props.get("adm0_a3") or props.get("sov_a3")
    if adm:
        return adm in ("Canada", "CAN")
    return code_of(props) in NAME_TO_CODE.values()


def rings_of(geom):
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return []
    return [ring for poly in polys for ring in poly]


def area(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def dp(points, tol):
    """Douglas-Peucker on an open polyline (iterative)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            x, y = points[i]
            d = (math.hypot(x - x1, y - y1) if norm == 0
                 else abs(dy * (x - x1) - dx * (y - y1)) / norm)
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, keep) if k]


def main():
    if not SRC.exists():
        sys.exit(f"Missing {SRC.name}. Run the curl command at the top of this file first.")
    feats = json.load(open(SRC, encoding="utf-8"))["features"]
    raw = {}
    for f in feats:
        p = f["properties"]
        if not is_canada(p):
            continue
        code = code_of(p)
        if code not in NAME_TO_CODE.values():
            continue
        raw.setdefault(code, []).extend(
            [[lcc(lon, lat) for lon, lat, *_ in ring] for ring in rings_of(f["geometry"])])
    if len(raw) < 10:
        sys.exit(f"Only found {sorted(raw)}; is this the right file?")

    xs = [x for rs in raw.values() for r in rs for x, _ in r]
    ys = [y for rs in raw.values() for r in rs for _, y in r]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    s = WIDTH / (x1 - x0)
    H = round((y1 - y0) * s, 1)

    provinces, centres = {}, {}
    for code, rs in raw.items():
        scr = [[((x - x0) * s, (y1 - y) * s) for x, y in r[:-1]] for r in rs]   # y flipped
        scr.sort(key=area, reverse=True)
        parts, biggest = [], None
        for i, r in enumerate(scr):
            if i > 0 and area(r) < MIN_AREA:
                continue
            simp = dp(r + [r[0]], TOLERANCE)[:-1]
            if len(simp) < 3:
                continue
            if biggest is None:
                biggest = simp
            parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in simp) + "Z")
        provinces[code] = "".join(parts)
        bx = [x for x, _ in biggest]
        by = [y for _, y in biggest]                 # label spot: centre of the largest piece
        centres[code] = [round((min(bx) + max(bx)) / 2, 1), round((min(by) + max(by)) / 2, 1)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("window.MAP = " + json.dumps({"w": WIDTH, "h": H, "paths": provinces,
                                                "centres": centres}) + ";\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(provinces)} provinces/territories, {OUT.stat().st_size // 1024} KB")
    missing = sorted(set(NAME_TO_CODE.values()) - set(provinces))
    if missing:
        print("Not found:", missing)


if __name__ == "__main__":
    main()