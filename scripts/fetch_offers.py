import json, os, sys, time
import requests

# France Travail "Offres d'emploi v2" API -- OAuth2 client_credentials flow.
# The auth flow below (token endpoint, client_credentials, scope) was confirmed
# working against a real account. The typeContrat filter went through two
# failed real attempts: first a hardcoded guess ("STA"), rejected by the API;
# then a lookup against the API's own referentiel/typesContrats endpoint,
# which DID work but returned the real, authoritative list of contract-type
# codes -- CCE, CDD, CDI, DDI, DIN, FRA, LIB, MIS, REP, SAI, TTI, DDT -- and
# none of them is "stage". That's not a bug to route around; it reflects a
# real legal distinction in France: a "stage" is governed by a school
# "convention de stage", not an employment contract, so it may not live in
# this employment-offers API's contract-type taxonomy at all.
#
# Rather than guess a third field name, this version does not depend on any
# exact categorical match existing. It searches by keyword instead (motsCles
# does full-text matching over title and description, and real internship
# postings reliably say "stage" or "stagiaire" in their text) and treats a
# contract-type filter as optional, best-effort enrichment: it tries to find
# a "stage"-labeled code in the referentiel and applies it only if one
# exists, logging clearly either way instead of crashing.

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
REFERENTIEL_CONTRATS_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/referentiel/typesContrats"

CLIENT_ID = os.environ["FRANCETRAVAIL_CLIENT_ID"]
CLIENT_SECRET = os.environ["FRANCETRAVAIL_CLIENT_SECRET"]
SCOPE = "api_offresdemploiv2 o2dsoffre"

# Edit this to your own search: keywords, commune/department code, radius (km).
# "stage" is part of the keyword search itself -- see the comment above on why
# this project does not filter on typeContrat as a hard requirement.
SEARCH_PARAMS = {
    "motsCles": "data stage",
    "commune": "72181",          # INSEE code for Le Mans; change to your target area
    "distance": "50",
    "sort": "1",                 # sort by date, most recent first
    "range": "0-49",             # first 50 results; see note below for more
}

def get_access_token(retries=4, backoff=5):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "scope": SCOPE,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=(10, 20),
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"  token request attempt {attempt}/{retries} failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  response body: {e.response.text[:500]}")
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"Could not obtain access token after {retries} attempts") from last_error

def try_resolve_contract_type_code(token, label_substring="stage"):
    """Best-effort only: look up a typeContrat code matching label_substring
    from France Travail's own referentiel endpoint. Returns None (never
    raises) if the endpoint is unreachable or no match exists -- confirmed by
    real testing that "stage" has no match in this taxonomy at all, which is
    an honest fact about the data (see the module docstring above), not a
    failure to fix. main() falls back to keyword-only search when this
    returns None."""
    try:
        resp = requests.get(
            REFERENTIEL_CONTRATS_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 20),
        )
        resp.raise_for_status()
        all_types = resp.json()
        print("Available contract types:", json.dumps(all_types, ensure_ascii=False))
        for t in all_types:
            if label_substring.lower() in t.get("libelle", "").lower():
                print(f"Resolved '{label_substring}' -> code '{t['code']}' ({t['libelle']})")
                return t["code"]
        print(f"No contract type matches '{label_substring}' -- proceeding with keyword search only "
              f"(this is expected: 'stage' is not part of this API's contract-type taxonomy).")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch contract-type referentiel ({e}) -- proceeding with keyword search only.")
        return None

def search_offers(token, retries=4, backoff=5):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                SEARCH_URL,
                params=SEARCH_PARAMS,
                headers={"Authorization": f"Bearer {token}"},
                timeout=(10, 30),
            )
            # This API returns 206 (Partial Content) with a Content-Range header
            # on a normal successful paginated response, not just 200 -- treat
            # both as success, everything else as a real error.
            if resp.status_code not in (200, 206):
                resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"  search attempt {attempt}/{retries} failed: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"  response body: {e.response.text[:500]}")
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"Could not search offers after {retries} attempts") from last_error

def main():
    print("Requesting access token...")
    token = get_access_token()

    print("Checking whether a 'stage' contract type code exists...")
    code = try_resolve_contract_type_code(token, "stage")
    if code:
        SEARCH_PARAMS["typeContrat"] = code

    print("Got token, searching offers...")
    data = search_offers(token)
    offers = data.get("resultats", [])
    print(f"Found {len(offers)} offers")

    os.makedirs("data/offers", exist_ok=True)
    with open("data/offers/raw_offers.json", "w") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "search_params": SEARCH_PARAMS, "offers": offers}, f, indent=2, ensure_ascii=False)
    print("Wrote data/offers/raw_offers.json")
    if offers:
        print("First offer preview:", json.dumps(offers[0], ensure_ascii=False, indent=2)[:800])

if __name__ == "__main__":
    main()
