import argparse
from playwright.sync_api import sync_playwright
import re
from tqdm import tqdm
from tld import get_fld
import json
import time
import numpy as np

class StatisticsCrawler:
    def __init__(self):
        self.stats = {
            # page load times
            "page_load_times_allow": [],
            "page_load_times_block": [],

            # number of requests
            "number_of_requests_allow": [],
            "number_of_requests_block": [],

            # number of distinct third-party domains
            "number_of_third_party_domains_allow": [],
            "number_of_third_party_domains_block": [],

            # number of distinct tracker domains
            "number_of_tracker_domains_allow": [],
            "number_of_tracker_domains_block": [],
            
            # number of distinct third-party domains that set a cookie with SameSite=None and without the Partitioned attribute
            "number_of_third_party_domains_set_cookie_allow": [],
            "number_of_third_party_domains_set_cookie_block": [],

            # number of get requests
            "number_of_get_requests_allow": [],
            "number_of_get_requests_block": [],

            # number of post requests
            "number_of_post_requests_allow": [],
            "number_of_post_requests_block": [],

            # We also want to analyze the Permissions-Policy headers for:
            # disable access to camera for all parties
            "disable_camera_allow": [],
            "disable_camera_block": [],

            # disable access to geolocation
            "disable_geolocation_allow": [],
            "disable_geolocation_block": [],

            # disable microphone for all parties
            "disable_microphone_allow": [],
            "disable_microphone_block": [],

            # We also want to analyze the Referrer-Policy headers for:
            # websites that use no-referrer
            "no_referrer_allow": [],
            "no_referrer_block": [],

            # websites that use the unsafe-url
            "unsafe_url_allow": [],
            "unsafe_url_block": []

            # We should also analyze the Accept-CH headers
            # make a list of 3 high-entropy client hints that are requested on most websites:
            
            # TODO: No idea what they exactly want here

            # The three most prevalent distinct cross-domain http redirection pairs.
            # source domain -> target domain -> number of distinct websites
            # TODO: Not sure how to order this
        }


    def update_stat(self, stat_name, block, value):
        if block:
            self.stats[stat_name + "_block"].append(value)
        else:
            self.stats[stat_name + "_allow"].append(value)


    def get_stats(self):
        return self.stats

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

def accept_cookie(page):
    accept_words = []
    found_accept_button = False
    with open("utils/accept_words.txt", 'r', encoding="utf-8") as file:
        for line in file:
            accept_words.append(line.strip())

    for word in accept_words:
        accept_button = page.query_selector(f'button:has-text("{word}")')
        if accept_button:
            accept_button.click()
            found_accept_button = True
            break

    return page, found_accept_button

def scroll_to_bottom_in_multiple_steps(page):
    max_height = page.evaluate("document.body.scrollHeight")
    scroll_step = 200
    scroll_position = 0
    while scroll_position < max_height:
        page.evaluate(f"window.scrollBy(0, {scroll_step})")
        scroll_position += scroll_step
    return page

def route_intercept(route, request, block_list, debug, stats_crawler, block_trackers):
    # We will update the amount of requests here
    stats_crawler.update_stat("number_of_requests", block_trackers, 1)

    # Checking whether the request is in the block list
    request_url = request.url
    for tracker in block_list:
        if tracker in request_url:
            if debug:
                domain_blocked_request = get_fld(request_url)
                print(f"Blocking request to {domain_blocked_request}")
            return route.abort()
    return route.continue_()


def crawler(playwright, url, debug, block_trackers, stats_crawler):
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
    if block_trackers:
        # create block list
        with open("utils/services.json", "r", encoding="utf-8") as f:
            blocklist_data = json.load(f)
        for category in blocklist_data['categories']['Email']:
            for key, value in category.items():
                if isinstance(value, dict):
                    for inner_key, domain in value.items():
                        if isinstance(domain, list):
                            block_list.extend(domain)
            

    page.route("**/*", lambda route, request: route_intercept(route, request, block_list, debug, stats_crawler, block_trackers))



    # Start tracking time so we can use it for load times
    start_time = time.time()
    page.goto(url)

    page.wait_for_load_state('load')
    end_time = time.time()
    page_load_time = end_time - start_time
    stats_crawler.update_stat("page_load_times", block_trackers, page_load_time)

    # Wait 10s
    if debug:
        print("Waiting for 10 seconds")
    page.wait_for_timeout(3000) # Change to 10s later

    # Screenshot of the page before accepting cookies
    page.screenshot(path="screenshots/"+url_domain+"/before_accept.png")

    # Accept all cookies
    if debug:
        print("Accepting all cookies")
    page, found_accept_button = accept_cookie(page)

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
    # python crawl.py -l "/utils/nl-gov-sites.txt" --debug
    # Gather arguments in variables
    block_trackers, url, file_path, debug = parse_arguments()
    urls = []

    # We will use the file path if it is provided
    if file_path is not None:
        urls = read_lines_of_file(file_path)

    # We will use the url if it is provided, if a file is also provided we just ignore it
    if url is not None:
        urls = [url]

    # Create a statistics crawler
    stats_crawler = StatisticsCrawler()

    with sync_playwright() as playwright:
        # Two crawlers for every url, one with blocking trackers and one without
        if debug:
            print("visiting: ", url, " with and without blocking trackers")
        for url_loop in tqdm(urls):
            # Once for allowing trackers
            crawler(playwright, url_loop, debug, False, stats_crawler)

            # Once for blocking trackers
            crawler(playwright, url_loop, debug, True, stats_crawler)
        
    # Getting all of the statistics we will use for the analysis
    stats = stats_crawler.get_stats()
    print("reload times average:", np.mean(stats["page_load_times_allow"]))
    print("number of requests in allow:", len(stats["number_of_requests_allow"]))
    print("number of third-party domains (not distinct yet):", len(stats["number_of_third_party_domains_allow"]))
    print("number of tracker domains (not distinct yet):", len(stats["number_of_tracker_domains_allow"]))
    print("number of third-party domains (not distinct yet) that set a cookie with SameSite=None and without the Partitioned attribute:", len(stats["number_of_third_party_domains_set_cookie_allow"]))
if __name__ == "__main__":
    main()
