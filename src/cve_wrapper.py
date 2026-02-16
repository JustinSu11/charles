
# TODO - Implement the NVD api to retrieve CVE data

import nvdlib

# Query cve's by recency, default to any
def query_cve_recent(keyword="", limit=10):
    if(limit >= 20):
        print("Limit is too high")
    nvdlib.cve.searchCVE(keyword=keyword, limit=limit)

def query_cve(keyword=""):
    nvdlib.cve.searchCVE()