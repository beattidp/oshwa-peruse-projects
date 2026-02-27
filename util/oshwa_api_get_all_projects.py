#!/usr/bin/env python3
# Referencing OSHWA projects at https://certification.oshwa.org/list.html
# Get information on all projects to a JSON file, using the API.
# API documentation is here
# https://certificationapi.oshwa.org/documentation

import os
import sys
import random
import time
import requests
import json
from pprint import pprint as pp
import locale


# get home dir, look for file ".oshwa_token" and load the token
with open(os.path.join(os.path.expanduser("~"),".oshwa_token"),"r") as inpfile:
    token = inpfile.read().rstrip('\n')

url = "https://certificationapi.oshwa.org/api/projects"


# example determined total: 3237
total = 0;

LIMIT = 200

payload = {
    'limit': LIMIT,
    'offset': 0
}

headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {token}'
}

cache_dir = "cache"

# # print(response.text.encode('utf8'))
# answer = response.text.encode('utf8')
# pp(answer)
# pp(r)
items = []
last_fetch = False
while True:
    if (last_fetch):
        #print(f"final fetch: ({payload['offset'] }), limit: ({payload['limit']})", 
        print("Last Fetch:", file=sys.stderr)

    # introduce a random delay between each fetch, 200 to 500 milliseconds
    time.sleep(int(random.uniform(20,50)) / 100)

    print(f"GET (offset={payload['offset']} limit={payload['limit']}: ", file=sys.stderr, end="")
    response = requests.request("GET", url, headers=headers, params=payload)
    r = json.loads(response.text)

    if not total:
        total = int(r['total'])

    for i in r['items']:
        items.append(i)

    print(f"new total items is {len(items)}",file=sys.stderr)
    if (last_fetch):
        break

    
    payload['offset'] = payload['offset'] + LIMIT
    new_offset = int(payload['offset'])
    if (new_offset + LIMIT > total):
        payload['limit'] = total - new_offset
        last_fetch = True


# if not os.path.exists(cache_dir):
#     os.makedirs(cache_dir)

save_path = os.path.join(".", "oshwa_projects.json")

with open(save_path, mode="w", encoding=locale.getencoding()) as oupfile:
    json.dump(items,oupfile)

def check_duplicates():
    ids = [ i['oshwaUid'] for i in items ]
    seen = set()
    dupes = set()
    for x in ids:
        if x in seen:
            dupes.add(x)
        else:
            seen.add(x)

    if (dupes):        
        print(f"Duplicate IDs Found: {dupes}")

"""
https://github.com/vgalin/html2image#readme
https://grokipedia.com/page/html2image

https://toga.beeware.org/en/latest/reference/api/
https://pyjs.org/examples/
https://www.wxpython.org/pages/downloads/

"""



"""
>>> uniq = list(set(ids))
>>> len(uniq)
3199
>>> 
>>> seen = set()
>>> dupes = set()
>>> for x in ids:
...   if x in seen:
...     dupes.add(x)
...   else:
...     seen.add(x)
... 
>>> dupes
{'US000046'}

"""