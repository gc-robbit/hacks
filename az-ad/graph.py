#!/usr/bin/env python3 -u

import adal
import argparse
import logging
import requests
import time

import graph_config


# TODO: Document app registration required, including permissions
class Graph(object):
    """
    Graph acts as a wrapper around Microsoft Graph API with convenience methods to not have to worry about pagination
    etc.
    Main focus right now is to extract users and their last login details (auditing)
    """

    def __init__(self, config):
        self._initialize(config)
        self.headers = {
            'Authorization': 'Bearer {token}'.format(token=self.token["accessToken"]),
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self._remote = '{config.API_BASE}/{config.API_VERSION}{{endpoint}}'.format(config=config)
        self.logger = logging.getLogger("graph")
        self.logger.setLevel(logging.ERROR)

    def _initialize(self, config):
        self.context = adal.AuthenticationContext(config.GRAPH_AUTHORITY)
        self.token = self.context.acquire_token_with_client_credentials(
            config.API_BASE, config.CLIENT_ID, config.CLIENT_SECRET
        )

    def get_guest_users(self) -> []:
        return self._query_for_values("/users?$filter=userType eq 'Guest'&$select=displayName,mail,id,userPrincipalName")

    def get_most_recent_sign_in(self, user_id):
        result = self._query(endpoint="/auditLogs/signIns?$filter=userId eq '{user_id}'&$top=1".format(user_id=user_id))
        return result['value'][0] if len(result['value']) == 1 else None

    def get_sign_ins(self):
        # Filter example for createDateTime:
        # endpoint="/auditLogs/signIns?$filter=userId eq 'object_id' and createdDateTime le 2019-09-01")
        return self._query_for_values(endpoint='/auditLogs/signIns')

    def get_group_name(self, object_id) -> str:
        display_name = None
        try:
            data = self._query(endpoint="/groups/{id}?$select=displayName".format(id=object_id))
            display_name = data['displayName']
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != requests.codes.not_found:
                raise e

        return display_name

    def _query_for_values(self, endpoint):
        query_result = self._query(endpoint=endpoint)
        result = []
        # Retrieves ALL results, which my be paginated
        while '@odata.nextLink' in query_result:
            result.extend(query_result['value'])
            self.logger.debug("Paging, fetching next page")
            query_result = self._query(url=query_result['@odata.nextLink'])
        # Add last result to values (the result which is not paginated)
        result.extend(query_result['value'])
        return result

    def _query(self, endpoint=None, url=None):
        if url:
            request_url = url
        else:
            request_url = self._remote.format(endpoint=endpoint)

        response = requests.get(url=request_url, headers=self.headers)
        if response.status_code == requests.codes.too_many_requests:
            # We're throttled! Wait before retrying
            self.logger.debug("Throttled, waiting...")
            time.sleep(10)
            return self._query(url=request_url)
        response.raise_for_status()
        return response.json()


def users_main(graph, args):
    count = 0

    for user in sorted(graph.get_guest_users(), key=lambda u: u['mail']):
        # user has {displayName, mail, id, userPrincipalName}
        # sign_in is None or has {createdDateTime}
        sign_in = graph.get_most_recent_sign_in(user['id'])
        display_user = not sign_in if args.no_logins else True
        if display_user:
            count += 1
            sign_in_date = 'no login' if not sign_in else sign_in['createdDateTime']
            print('{name:<30} - {mail:<40} - {date}'.format(
                name=user['displayName'],
                mail=user['mail'],
                date=sign_in_date)
            )
    print("Matched {count} user(s) in total".format(count=count))


def groups_main(graph, args):
    name = graph.get_group_name(args.id)
    print("Group: {id} has name: '{name}'".format(id=args.id, name=name))


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s')
    logger = logging.getLogger("main")
    logger.setLevel(logging.ERROR)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    users_parser = subparsers.add_parser('users', help='Commands for interacting with users')
    users_parser.add_argument("--no-logins", action="store_true", default=False, help="Only users without login")
    users_parser.set_defaults(func=users_main)

    groups_parser = subparsers.add_parser('groups', help='Commands for interacting with groups')
    groups_parser.add_argument('id')
    groups_parser.set_defaults(func=groups_main)

    args = parser.parse_args()
    graph = Graph(graph_config)
    args.func(graph, args)
