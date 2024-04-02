from jq import jq
import json
import publicsuffix2
import urllib
import http.cookies
import email.utils


def load_json_file(json_filename):
    with open(json_filename) as fp:
        data = json.load(fp)
    return data


def jq_one(data, query):
    # retrieve data from the json data using a jq query
    return jq(query).input_value(data).first()


def jq_all(data, query):
    # retrieve data from the json data using a jq query
    return jq(query).input_value(data).all()


def url_to_domain(url):
    # first extract the network location, then the public suffix
    return publicsuffix2.get_sld(urllib.parse.urlparse(url).netloc)


def get_entityname(domain_map, domain):
    # extract the entity name from the domain map for the given domain
    try:
        return domain_map[domain]['entityName']
    except KeyError:
        return f'Unknown ({domain})'


def compute_num_requests(data):
    # compute the total number of requests
    return len(jq_all(data, '.log.entries.[].request'))


def compute_num_w_cookies_request(data):
    # compute the number of request or response entries with cookies
    return len(jq_all(data,
        '.log.entries.[].request.headers | select(.[].name == "cookie")'))


def compute_num_w_cookies_response(data):
    # compute the number of request or response entries with cookies
    return len(jq_all(data,
        '.log.entries.[].response.headers | select(.[].name == "set-cookie")'))


def compute_third_party_domains(data, first_party_domain):
    # compute the list of distinct third party domains (eTLD+1)
    request_urls = jq_all(data, '.log.entries.[].request.url')
    return sorted(filter(lambda domain: domain != first_party_domain, list(set([
        url_to_domain(request_url) for request_url in request_urls
    ]))))


def check_cookie_requirements(cookie, response_date):
    # return whether the given cookie satisfies the samesite=none and >60 days requirement
    # check the samesite requirement for a tracker cookie
    if cookie['samesite'].lower() != 'none':
        return False

    # check max-age > 60 before checking expires as it has precedence
    if len(cookie['max-age']) > 0:
        if int(cookie['max-age']) >= 60 * 3600 * 24:
            return True

    # check expires > 60
    if len(cookie['expires']) > 0:
        expire_date = email.utils.parsedate_to_datetime(cookie['expires'])
        if (expire_date - response_date).total_seconds() >= 60 * 3600 * 24:
            return True

    # if we got here then the cookie expires before 60 days
    return False


def compute_tracker_cookie_domains(data):
    # compute the list of distinct domains that set tracker cookies

    # extract all the responses which set cookies
    responses_with_cookies = jq_all(data,
        '.log.entries.[].response.headers | select(.[].name == "set-cookie")')
    domains = []

    for response_with_cookies in responses_with_cookies:
        # extract the date from the response
        raw_response_date = jq_one(response_with_cookies, '.[] | select(.name == "date") | .value')
        response_date = email.utils.parsedate_to_datetime(raw_response_date)

        # extract the cookies from the response
        raw_cookies = jq_all(response_with_cookies, '.[] | select(.name == "set-cookie") | .value')

        for raw_cookie in raw_cookies:
            # load the raw cookie data into a cookie object
            cookie = http.cookies.BaseCookie()
            cookie.load(raw_cookie)

            try: cookie = cookie[list(cookie.keys())[0]]  # get the morsel object
            except IndexError: continue

            if check_cookie_requirements(cookie, response_date):
                domains.append(publicsuffix2.get_sld(cookie['domain']))

    return list(set(domains))


def compute_third_party_entities(data, domain_map, third_party_domains):
    # use the domain map and third party domains to get the third party entities
    return sorted(list(set(
        get_entityname(domain_map, domain) for domain in third_party_domains
    )))


def compute_requests(data, domain_map, first_party_domain):
    # compute all the requests and responses data
    requests_and_responses = jq_all(data, '.log.entries.[]')
    all_results = []

    for request_and_response in requests_and_responses:
        results = {}

        url = jq_one(request_and_response, '.request.url')
        domain = url_to_domain(url)

        results['url_first_128_char'] = url[:128]
        results['url_domain'] = domain
        results['is_third_party'] = domain != first_party_domain
        results['set_http_cookies'] = len(jq_all(request_and_response,
            '.response.headers.[] | select(.name == "set-cookie")')) > 0
        results['entity_name'] = get_entityname(domain_map, domain)

        all_results.append(results)

    return all_results


def compute_results(data, domain_map, first_party_domain):
    results = {}

    results['num_reqs'] = compute_num_requests(data)
    results['num_requests_w_cookies'] = compute_num_w_cookies_request(data)
    results['num_responses_w_cookies'] = compute_num_w_cookies_response(data)
    results['third_party_domains'] = compute_third_party_domains(data, first_party_domain)
    results['tracker_cookie_domains'] = compute_tracker_cookie_domains(data)
    results['third_party_entities'] = compute_third_party_entities(data, domain_map, results['third_party_domains'])
    results['requests'] = compute_requests(data, domain_map, first_party_domain)

    return results


def write_results(results, results_filename):
    # write the results dictionary to a json file with indentation
    with open(results_filename, 'w') as fp:
        json.dump(results, fp, indent=4)


def main():
    domain_map = load_json_file('domain_map.json')

    first_party_domain = 'bol.com'
    har_filenames = ['bol.com_accept.har', 'bol.com_reject.har']

    for har_filename in har_filenames:
        # load and analyze the har file
        data = load_json_file(har_filename)
        results = compute_results(data, domain_map, first_party_domain)

        # write the results to json
        results_filename = har_filename.rsplit('.', 1)[0] + '.json'
        write_results(results, results_filename)


if __name__ == '__main__':
    main()