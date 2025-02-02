#!/usr/bin/env python3

import json

# az ad group member list --group "AD Group" --query "[].mail" > ad-group-members.json
# Used ./bitbucket.py by retrieving all users and outputting their email as json


def load(file_name) -> []:
    data = None
    with open(file_name) as f:
        data = json.load(f)
    return data


bitbucket_users = load('bitbucket-user-emails.json')
developers = load('ad-group-members.json')

print("Users in AD Group but not in bitbucket_users")
for dev in sorted(developers):
    if dev not in bitbucket_users:
        print(dev)
