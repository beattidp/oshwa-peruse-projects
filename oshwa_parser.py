import json
import os

def parse_oshwa_projects(filepath: str) -> list[dict]:
    """
    Parses the oshwa_projects.json file and extracts the oshwaUid
    and projectWebsite for each record.
    """
    if not os.path.exists(filepath):
        return []

    results = []
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            for record in data:
                uid = record.get("oshwaUid")
                website = record.get("projectWebsite")
                if uid and website:
                    if "github.com" in website.lower() and "#readme" not in website.lower():
                        website = website.rstrip("/") + "#readme"
                        
                    results.append({
                        "uid": uid,
                        "url": website,
                        "country": record.get("country", ""),
                        "projectName": record.get("projectName", ""),
                        "projectDescription": record.get("projectDescription", ""),
                        "documentationUrl": record.get("documentationUrl", ""),
                        "primaryType": record.get("primaryType", "")
                    })
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")

    return results

if __name__ == "__main__":
    # Test execution
    data = parse_oshwa_projects("oshwa_projects.json")
    print(f"Parsed {len(data)} records.")
    for d in data[:3]:
        print(d)
