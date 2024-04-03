import argparse
from playwright.sync_api import sync_playwright
import re
from tqdm import tqdm
from tld import get_fld
import json
import time
import numpy as np


# To keep track of the statistics for the analysis
class StatisticsCrawler:
    def __init__(self, amount_of_urls):
        self.stats = {
            # page load times
            "page_load_times_allow": [[] for _ in range(amount_of_urls)],
            "page_load_times_block": [[] for _ in range(amount_of_urls)],

            # number of requests
            "number_of_requests_allow": [0 for _ in range(amount_of_urls)],
            "number_of_requests_block": [0 for _ in range(amount_of_urls)],

            # third-party domains
            "third_party_domains_allow": [[] for _ in range(amount_of_urls)],
            "third_party_domains_block": [[] for _ in range(amount_of_urls)],

            # tracker domains
            "tracker_domains_allow": [[] for _ in range(amount_of_urls)],
            "tracker_domains_block": [[] for _ in range(amount_of_urls)],
            
            # third-party domains that set a cookie with SameSite=None and
            # without the Partitioned attribute
            "third_party_domains_set_cookie_allow": [[] for _ in range(amount_of_urls)],
            "third_party_domains_set_cookie_block": [[] for _ in range(amount_of_urls)],

            # number of get requests
            "number_of_get_requests_allow": [0 for _ in range(amount_of_urls)],
            "number_of_get_requests_block": [0 for _ in range(amount_of_urls)],

            # number of post requests
            "number_of_post_requests_allow": [0 for _ in range(amount_of_urls)],
            "number_of_post_requests_block": [0 for _ in range(amount_of_urls)],

            # Permissions-Policy headers
            # disable access to camera for all parties
            "disable_camera_allow": [[] for _ in range(amount_of_urls)],
            "disable_camera_block": [[] for _ in range(amount_of_urls)],

            # disable access to geolocation
            "disable_geolocation_allow": [[] for _ in range(amount_of_urls)],
            "disable_geolocation_block": [[] for _ in range(amount_of_urls)],

            # disable microphone for all parties
            "disable_microphone_allow": [[] for _ in range(amount_of_urls)],
            "disable_microphone_block": [[] for _ in range(amount_of_urls)],

            # Referrer-Policy headers
            # websites that use no-referrer
            "no_referrer_allow": [[] for _ in range(amount_of_urls)],
            "no_referrer_block": [[] for _ in range(amount_of_urls)],

            # websites that use the unsafe-url
            "unsafe_url_allow": [[] for _ in range(amount_of_urls)],
            "unsafe_url_block": [[] for _ in range(amount_of_urls)]

            # We should also analyze the Accept-CH headers
            # make a list of 3 high-entropy client hints that are requested on most websites:
            
            # TODO: No idea what they exactly want here

            # The three most prevalent distinct cross-domain http redirection pairs.
            # source domain -> target domain -> number of distinct websites
            # TODO: Not sure how to order this
        }


    def update_stat(self, stat_name, block, value, url_index):
        if block:
            self.stats[stat_name + "_block"][url_index].append(value)
        else:
            self.stats[stat_name + "_allow"][url_index].append(value)

    def update_stat_counter(self, stat_name, block, value, url_index):
        if block:
            self.stats[stat_name + "_block"][url_index] += value
        else:
            self.stats[stat_name + "_allow"][url_index] += value

    def get_stats(self):
        return self.stats

# To handle the arguments of running this script
def parse_arguments():
    parser = argparse.ArgumentParser(description='Crawler with options')
    parser.add_argument('--block-trackers', action='store_true', help='Block trackers if provided')
    parser.add_argument('-u', metavar='URL', help='Single URL to crawl')
    parser.add_argument('-l', metavar='FILE', help='File containing list of URLs to crawl')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()
    block_trackers = args.block_trackers
    url = args.u
    file_path = args.l
    debug = args.debug

    if debug:
        print("Block Trackers:", block_trackers)
        print("URL:", url)
        print("File Path:", file_path)
        print("Debug Mode:", debug)

    return block_trackers, url, file_path, debug

def read_lines_of_file(file_path):
    lines = []
    with open(file_path, 'r') as file:
        for line in file:
            lines.append(line.strip())
    return lines

# To find the accept button on the page using a file, and attempt to click it
def accept_cookie(page, debug):
    accept_words = []
    found_accept_button = False
    with open("utils/accept_words.txt", 'r', encoding="utf-8") as file:
        for line in file:
            accept_words.append(line.strip())

    for word in accept_words:
        # Check for button with text containing the accept word
        accept_button = page.query_selector(f'button:has-text("{word}")')
        if accept_button:
            if debug:
                print("found button with word:", word)
            accept_button.click()
            found_accept_button = True
            break
        
        # Some cookie accept buttons are not actual buttons but just links...abs
        # However sometimes on websites links exist that contain some word of our accept_words list

        # Check for link with text containing the accept word
        accept_link = page.query_selector(f'a:has-text("{word}")')
        if accept_link:
            if debug:
                print("found link with word:", word)
            accept_link.click()
            found_accept_button = True
            break

    return page, found_accept_button

# Scroll to the bottom based on the max_height, not every website shows the full height, so scroll a little more
def scroll_to_bottom_in_multiple_steps(page):
    max_height = page.evaluate("document.body.scrollHeight")
    scroll_step = 200
    scroll_position = 0
    while scroll_position < max_height:
        page.evaluate(f"window.scrollBy(0, {scroll_step})")
        scroll_position += scroll_step
        page.wait_for_timeout(100)
    page.evaluate(f"window.scrollBy(0, {scroll_step*20})")
    return page

# Using to handle the requests
def block_tracker_requests(route, request, block_list, debug):
    domain_of_request_url = get_fld(request.url)
    # Checking whether the request is in the block list

    if domain_of_request_url in block_list:
        if debug:
            print(f"Blocking request to {domain_of_request_url}")
        return route.abort()
    return route.continue_()

def response_inspect(response, block_list, debug, stats_crawler, block_trackers, url_index, first_party_url):
    response_url = response.url
    domain_of_response_url = get_fld(response_url)
    first_party_domain = get_fld(first_party_url)
    
    headers = response.headers
    cookie_set = False
    partitioned_set = True
    # We want to find all the third-party domains that set a cookie with SameSite=None and without the Partitioned attribute
    for header_name, header_value in headers.items():
        if header_name == "Set-Cookie":
            cookie_set = True
        if "Partitioned" in header_name:
            partitioned_set = False
    
    if (cookie_set == True) and (partitioned_set == False):
        stats_crawler.update_stat("third_party_domains_set_cookie", block_trackers, domain_of_response_url, url_index)
            
def request_inspect(request, block_list, debug, stats_crawler, block_trackers, url_index, first_party_url):
    request_url = request.url
    domain_of_request_url = get_fld(request_url)    
    first_party_domain = get_fld(first_party_url)

    
    # We will update the amount of requests here
    stats_crawler.update_stat_counter("number_of_requests", block_trackers, 1, url_index)

    # We want to find all the third-party domains. It will be a list of all the third-party domains per url (not distinct yet)
    is_third_party = False
    if domain_of_request_url != first_party_domain:
        is_third_party = True
        if is_third_party:
            stats_crawler.update_stat("third_party_domains", block_trackers, domain_of_request_url, url_index)

    # We want to find all the tracker domains. It will be a list of all the distinct domains per url
    if domain_of_request_url in block_list:
        stats_crawler.update_stat("tracker_domains", block_trackers, domain_of_request_url, url_index)
        
    # We want to update the number of get requests
    if request.method == 'GET':
        stats_crawler.update_stat_counter("number_of_get_requests", block_trackers, 1, url_index)

    # We want to update the number of post requests
    if request.method == 'POST':
        stats_crawler.update_stat_counter("number_of_post_requests", block_trackers, 1, url_index)


    # Permissions-Policy headers, Refer policy, accept-ch not sure where that needs to be tracked, didnt look yet


def crawler(playwright, url, debug, block_trackers, stats_crawler, url_index):
    browser = playwright.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context()
    url_domain = get_fld(url)
    if block_trackers:
        record_video_dir = "videos/"+url_domain+"/deny/"
        har_file_path = "har_files/" + url_domain+"/deny.har"
    else:
        record_video_dir = "videos/"+url_domain+"/accept/"
        har_file_path = "har_files/" + url_domain+"/accept.har"
    context = browser.new_context(
    record_video_dir=record_video_dir,
    record_video_size={"width": 640, "height": 480},
    record_har_path=har_file_path
    )
    page = context.new_page()
    # Somehow we have to save all the network traffic as HAR file. The assignment says use internal HAR recording feature of playwright, I cannot find it


    # If block_trackers is True, then we block the tracker requests here.
    block_list = []
    with open("utils/services.json", "r", encoding="utf-8") as f:
        blocklist_data = json.load(f)
    for category in blocklist_data['categories']['Email']:
        for key, value in category.items():
            if isinstance(value, dict):
                for inner_key, domain in value.items():
                    if isinstance(domain, list):
                        block_list.extend(domain)
            
    if block_trackers:
        page.route("**/*", lambda route, request: block_tracker_requests(route, request, block_list, debug))
    page.on("request", lambda request: request_inspect(request, block_list, debug, stats_crawler, block_trackers, url_index, url) if request.url.startswith("http://") or request.url.startswith("https://") else None)
    page.on("response", lambda response: response_inspect(response, block_list, debug, stats_crawler, block_trackers, url_index, url) if response.url.startswith("http://") or response.url.startswith("https://") else None)

    # Start tracking time so we can use it for load times
    start_time = time.time()
    page.goto(url)

    page.wait_for_load_state('load')
    end_time = time.time()
    page_load_time = end_time - start_time
    stats_crawler.update_stat("page_load_times", block_trackers, page_load_time, url_index)

    # Wait 10s
    if debug:
        print("Waiting for 10 seconds")
    page.wait_for_timeout(3000) # Change to 10s later

    # Screenshot of the page before accepting cookies
    page.screenshot(path="screenshots/"+url_domain+"/before_accept.png")

    # Accept all cookies
    if debug:
        print("Finding accept cookies button")
    try:
        page, found_accept_button = accept_cookie(page, debug)
    except:
        print("could not find accept button")

    # We need the cookies one day probably
    cookies = context.cookies()

    # Screenshot of the page after accepting cookies
    page.screenshot(path="screenshots/"+url_domain+"/after_accept.png")

    # wait 3s
    if debug:
        print("Waiting for 3 seconds")
    page.wait_for_timeout(3000)

    # Scroll all the way down, in multiple steps
    if debug:
        print("Scrolling all the way down")
    page = scroll_to_bottom_in_multiple_steps(page)

    # wait 3s
    if debug:
        print("Waiting for 3 seconds")
    page.wait_for_timeout(3000)


    # Close the page
    context.close()
    browser.close()
    return


def main():
    # python crawl.py -u "https://business.gov.nl/" --debug
    # python crawl.py -l "utils/nl-gov-sites.txt" --debug
    # Gather arguments in variables
    block_trackers, url, file_path, debug = parse_arguments()
    urls = []

    # We will use the file path if it is provided
    if file_path is not None:
        urls = read_lines_of_file(file_path)

    # We will use the url if it is provided, if a file is also provided we just ignore it
    if url is not None:
        urls = [url]

    number_of_urls = len(urls)

    # Create a statistics crawler
    stats_crawler = StatisticsCrawler(number_of_urls)

    with sync_playwright() as playwright:
        # Two crawlers for every url, one with blocking trackers and one without

        for url_index, url_loop in tqdm(enumerate(urls), total=number_of_urls):
            if debug:
                print("visiting: ", url_loop, " with and without blocking trackers")
            # Once for allowing trackers
            crawler(playwright, url_loop, debug, False, stats_crawler, url_index)

            # Once for blocking trackers
            if block_trackers:
                crawler(playwright, url_loop, debug, True, stats_crawler, url_index)
        
    # Getting all of the statistics we will use for the analysis
    stats = stats_crawler.get_stats()

    # Getting the distinct domains
    for url in range(number_of_urls):
        stats["third_party_domains_allow"][url] = list(np.unique(stats["third_party_domains_allow"][url]))
        stats["third_party_domains_block"][url] = list(np.unique(stats["third_party_domains_block"][url]))
        stats["tracker_domains_allow"][url] = list(np.unique(stats["tracker_domains_allow"][url]))
        stats["tracker_domains_block"][url] = list(np.unique(stats["tracker_domains_block"][url]))
        stats["third_party_domains_set_cookie_allow"][url] = list(np.unique(stats["third_party_domains_set_cookie_allow"][url]))
        stats["third_party_domains_set_cookie_block"][url] = list(np.unique(stats["third_party_domains_set_cookie_block"][url]))


    print("reload times:", stats["page_load_times_allow"])
    print("number of requests in allow:", stats["number_of_requests_allow"])
    print("third_party_domains_allow", stats["third_party_domains_allow"])
    print("tracker_domains_allow", stats["tracker_domains_allow"])
    print("third_party_domains_set_cookie_allow", stats["third_party_domains_set_cookie_allow"])
    print("number_of_get_requests_allow", stats["number_of_get_requests_allow"])
    print("number_of_post_requests_allow", stats["number_of_post_requests_allow"])


if __name__ == "__main__":
    main()
