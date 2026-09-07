import csv, json, os, time

def load_profile(path="data/profile/my_skills.csv"):
    profile = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            profile[row["skill"]] = {"level": int(row["level"]), "evidence": row["evidence"]}
    return profile

def score_offer(profile, required_skills):
    if not required_skills:
        return {"score": 0.0, "coverage": 0.0, "matched": [], "gaps": list(required_skills)}
    matched = [s for s in required_skills if s in profile]
    gaps = [s for s in required_skills if s not in profile]
    score = sum(profile[s]["level"] for s in matched) / (len(required_skills) * 5)
    coverage = len(matched) / len(required_skills)
    return {"score": round(score, 3), "coverage": round(coverage, 3), "matched": matched, "gaps": gaps}

def main():
    profile = load_profile()
    with open("data/offers/structured_offers.json") as f:
        data = json.load(f)

    results = []
    for offer in data["offers"]:
        m = score_offer(profile, offer["required_skills"])
        results.append({**offer, **m})

    results.sort(key=lambda r: r["score"], reverse=True)

    gap_counts = {}
    for r in results:
        for g in r["gaps"]:
            gap_counts[g] = gap_counts.get(g, 0) + 1
    top_gaps = sorted(gap_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_offers": len(results),
        "offers": results,
        "top_skill_gaps": [{"skill": s, "count": c} for s, c in top_gaps],
    }
    os.makedirs("docs/data", exist_ok=True)
    with open("docs/data/matches.json", "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Wrote docs/data/matches.json ({len(results)} offers ranked)")
    for r in results:
        print(f"  {r['score']:.3f}  {r['title']} @ {r['company']}  (coverage {r['coverage']:.0%}, gaps: {r['gaps']})")

if __name__ == "__main__":
    main()
