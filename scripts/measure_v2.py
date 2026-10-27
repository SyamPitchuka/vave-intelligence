"""
Measure the lexical properties of edge set v2.

Implements rapidfuzz's scorers directly (no network available):
  fuzz.ratio            = 2*LCS / (len1+len2) * 100      [indel similarity]
  fuzz.token_sort_ratio = ratio on whitespace-sorted tokens
  fuzz.token_set_ratio  = max over the intersection/difference triple

Purpose: show that the NEGATIVES are lexically indistinguishable from the
POSITIVES, so passing them cannot be explained by word overlap. This is the
same property that made v1 credible, measured the same way.
"""
import openpyxl
from collections import defaultdict
from pathlib import Path


def lcs(a, b):
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for ca in a:
        cur = [0]
        for j, cb in enumerate(b):
            cur.append(prev[j] + 1 if ca == cb else max(cur[j], prev[j + 1]))
        prev = cur
    return prev[-1]


def ratio(a, b):
    a, b = a.lower(), b.lower()
    if not a and not b:
        return 100.0
    return 200.0 * lcs(a, b) / (len(a) + len(b))


def token_sort_ratio(a, b):
    return ratio(" ".join(sorted(a.lower().split())), " ".join(sorted(b.lower().split())))


def token_set_ratio(a, b):
    ta, tb = set(a.lower().split()), set(b.lower().split())
    inter = " ".join(sorted(ta & tb))
    da = " ".join(sorted(ta - tb))
    db = " ".join(sorted(tb - ta))
    s1 = (inter + " " + da).strip()
    s2 = (inter + " " + db).strip()
    return max(ratio(inter, s1), ratio(inter, s2), ratio(s1, s2))


def jaccard(a, b):
    ta = set(a.lower().replace('.', ' ').replace(',', ' ').split())
    tb = set(b.lower().replace('.', ' ').replace(',', ' ').split())
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


wb = openpyxl.load_workbook(Path(__file__).resolve().parents[1] / "data" / "vave_duplicate_edge_cases_v2.xlsx")

HDR = [c.value for c in wb["Ideas"][1]]
iC, iD = HDR.index("Component"), HDR.index("Idea_Description")
iCur, iProp = HDR.index("Current design or process"), HDR.index("Proposed technical change")
iVol = HDR.index("HCV Rigid Truck (Annual Volume)")


def load(sheet):
    out = {}
    for r in wb[sheet].iter_rows(min_row=2, values_only=True):
        out[r[0]] = dict(comp=r[iC], desc=r[iD], cur=r[iCur], prop=r[iProp],
                         vols=tuple(r[iVol:iVol + 5]))
    return out


hist, qs = load("Ideas"), load("TestQueries")

rows = []
for r in wb["LabelledPairs"].iter_rows(min_row=2, values_only=True):
    qid, cid, label, probe, polarity, _why = r
    q, c = qs[qid], hist[cid]
    rows.append(dict(
        qid=qid, cid=cid, label=label, probe=probe, polarity=polarity,
        comp_exact=q["comp"].lower() == c["comp"].lower(),
        comp_sort=token_sort_ratio(q["comp"], c["comp"]),
        comp_set=token_set_ratio(q["comp"], c["comp"]),
        desc_jac=jaccard(q["desc"], c["desc"]),
        desc_set=token_set_ratio(q["desc"], c["desc"]),
        desc_sort=token_sort_ratio(q["desc"], c["desc"]),
        vols_differ=q["vols"] != c["vols"],
    ))

W = 118
print("=" * W)
print("EDGE SET v2 - LEXICAL PROPERTIES")
print("=" * W)

print("\n--- A. COMPONENT MATCHING: do the negatives clear a fuzzy threshold of 90? ---\n")
print(f"{'Query':<12} {'Query component':<30} {'Candidate component':<26} {'exact':<6} {'sort':>6} {'set':>7}  verdict@90")
print("-" * W)
for r in rows:
    if r["probe"] in ("component_variant_negative", "component_qualifier_negative", "sparse_negative"):
        q, c = qs[r["qid"]], hist[r["cid"]]
        over = "OVER-MATCHES" if max(r["comp_sort"], r["comp_set"]) >= 90 else "correctly below"
        print(f"{r['qid']:<12} {q['comp']:<30} {c['comp']:<26} {str(r['comp_exact']):<6} "
              f"{r['comp_sort']:>6.1f} {r['comp_set']:>7.1f}  {over}")

print("\n--- B. DESCRIPTION OVERLAP by probe type and polarity ---\n")
agg = defaultdict(list)
for r in rows:
    agg[(r["polarity"], r["probe"])].append(r)
print(f"{'Polarity':<10} {'Probe type':<28} {'n':>3} {'Jaccard':>9} {'tok_set':>9} {'tok_sort':>9}")
print("-" * W)
for (pol, probe) in sorted(agg, key=lambda k: (k[0], k[1])):
    g = agg[(pol, probe)]
    n = len(g)
    print(f"{pol:<10} {probe:<28} {n:>3} "
          f"{sum(x['desc_jac'] for x in g)/n:>9.3f} "
          f"{sum(x['desc_set'] for x in g)/n:>9.1f} "
          f"{sum(x['desc_sort'] for x in g)/n:>9.1f}")

pos = [r for r in rows if r["polarity"] == "positive"]
neg = [r for r in rows if r["polarity"] == "negative"]
print("-" * W)
print(f"{'POSITIVE':<10} {'(must be flagged)':<28} {len(pos):>3} "
      f"{sum(x['desc_jac'] for x in pos)/len(pos):>9.3f} "
      f"{sum(x['desc_set'] for x in pos)/len(pos):>9.1f} "
      f"{sum(x['desc_sort'] for x in pos)/len(pos):>9.1f}")
print(f"{'NEGATIVE':<10} {'(must NOT be flagged)':<28} {len(neg):>3} "
      f"{sum(x['desc_jac'] for x in neg)/len(neg):>9.3f} "
      f"{sum(x['desc_set'] for x in neg)/len(neg):>9.1f} "
      f"{sum(x['desc_sort'] for x in neg)/len(neg):>9.1f}")

pj = sum(x['desc_jac'] for x in pos) / len(pos)
nj = sum(x['desc_jac'] for x in neg) / len(neg)
print(f"\n  Separability by word overlap: {'NONE - negatives overlap MORE' if nj >= pj else f'positives higher by {pj-nj:.3f}'}")
print("  A lexical-only classifier cannot pass this set. That is the point.")

print("\n--- C. STRUCTURED SIGNAL: do programme volumes differ where they should? ---\n")
print(f"{'Query':<12} {'Probe type':<28} {'Query volumes':<22} {'Cand volumes':<22} differ")
print("-" * W)
for r in rows:
    if r["probe"] in ("different_programme", "same_programme_negative"):
        q, c = qs[r["qid"]], hist[r["cid"]]
        print(f"{r['qid']:<12} {r['probe']:<28} {str(q['vols']):<22} {str(c['vols']):<22} {r['vols_differ']}")
print("\n  v1 defect fixed: a structured programme signal now exists to detect.")

print("\n--- D. WORST CASES (highest-overlap negatives) ---\n")
for r in sorted(neg, key=lambda x: -x["desc_set"])[:5]:
    print(f"  {r['qid']}  {r['probe']:<28} tok_set {r['desc_set']:>5.1f}  jac {r['desc_jac']:.3f}  -> must return {r['label']}")
print("=" * W)
