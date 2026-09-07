import json, os, sys, time
import requests

# France Travail "Offres d'emploi v2" API -- OAuth2 client_credentials flow.
# Technical details confirmed against multiple independent sources (the official
# api.gouv.fr catalog entry, a maintained open-source Python wrapper, and a
# third-party integration guide) since this API requires per-user registration
# and could not be executed end-to-end without real credentials -- verify the
# exact endpoint/scope against your own francetravail.io application dashboard
# if anything here doesn't match on first run.

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

CLIENT_ID = os.environ["FRANCETRAVAIL_CLIENT_ID"]
CLIENT_SECRET = os.environ["FRANCETRAVAIL_CLIENT_SECRET"]
SCOPE = "api_offresdemploiv2 o2dsoffre"

# Edit this to your own search: keywords, commune/department code, radius (km).
SEARCH_PARAMS = {
    "motsCles": "data",
    "typeContrat": "STA",       # STA = stage (internship)
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
