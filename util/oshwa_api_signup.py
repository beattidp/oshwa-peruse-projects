#!/usr/bin/env python3
import os
import requests
import json

# Obviously, change to your own name and email...
dict_data = { "firstName": "Alfred_E",
      "lastName": "Neumann",
      "email": "mad+magazine@dc.com" 
}

payload = json.dumps(dict_data)

url = "https://certificationapi.oshwa.org/users/signup"

headers = {
    'Content-Type': 'application/json',
}

response = requests.request("POST", url, headers=headers, data=payload)

rt = response.text.encode('utf8')

print(rt)

'''
example response
b'{"token":"eyJhbGciJIUzI1NiOiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjIyZCIsImlhdCI6MTc2OTkzMjY5N2YwBCWxMTAzYTIyMDAxNTM5MjgzMSwiZXhwIjoxNzc4NTcyODMxfQ.Bq57cODFmpxNvSJ_Nlc4XErKHV2u09ypz3neFrGvWFo"}'
'''

token_dict = json.loads(rt.decode())

tokenfile = os.path.join(os.path.expanduser("~"),".oshwa_token")
if not os.path.exists(tokenfile):
    with open(tokenfile,"w+") as oupfile:
        _ = oupfile.write(token_dict['token'])
