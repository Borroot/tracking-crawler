# Deadline 6 March 2024
# apotheekenhuid.nl

# Virtual env windows to create requirements.txt:
## ./OTP/Scripts/activate
## pip freeze > requirements.txt
## deactivate

# Imports
from tld import get_fld
import json
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from dateutil import parser

def get_urls_from_entries(data):
    urls = set()
    for entry in data['log']['entries']:
        urls.add(entry['request']['url'])
    return urls

def get_number_of_reqs(data):
    return len(data['log']['entries'])

def get_number_of_reqs_with_cookies(data):
    count = 0
    for entry in data['log']['entries']:
        if entry['request']['cookies'] == []:
            count += 1
    return count

def get_number_of_resp_with_cookes(data):
    count = 0
    for entry in data['log']['entries']:
        if entry['response']['cookies'] == []:
            count += 1
    return count

def get_third_parties(data):
    first_party = 'apotheekenhuid.nl'
    third_parties = set()
    for entry in data['log']['entries']:
        url = entry['request']['url']
        url_domain = get_fld(url)
        if url_domain != first_party:
            third_parties.add(url_domain)
    return third_parties

def parse_set_cookie_header(set_cookie_header):
    cookie = SimpleCookie()
    cookie.load(set_cookie_header)
    return cookie

def is_max_age_60_or_more_days(cookie_parts):
    max_age = None
    for part in cookie_parts:
        if 'Max-Age' in part:
            max_age = part.split('=')[1].strip()
            break
    if max_age is None:
        return False
    if (int(max_age) >= 60*60*24*60):
        return True
    else:
        return False

def is_expire_date_60_or_more_days(cookie_parts):
    expires = None
    for part in cookie_parts:
        if 'expires' in part:
            expires = part.split('=')[1].strip()
            break
    if expires is None:
        return False
    try:
        expires_date = parser.parse(expires)
        current_utc_time = datetime.now(timezone.utc)
        days_until_expires = (expires_date - current_utc_time).days
        if days_until_expires >= 60:
            return True
        else:
            return False
    except ValueError:
        print("Some error with expire date parsing")
        return False 

def get_tracker_cookie_domains(data):
    # Distinct domains, only cookies set by HTTP response header
    # Set-Cookie, samesite = none, expires or max-age for 60 or more days
    # Did not check for partitioned = false

    tracker_cookie_domains = set()
    count = 0
    for entry in data['log']['entries']:
        headers = entry['response']['headers']
        for header in headers:
            if header['name'].lower() == 'set-cookie':
                cookie_parts = header['value'].split(';')
                max_days_bool = is_max_age_60_or_more_days(cookie_parts)
                expire_date_bool = is_expire_date_60_or_more_days(cookie_parts)
                if max_days_bool or expire_date_bool:
                    count += 1
                    url = entry['request']['url']
                    url_domain = get_fld(url)
                    tracker_cookie_domains.add(url_domain)
    return tracker_cookie_domains

def get_third_party_entities(data):
    third_party_domains = get_third_parties(data)
    third_party_entities = set()
    with open('domain_map.json', 'r', encoding='utf-8') as f:
        domain_map = json.load(f)
    
    for domain in third_party_domains:
        if domain in domain_map:
            entity_name = domain_map[domain]["entityName"]
            entity_name = entity_name.replace('\\"', '"')
            third_party_entities.add(entity_name)

    return third_party_entities


def get_request(data):
    request_list = list()
    for entry in data['log']['entries']:
        # building first level key
        requests = {'requests': {}}

        # url_first_128_char
        url = entry['request']['url']
        requests['requests']['url_first_128_char'] = url[:128]

        # url_domain
        domain = get_fld(url)
        requests['requests']['url_domain'] = domain

        # is_third_party
        first_party = 'apotheekenhuid.nl'
        if domain == first_party:
            is_third_party = False
        else:
            is_third_party = True
        requests['requests']['is_third_party'] = is_third_party

        # set_http_cookies
        headers = entry['response']['headers']
        set_http_cookies = False
        for header in headers:
            if header['name'].lower() == 'set-cookie' and header['value']:
                set_http_cookies = True
        requests['requests']['set_http_cookies'] = set_http_cookies

        # entity_name
        with open('domain_map.json', 'r', encoding='utf-8') as f:
            domain_map = json.load(f)

        # This implementation is kinda slow...
        found_entity_name = False
        if domain in domain_map:
            entity_name = domain_map[domain]["entityName"]
            entity_name = entity_name.replace('\\"', '"')
            requests['requests']['entity_name'] = entity_name
        else:
            requests['requests']['entity_name'] = 'unknown'
            
        request_list.append(requests)
    
    return request_list

def generate_json_results(data, path):
    results = {'results': {}}
    results['results']['num_reqs'] = get_number_of_reqs(data)
    results['results']['num_requests_w_cookies'] = get_number_of_reqs_with_cookies(data)
    results['results']['num_responses_w_cookies'] = get_number_of_resp_with_cookes(data)
    results['results']['third_party_domains'] = list(get_third_parties(data))
    results['results']['tracker_cookie_domains'] = list(get_tracker_cookie_domains(data))
    results['results']['third_party_entities'] = list(get_third_party_entities(data))
    results['results']['requests'] = get_request(data)

    with open(path, "w") as json_file:
        json.dump(results, json_file, indent=4)

if __name__ == "__main__":
    data_accept = json.loads(open('apotheekenhuid.nl_accept.har').read())
    data_reject = json.loads(open('apotheekenhuid.nl_reject.har').read())

    print("Starting with generating 'apotheekenhuid.nl_accept.json'")
    # To generate the accept json results
    generate_json_results(data_accept, 'apotheekenhuid.nl_accept.json')
    print("done")
    print("Starting with generating 'apotheekenhuid.nl_reject.json'")
    # To generate the reject json results
    generate_json_results(data_reject, 'apotheekenhuid.nl_reject.json')
    print("done")