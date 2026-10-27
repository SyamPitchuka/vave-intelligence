"""
Edge-case evaluation set v2 for VAVE duplicate detection.

DIFFERENT INSTRUMENT FROM v1, NOT MORE OF THE SAME.

v1 asked: "does the system handle these linguistic phenomena?"  Every case was a
phenomenon the system got wrong, so passing v1 only shows a rule fires.

v2 asks: "does each rule fire ONLY when it should?"  Every probe type carries a
positive AND a negative case, so a rule that fires too readily now costs marks
instead of earning them.

HONESTY ABOUT INDEPENDENCE
  v1 was authored without sight of the classifier.
  v2 is NOT independent in that sense: it was written knowing which rules exist
  (component fuzzy matching at 90, direction extraction from state pairs, scope
  comparison, negation cue windows).  It is an ADVERSARIAL PROBE SET aimed at
  those rules' known weak directions, which is a stronger test of over-firing
  and a weaker test of generalisation.  Report it as such.  It does not replace
  a held-out set authored blind.

Each case type isolates ONE mechanism and tests it in BOTH directions.
"""

import random
from pathlib import Path
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill

random.seed(20261028)

# A block is (component, dept, description, current, proposed, rationale, benefit, constraints)
# Each case: (case_type, query_block, [(candidate_block, label, why)], query_vols, cand_vols)

CASES = []

# Programme volume tuples: (HCV Rigid, HCV Tipper, Tractor-Trailer, RMC, COWL)
ALL_PROG = (1200, 800, 400, 300, 200)
RIGID_ONLY = (1200, 0, 0, 0, 0)
TIPPER_ONLY = (0, 800, 0, 0, 0)
TRACTOR_ONLY = (0, 0, 400, 0, 0)


def case(ct, q, cands, qv=ALL_PROG, cv=ALL_PROG):
    CASES.append(dict(case_type=ct, query=q, cands=cands, qv=qv, cv=cv))


# ═══════════════════════════════════════════════════════════════════════
# A. COMPONENT VARIANT NEGATIVES  — does fuzzy component matching at 90
#    over-match?  Component names are lexically close; the parts are not
#    the same part.  The proposed change is deliberately similar so the
#    description embedding will also score high.
#    THESE MUST NOT BE CALLED DUPLICATES.
# ═══════════════════════════════════════════════════════════════════════

case("component_variant_negative",
     ("Cab mounting damper", "Cab",
      "Replace the steel cab mounting damper housing with an aluminium alloy housing of equivalent stiffness to cut vehicle mass.",
      "Steel cab mounting damper housing.", "Aluminium alloy damper housing at equivalent stiffness.",
      "Lower density reduces mass once the section is resized.", "Mass and piece-cost reduction.",
      "Damping rate and isolation performance to be held."),
     [(("Cab mounting bracket", "Cab",
        "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass.",
        "Steel fabricated cab mounting bracket.", "Aluminium alloy bracket sized for equivalent stiffness.",
        "Lower density reduces mass if section size recovers stiffness.", "Lower mass and part cost.",
        "Stiffness, durability and cab-mount noise within current targets."),
       "similar_but_distinct",
       "DAMPER is not BRACKET. Two of three component tokens match and the proposed change is identical in kind. "
       "Probes whether relaxing component matching to fuzzy 90 now accepts a different part.")])

case("component_variant_negative",
     ("Front spring shackle", "Suspension",
      "Change the front spring shackle from forged steel to a fabricated steel assembly to reduce forging cost.",
      "Forged steel shackle.", "Fabricated steel shackle assembly.",
      "Fabrication avoids the forging die cost at this volume.", "Piece-cost and tooling reduction.",
      "Fatigue life at the pin bore to be validated."),
     [(("Front spring bracket", "Suspension",
        "Change the front spring bracket from forged steel to a fabricated steel assembly to reduce forging cost.",
        "Forged steel front spring bracket.", "Fabricated steel bracket assembly.",
        "Fabrication avoids forging die cost at current volumes.", "Piece-cost and tooling reduction.",
        "Fatigue life at the bolted joint to be validated."),
       "similar_but_distinct",
       "SHACKLE and BRACKET are different parts in the same assembly. Descriptions are near-identical by construction. "
       "This is the hardest negative in the set.")])

case("component_variant_negative",
     ("Door check bracket", "Cab",
      "Delete two webs from the door check bracket casting to reduce mass without affecting the check mechanism load path.",
      "Six-web casting.", "Four-web casting.",
      "The two deleted webs carry little load in the check-open case.", "Casting mass reduction.",
      "Check-open durability cycles to be re-run."),
     [(("Door hinge bracket", "Cab",
        "Delete two webs from the door hinge bracket casting to reduce mass without affecting the hinge load path.",
        "Six-web hinge bracket casting.", "Four-web casting.",
        "The deleted webs carry little load in the door-open case.", "Casting mass reduction.",
        "Door sag and slam durability to be re-run."),
       "similar_but_distinct",
       "CHECK bracket and HINGE bracket are different parts. One token differs out of three.")])

# ═══════════════════════════════════════════════════════════════════════
# A2. COMPONENT QUALIFIER NEGATIVES  — the sharpest probe in the set.
#     A positional qualifier makes the candidate name a STRICT SUBSET of the
#     query name, so token_set_ratio returns exactly 100.0 by construction -
#     the same containment property already diagnosed in the superset cases,
#     now striking the COMPONENT field. token_sort_ratio returns 85-91 on the
#     same pairs, so WHICH scorer guards component matching decides whether
#     these over-match. No threshold on token_set_ratio can stop them.
#     THESE MUST NOT BE CALLED DUPLICATES.
# ═══════════════════════════════════════════════════════════════════════

case("component_qualifier_negative",
     ("Front spring bracket rear", "Suspension",
      "Change the front spring REAR bracket from forged steel to a fabricated steel assembly to reduce forging cost.",
      "Forged steel front spring rear bracket.", "Fabricated steel rear bracket assembly.",
      "Fabrication avoids the forging die cost at this volume.", "Piece-cost and tooling reduction.",
      "Fatigue at the shackle pin bore to be validated."),
     [(("Front spring bracket", "Suspension",
        "Change the front spring bracket from forged steel to a fabricated steel assembly to reduce forging cost.",
        "Forged steel front spring bracket.", "Fabricated steel bracket assembly.",
        "Fabrication avoids forging die cost at current volumes.", "Piece-cost and tooling reduction.",
        "Fatigue life at the bolted joint to be validated."),
       "similar_but_distinct",
       "The front spring FRONT and REAR brackets are different parts with different load cases. The candidate name is a "
       "strict SUBSET of the query name, so token_set_ratio = 100.0 regardless of threshold. token_sort_ratio = 88.9.")])

case("component_qualifier_negative",
     ("Door hinge bracket lower", "Cab",
      "Delete two webs from the LOWER door hinge bracket casting to reduce mass without affecting the hinge load path.",
      "Six-web lower hinge bracket casting.", "Four-web casting.",
      "The deleted webs carry little load at the lower hinge.", "Casting mass reduction.",
      "Door sag and slam durability to be re-run."),
     [(("Door hinge bracket", "Cab",
        "Delete two webs from the door hinge bracket casting to reduce mass without affecting the hinge load path.",
        "Six-web hinge bracket casting.", "Four-web casting.",
        "The deleted webs carry little load in the door-open case.", "Casting mass reduction.",
        "Door sag and slam durability to be re-run."),
       "similar_but_distinct",
       "Upper and lower hinge brackets carry different proportions of door weight. Subset name: token_set_ratio = 100.0, "
       "token_sort_ratio = 85.7. Descriptions differ by one word.")])

case("component_qualifier_negative",
     ("Exhaust heat shield front", "Exhaust",
      "Replace the FRONT aluminised steel exhaust heat shield with an embossed aluminium shield of equal thermal performance.",
      "Aluminised steel front heat shield.", "Embossed aluminium front shield at equal thermal performance.",
      "Aluminium reflects better, so equal protection at lower mass.", "Mass and material cost reduction.",
      "Surface temperature near the manifold to be validated."),
     [(("Exhaust heat shield", "Exhaust",
        "Replace the aluminised steel exhaust heat shield with an embossed aluminium shield of equal thermal performance.",
        "Aluminised steel heat shield.", "Embossed aluminium shield at equal thermal performance.",
        "Aluminium reflects better, so equal protection at lower mass.", "Mass and material cost reduction.",
        "Surface temperature and fixing fatigue to be validated."),
       "similar_but_distinct",
       "The front shield sits near the manifold at far higher temperature than the mid shield. Subset name: "
       "token_set_ratio = 100.0, token_sort_ratio = 86.4. The hardest pair in the set on every lexical measure.")])

# ═══════════════════════════════════════════════════════════════════════
# B. DIRECTION AGREEMENT  — both sides propose the SAME direction, worded
#    differently.  Direction extraction must not block these.
#    THESE MUST BE CALLED DUPLICATES.
# ═══════════════════════════════════════════════════════════════════════

case("direction_agreement",
     ("Engine oil pan", "Powertrain",
      "Thin the engine oil pan wall from 1.5 mm down to 1.2 mm and fit an internal baffle so oil surge stays controlled.",
      "1.5 mm pressed steel oil pan.", "1.2 mm pan with internal surge baffle.",
      "The thinner wall is acceptable once surge is managed.", "Material and mass reduction.",
      "Oil surge, drumming and stone impact to be validated."),
     [(("Engine oil pan", "Powertrain",
        "Reduce engine oil pan sheet thickness from 1.5 mm to 1.2 mm and add a baffle to control oil surge.",
        "1.5 mm pressed steel oil pan.", "1.2 mm pan with an internal surge baffle.",
        "Thinner wall is acceptable if surge loads are managed.", "Material cost and mass reduction.",
        "Oil surge, drumming and stone impact to be validated."),
       "duplicate",
       "Same direction (1.5 to 1.2), same component, same added baffle. Query says 'thin ... down to' instead of 'reduce'. "
       "Probes whether direction extraction depends on the verb rather than the state pair.")])

case("direction_agreement",
     ("Frame intermediate crossmember", "Frame",
      "Take the frame intermediate crossmember section down by 1 mm and add a local doubler at the spring hanger.",
      "6 mm crossmember section.", "5 mm section with a local doubler.",
      "Load concentrates at the hanger, so the span can be lighter.", "Steel cost and unladen mass reduction.",
      "Frame torsional stiffness and hanger fatigue to be validated."),
     [(("Frame intermediate crossmember", "Frame",
        "Reduce the frame intermediate crossmember sheet thickness from 6 mm to 5 mm and add a local doubler at the spring hanger.",
        "6 mm crossmember section.", "5 mm section with a local doubler.",
        "Load concentrates at the hanger; the span is lightly loaded.", "Steel cost and unladen mass reduction.",
        "Frame torsional stiffness and hanger fatigue to be validated."),
       "duplicate",
       "ASYMMETRIC STATE PAIRS: the query gives a delta ('down by 1 mm'), the candidate gives from-to (6 to 5). "
       "Both are decreases. Probes whether a missing explicit pair causes a false direction conflict.")])

case("direction_agreement",
     ("Tail lamp lens", "Lamps",
      "Move the tail lamp lens away from polycarbonate and over to acrylic PMMA at low-impact positions to take out cost.",
      "Polycarbonate tail lamp lens.", "Acrylic PMMA lens at low-impact positions.",
      "PMMA is cheaper and UV stable where impact risk is low.", "Piece-price reduction.",
      "Impact and thermal shock by position to be validated."),
     [(("Tail lamp lens", "Lamps",
        "Change the tail lamp lens from polycarbonate to acrylic PMMA on lamps with low impact exposure to reduce part cost.",
        "Polycarbonate tail lamp lens.", "Acrylic PMMA lens at low-impact positions.",
        "PMMA is cheaper and more UV stable where impact risk is low.", "Piece-price reduction.",
        "Impact and thermal shock by position to be validated."),
       "duplicate",
       "Same substitution in the same direction (PC to PMMA), phrased as 'away from X and over to Y'. "
       "Probes whether material-pair direction depends on the word 'from'.")])

# ═══════════════════════════════════════════════════════════════════════
# C. REVERSAL WITHOUT STATES  — the known gap. Removing the reversal verb
#    rule means a reversal that names no materials yields no state pair.
#    THESE MUST NOT BE CALLED DUPLICATES.
# ═══════════════════════════════════════════════════════════════════════

case("reversal_no_states",
     ("Cab mounting bracket", "Cab",
      "Revert the cab mounting bracket to the previously released design following field fatigue findings at the mount face.",
      "Current released bracket.", "Return to the previously released design.",
      "Field returns show cracking at the mount face on the current design.", "Removes a warranty failure mode.",
      "Change-point management and mass impact to be accepted."),
     [(("Cab mounting bracket", "Cab",
        "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass.",
        "Steel fabricated cab mounting bracket.", "Aluminium alloy bracket sized for equivalent stiffness.",
        "Lower density reduces mass if section size recovers stiffness.", "Lower mass and part cost.",
        "Stiffness, durability and cab-mount noise within current targets."),
       "similar_but_distinct",
       "A reversal naming NEITHER material, so no state pair exists to flip. Direction extraction cannot see this. "
       "This is the coverage lost when the reversal verb rule was removed.")])

case("reversal_no_states",
     ("Headliner substrate", "Interior trims",
      "Roll back the headliner substrate change and reinstate the specification in use before the current release, after hot-climate sag complaints.",
      "Current released substrate.", "Reinstate the prior specification.",
      "Hot-climate field returns show sag beyond the acceptance limit.", "Removes a field quality issue.",
      "Mass and recyclability impact to be noted."),
     [(("Headliner substrate", "Interior trims",
        "Switch the headliner substrate from a phenolic resin board to a lighter PET felt while keeping the same formed thickness.",
        "Phenolic resin headliner board.", "PET felt substrate at equal formed thickness.",
        "PET felt gives similar stiffness at lower mass.", "Mass reduction and recyclability.",
        "Sag at high cabin temperature to be validated."),
       "similar_but_distinct",
       "Reversal expressed as 'roll back' and 'reinstate the prior specification', with no materials named.")])

# ═══════════════════════════════════════════════════════════════════════
# D. SCOPE SENSITIVITY  — is scope comparison too blunt?  One case adds a
#    COSMETIC second item (should still be a duplicate); one adds a
#    SUBSTANTIVE second change (should not).
# ═══════════════════════════════════════════════════════════════════════

case("scope_cosmetic",
     ("Battery tray", "Electrical",
      "Change the low-voltage battery tray from painted steel to a formed polypropylene tray with metal inserts at the clamp points, and update the part marking to the current corporate standard.",
      "Painted steel battery tray, legacy marking.", "Polypropylene tray with metal inserts, marking updated.",
      "The marking update is a documentation alignment carried with the change.", "Lower mass, no paint step.",
      "Clamp load retention and thermal ageing to be validated."),
     [(("Battery tray", "Electrical",
        "Change the low-voltage battery tray from painted steel to a formed polypropylene tray with metal inserts at the clamp points.",
        "Painted steel battery tray.", "Formed polypropylene tray with metal inserts.",
        "Polymer resists electrolyte corrosion and removes the paint operation.", "Lower mass, no paint step.",
        "Clamp load retention and thermal ageing to be validated."),
       "duplicate",
       "The second item is a PART MARKING update: no engineering content, no cost or validation consequence. "
       "The technical proposal is identical. Probes whether scope comparison counts documentation as scope.")])

case("scope_cosmetic",
     ("Exhaust heat shield", "Exhaust",
      "Replace the aluminised steel exhaust heat shield with an embossed aluminium shield of equal thermal performance, and move the supplier drawing to the latest template revision.",
      "Aluminised steel shield, old drawing template.", "Embossed aluminium shield, drawing re-issued.",
      "The drawing re-issue is administrative and carried with the change.", "Mass and material cost reduction.",
      "Surface temperature and fixing fatigue to be validated."),
     [(("Exhaust heat shield", "Exhaust",
        "Replace the aluminised steel exhaust heat shield with an embossed aluminium shield of equal thermal performance.",
        "Aluminised steel heat shield.", "Embossed aluminium shield at equal thermal performance.",
        "Aluminium reflects better, so equal protection at lower mass.", "Mass and material cost reduction.",
        "Surface temperature and fixing fatigue to be validated."),
       "duplicate",
       "Second item is a drawing template revision. Administrative, not a scope change.")])

case("scope_substantive",
     ("Radiator lower mounting", "Cooling",
      "Replace the steel radiator lower mounting with a glass-filled nylon mounting, and relocate the mounting 25 mm forward to open up fan tip clearance.",
      "Steel mounting at current position.", "Glass-filled nylon mounting, relocated 25 mm forward.",
      "The material change and the packaging move are proposed as one package.", "Mass saving plus a clearance issue resolved.",
      "Mounting creep at temperature and fan clearance to be validated."),
     [(("Radiator lower mounting", "Cooling",
        "Replace the steel radiator lower mounting with a glass-filled nylon mounting of equivalent load capacity.",
        "Steel radiator lower mounting.", "Glass-filled nylon mounting at equivalent load capacity.",
        "Nylon removes a corrosion path and reduces mass.", "Mass and cost reduction.",
        "Creep at under-bonnet temperature to be validated."),
       "similar_but_distinct",
       "The 25 mm relocation is a real second change with its own validation and packaging consequence. "
       "Confirms scope comparison still fires when the extra item has engineering content.")])

# ═══════════════════════════════════════════════════════════════════════
# E. DIFFERENT PROGRAMME  — v1's defect fixed: the volume columns now
#    genuinely differ, so a structured programme signal EXISTS to detect.
#    Plus a negative: same programme, phrased like a carry-over.
# ═══════════════════════════════════════════════════════════════════════

case("different_programme",
     ("Cab mounting bracket", "Cab",
      "Apply the aluminium cab mounting bracket, already released on the rigid truck, to the tipper programme.",
      "Steel bracket on the tipper programme.", "Aluminium alloy bracket, as released on the rigid truck.",
      "The design is proven on the rigid truck; tipper duty is more severe.", "Mass saving extended to a second programme.",
      "Tipper duty-cycle fatigue to be validated before carry-over."),
     [(("Cab mounting bracket", "Cab",
        "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass.",
        "Steel fabricated cab mounting bracket.", "Aluminium alloy bracket sized for equivalent stiffness.",
        "Lower density reduces mass if section size recovers stiffness.", "Lower mass and part cost.",
        "Stiffness, durability and cab-mount noise within current targets."),
       "related_not_duplicate",
       "Same technical change, DIFFERENT programme. Query volumes are tipper-only; candidate volumes are rigid-only. "
       "In v1 every row carried identical volumes, so no structured signal existed. Now it does.")],
     qv=TIPPER_ONLY, cv=RIGID_ONLY)

case("different_programme",
     ("Frame intermediate crossmember", "Frame",
      "Carry the 5 mm crossmember with the hanger doubler, released on the rigid truck, across to the tractor-trailer programme.",
      "6 mm crossmember on the tractor-trailer programme.", "5 mm crossmember with hanger doubler.",
      "Design is proven; the tractor-trailer load case differs at the fifth wheel.", "Mass saving extended to another programme.",
      "Fifth-wheel load path to be re-validated before carry-over."),
     [(("Frame intermediate crossmember", "Frame",
        "Reduce the frame intermediate crossmember sheet thickness from 6 mm to 5 mm and add a local doubler at the spring hanger.",
        "6 mm crossmember section.", "5 mm section with a local doubler.",
        "Load concentrates at the hanger; the span is lightly loaded.", "Steel cost and unladen mass reduction.",
        "Frame torsional stiffness and hanger fatigue to be validated."),
       "related_not_duplicate",
       "Same change, different programme and different governing load case. Volumes differ: tractor-only vs rigid-only.")],
     qv=TRACTOR_ONLY, cv=RIGID_ONLY)

case("same_programme_negative",
     ("Fuel tank mounting strap", "Fuel system",
      "Extend the rolled-edge fuel tank mounting strap design across the rigid truck range.",
      "Flat 60 mm strap on the rigid truck.", "50 mm strap with a rolled edge.",
      "The rolled edge recovers the section modulus lost to width.", "Steel and coating cost reduction.",
      "Tank retention under impulse load to be validated."),
     [(("Fuel tank mounting strap", "Fuel system",
        "Reduce fuel tank mounting strap width from 60 mm to 50 mm and add a rolled edge to restore bending stiffness.",
        "60 mm flat strap.", "50 mm strap with a rolled edge.",
        "The rolled edge recovers the section modulus lost to width.", "Steel and coating cost reduction.",
        "Tank retention under impulse load to be validated."),
       "duplicate",
       "Phrased like a carry-over ('extend across the range') but it is the SAME programme, rigid-only on both sides. "
       "Probes whether programme comparison fires on carry-over LANGUAGE instead of the programme fields.")],
     qv=RIGID_ONLY, cv=RIGID_ONLY)

# ═══════════════════════════════════════════════════════════════════════
# F. NEGATION ONLY  — the query rules something out and names NO
#    alternative action. v1's negation cases always named a second action,
#    which is why the fix looked stronger than it was.
#    THESE MUST NOT BE CALLED DUPLICATES.
# ═══════════════════════════════════════════════════════════════════════

case("negation_only",
     ("Steering column lower bracket", "Steering",
      "The aluminium steering column lower bracket proposal should not be taken forward. No change to the current bracket is proposed.",
      "Steel steering column lower bracket.", "No change proposed.",
      "Column shake results did not meet target in the aluminium build.", "Avoids a validation failure and retooling cost.",
      "None; the current design is retained."),
     [(("Steering column lower bracket", "Steering",
        "Replace the steel steering column lower bracket with an aluminium alloy bracket of equivalent stiffness.",
        "Steel steering column lower bracket.", "Aluminium alloy bracket of equivalent stiffness.",
        "Aluminium gives mass reduction if the section is resized.", "Mass saving with a cost benefit at volume.",
        "Column shake, crash stroke and fatigue to be validated."),
       "similar_but_distinct",
       "The query exists ONLY to reject the candidate and names no alternative action. Maximum lexical overlap, "
       "opposite intent, and no second action to rescue the verdict. The real test of negation handling.")])

case("negation_only",
     ("Battery tray", "Electrical",
      "Do not proceed with the polypropylene low-voltage battery tray. Retain the painted steel tray.",
      "Painted steel battery tray.", "Retain the painted steel tray; no change.",
      "Clamp load retention after thermal ageing did not meet the acceptance limit.", "Avoids a field retention risk.",
      "None; current design retained."),
     [(("Battery tray", "Electrical",
        "Change the low-voltage battery tray from painted steel to a formed polypropylene tray with metal inserts at the clamp points.",
        "Painted steel battery tray.", "Formed polypropylene tray with metal inserts.",
        "Polymer resists electrolyte corrosion and removes the paint operation.", "Lower mass, no paint step.",
        "Clamp load retention and thermal ageing to be validated."),
       "similar_but_distinct",
       "Names the material pair only to reject the change. 'Retain' is not a proposed action.")])

# ═══════════════════════════════════════════════════════════════════════
# G. SPARSE NEGATIVES  — v1 had two sparse duplicates and no sparse
#    non-duplicate, so the one genuine pass had no counterpart.
#    Sparse text starves direction and scope detection of signal.
# ═══════════════════════════════════════════════════════════════════════

case("sparse_negative",
     ("Door hinge bracket", "Cab",
      "Al bracket.",
      "Steel.", "Aluminium.",
      "Lighter.", "Weight saving.",
      "Stiffness."),
     [(("Cab mounting bracket", "Cab",
        "Replace the steel cab mounting bracket with an aluminium alloy bracket sized for equivalent stiffness to reduce vehicle mass.",
        "Steel fabricated cab mounting bracket.", "Aluminium alloy bracket sized for equivalent stiffness.",
        "Lower density reduces mass if section size recovers stiffness.", "Lower mass and part cost.",
        "Stiffness, durability and cab-mount noise within current targets."),
       "similar_but_distinct",
       "Sparse text, DIFFERENT component (door hinge vs cab mounting). Identical wording to the v1 sparse duplicate "
       "that passes. The only difference is the component. Tests whether that pass was component-aware or lucky.")])

case("sparse_negative",
     ("Engine oil pan", "Powertrain",
      "Thicker oil pan for stone impact.",
      "1.2 mm.", "1.5 mm.",
      "Stone impact.", "Fewer field failures.",
      "Mass up."),
     [(("Engine oil pan", "Powertrain",
        "Reduce engine oil pan sheet thickness from 1.5 mm to 1.2 mm and add a baffle to control oil surge.",
        "1.5 mm pressed steel oil pan.", "1.2 mm pan with an internal surge baffle.",
        "Thinner wall is acceptable if surge loads are managed.", "Material cost and mass reduction.",
        "Oil surge, drumming and stone impact to be validated."),
       "similar_but_distinct",
       "SPARSE AND OPPOSITE. The direction is only recoverable from the current/proposed fields (1.2 to 1.5), not the "
       "description. Tests whether direction extraction reads the structured fields or only the free text.")])

case("sparse_negative",
     ("Tail lamp lens", "Lamps",
      "PC instead of PMMA.",
      "PMMA lens.", "PC lens.",
      "Impact.", "Fewer cracks.",
      "Cost up."),
     [(("Tail lamp lens", "Lamps",
        "Change the tail lamp lens from polycarbonate to acrylic PMMA on lamps with low impact exposure to reduce part cost.",
        "Polycarbonate tail lamp lens.", "Acrylic PMMA lens at low-impact positions.",
        "PMMA is cheaper and more UV stable where impact risk is low.", "Piece-price reduction.",
        "Impact and thermal shock by position to be validated."),
       "similar_but_distinct",
       "A four-word REVERSAL. Both materials named, order flipped. The shortest possible flipped state pair.")])

# ═══════════════════════════════════════════════════════════════════════
# build workbook
# ═══════════════════════════════════════════════════════════════════════
HDR = ['Idea_ID', 'Component', 'Idea generation date', 'Idea belonged department',
       'Rejection date', 'Rejected department', 'HCV Rigid Truck (Annual Volume)',
       'HCV Tipper (Annual Volume)', 'Tractor-Trailer (Annual Volume)',
       'RMC (Annual Volume)', 'COWL (Annual Volume)', 'Idea_Description',
       'Current design or process', 'Proposed technical change', 'Engineering rationale',
       'Expected benefit', 'Constraints or validation requirements', 'Stage_Status',
       'Rejection_Category', 'Rejection_Reason', 'Idea_Type',
       'Applicable Vehicle / Tonnage Details', 'Saving per vehicle (INR)',
       'Total Combined Annual Saving Per Idea (INR)', 'Idea Disposition']

PROG_NAMES = ("HCV Rigid Truck", "HCV Tipper", "Tractor-Trailer", "RMC", "COWL")


def applicability(vols):
    live = [n for n, v in zip(PROG_NAMES, vols) if v > 0]
    if len(live) == len(PROG_NAMES):
        return "Synthetic applicability across HCV Rigid, Tipper, Tractor-Trailer, RMC and COWL."
    return "Synthetic applicability limited to: " + ", ".join(live) + "."


def row(iid, blk, vols, disp="Logged"):
    comp, dept, desc, cur, prop, rat, ben, con = blk
    gen = date(2023, 1, 1) + timedelta(days=random.randint(0, 1000))
    spv = random.randint(60, 520)
    return [iid, comp, gen.isoformat(), dept, None, None, *vols,
            desc, cur, prop, rat, ben, con,
            random.choice(["A", "B", "C", "D"]), None, None, "Edge case v2",
            applicability(vols), spv, spv * sum(vols), disp]


hist_rows, query_rows, pairs = [], [], []
seen_cand = {}
h = q = 0

for c in CASES:
    q += 1
    qid = f"VAVE-FQ-{q:03d}"
    query_rows.append(row(qid, c["query"], c["qv"]))
    for cand_blk, label, why in c["cands"]:
        key = (cand_blk[0], cand_blk[2], c["cv"])
        if key not in seen_cand:
            h += 1
            cid = f"VAVE-FH-{h:03d}"
            seen_cand[key] = cid
            hist_rows.append(row(cid, cand_blk, c["cv"], "Under evaluation"))
        pairs.append([qid, seen_cand[key], label, c["case_type"], why])

wb = openpyxl.Workbook()
HFILL = PatternFill("solid", fgColor="1F3864")
HFONT = Font(bold=True, color="FFFFFF", size=10)

cov = wb.active
cov.title = "Cover"
lines = [
    "SYNTHETIC DATA - DUPLICATE DETECTION EDGE CASES, SET v2", "",
    "Fictional VAVE examples. Not company records; must not be described as production history.", "",
    f"Historical ideas : {len(hist_rows)}",
    f"Edge-case queries: {len(query_rows)}",
    f"Labelled pairs   : {len(pairs)}",
    "ID prefixes      : VAVE-FQ-* (queries), VAVE-FH-* (historical) - distinct from v1's EQ/EH", "",
    "WHAT MAKES THIS A DIFFERENT INSTRUMENT FROM v1", "",
    "  v1 asked:  does the system handle these linguistic phenomena?",
    "             Every case was one the system got wrong, so passing shows only that a rule fires.",
    "",
    "  v2 asks:   does each rule fire ONLY when it should?",
    "             Most probe types now carry a NEGATIVE counterpart. A rule that fires too",
    "             readily loses marks here instead of earning them.",
    "",
    "DECLARED LIMITATION - READ BEFORE REPORTING RESULTS", "",
    "  v1 was authored without sight of the classifier: genuinely independent.",
    "  v2 is NOT independent in that sense. It was written knowing which rules exist",
    "  (component fuzzy matching at 90, direction extraction from state pairs, scope",
    "  comparison, negation cue windows) and aims at their known weak directions.",
    "",
    "  It is therefore an ADVERSARIAL PROBE SET: a strong test of over-firing and",
    "  brittleness, a weak test of generalisation. It does not replace a held-out set",
    "  authored blind. Report it as such.", "",
    "PROBE TYPES", "",
    "  component_variant_negative  NEGATIVE. Component names lexically close, parts genuinely",
    "      different (damper vs bracket, shackle vs bracket, check vs hinge). Proposed changes",
    "      deliberately similar so the embedding also scores high. Measured: these names score",
    "      77-85 on token_set_ratio, so they sit BELOW a threshold of 90. The pressure here is",
    "      on the description route, not the component gate - descriptions reach 0.78 Jaccard.",
    "",
    "  component_qualifier_negative  NEGATIVE. THE SHARPEST PROBE IN THE SET. A positional",
    "      qualifier makes the candidate name a strict SUBSET of the query name (front spring",
    "      bracket REAR vs front spring bracket), so token_set_ratio returns exactly 100.0 by",
    "      construction - no threshold can stop it. token_sort_ratio returns 85-89 on the same",
    "      pairs. So WHICH scorer guards component matching decides the outcome. This is the",
    "      containment property already diagnosed in the superset cases, now striking the",
    "      component field, and it is the direct risk created by relaxing exact string matching.",
    "",
    "  direction_agreement         POSITIVE. Same direction, different wording - 'thin down to',",
    "      'take down by 1 mm', 'away from X over to Y'. One case is deliberately ASYMMETRIC",
    "      (delta on one side, from-to on the other). Probes false direction conflicts.",
    "",
    "  reversal_no_states          NEGATIVE. A reversal naming NEITHER material, so no state pair",
    "      exists to flip. This is the coverage lost when the reversal verb rule was removed.",
    "",
    "  scope_cosmetic              POSITIVE. Second item is a part marking update or a drawing",
    "      template revision: no engineering content. Probes whether scope comparison counts",
    "      documentation as scope.",
    "",
    "  scope_substantive           NEGATIVE. Second item is a 25 mm relocation with its own",
    "      validation consequence. Confirms scope comparison still fires when it should.",
    "",
    "  different_programme         v1's DEFECT FIXED. The volume columns now genuinely differ",
    "      (tipper-only vs rigid-only, tractor-only vs rigid-only), so a structured programme",
    "      signal exists to detect. In v1 every row carried identical volumes.",
    "",
    "  same_programme_negative     Phrased like a carry-over ('extend across the range') but it is",
    "      the SAME programme on both sides. Probes whether programme comparison fires on",
    "      carry-over LANGUAGE instead of the programme fields.",
    "",
    "  sparse_negative             NEGATIVE. v1 had two sparse duplicates and no sparse",
    "      non-duplicate, so its one genuine pass had no counterpart. One case differs from the",
    "      v1 passing case ONLY in component. One is sparse AND opposite, with direction",
    "      recoverable only from the structured fields. One is a four-word reversal.", "",
    "LABELS",
    "  duplicate             - same component, same technical change, reworded",
    "  similar_but_distinct  - overlapping but a different or opposite change",
    "  related_not_duplicate - same change, different programme (if the system has no equivalent",
    "      verdict, score as correct when NOT called a duplicate)", "",
    "HOW TO READ RESULTS", "",
    "  Score by PROBE TYPE, never in aggregate.",
    "  Positives and negatives must be reported SEPARATELY. A rule that passes every positive",
    "  and fails every negative has not been validated - it has been shown to over-fire.",
    "",
    "  For each failure, name the layer: candidate selection, component matching, direction",
    "  extraction, scope comparison, the cosine threshold, or the lexical route.",
    "",
    "  Record RETRIEVAL separately from VERDICT. If the labelled candidate was never shown,",
    "  the verdict was never tested - that is a third outcome, not a pass.",
]
for i, line in enumerate(lines, 1):
    cov.cell(i, 1, line)
cov.column_dimensions['A'].width = 100

for name, rows in (("Ideas", hist_rows), ("TestQueries", query_rows)):
    ws = wb.create_sheet(name)
    ws.append(HDR)
    for cell_ in ws[1]:
        cell_.fill, cell_.font = HFILL, HFONT
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    for col, w in (('A', 14), ('B', 30), ('D', 18), ('L', 78), ('M', 36), ('N', 40), ('V', 50)):
        ws.column_dimensions[col].width = w

ws = wb.create_sheet("LabelledPairs")
ws.append(["Query_ID", "Candidate_ID", "Label", "Probe_Type", "Polarity", "Why"])
for cell_ in ws[1]:
    cell_.fill, cell_.font = HFILL, HFONT
POLARITY = {
    "component_variant_negative": "negative",
    "component_qualifier_negative": "negative",
    "direction_agreement": "positive",
    "reversal_no_states": "negative",
    "scope_cosmetic": "positive",
    "scope_substantive": "negative",
    "different_programme": "negative",
    "same_programme_negative": "positive",
    "negation_only": "negative",
    "sparse_negative": "negative",
}
for p in pairs:
    ws.append([p[0], p[1], p[2], p[3], POLARITY[p[3]], p[4]])
ws.freeze_panes = "A2"
for col, w in (('A', 14), ('B', 14), ('C', 24), ('D', 28), ('E', 11), ('F', 100)):
    ws.column_dimensions[col].width = w

wb.save(Path(__file__).resolve().parents[1] / "data" / "vave_duplicate_edge_cases_v2.xlsx")

from collections import Counter
print(f"historical : {len(hist_rows)}")
print(f"queries    : {len(query_rows)}")
print(f"pairs      : {len(pairs)}")
print("\nby probe type:")
for k, v in Counter(p[3] for p in pairs).most_common():
    print(f"   {v:3d}  {POLARITY[k]:9s}  {k}")
print("\nlabels     :", dict(Counter(p[2] for p in pairs)))
print("polarity   :", dict(Counter(POLARITY[p[3]] for p in pairs)))
