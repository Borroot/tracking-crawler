import argparse
from playwright.sync_api import sync_playwright
import re
from tqdm import tqdm
from tld import get_fld
import json

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

def route_intercept(route, request, block_list):
    # print(request)
    request_url = request.url
    for tracker in block_list:
        # print("tracker:", tracker, "\n")
        # print("request url:", request_url, "\n")
        if tracker in request_url:
            print(f"Blocking request to {request_url}")
            return route.abort()
    return route.continue_()


def crawler(playwright, url, debug, block_trackers):
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
    if block_trackers:
        # create block list
        with open("utils/services.json", "r", encoding="utf-8") as f:
            blocklist_data = json.load(f)
        block_list = []
        for category in blocklist_data['categories']['Email']:
            for key, value in category.items():
                if isinstance(value, dict):
                    for inner_key, domain in value.items():
                        if isinstance(domain, list):
                            block_list.extend(domain)
            

        page.route("**/*", lambda route, request: route_intercept(route, request, block_list))


    page.goto(url)
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
    return "TODO"


def main():
    # python crawl.py -u "https://business.gov.nl/" --debug
    # Gather arguments in variables
    block_trackers, url, file_path, debug = parse_arguments()
    urls = []
    # All the url's we will visit
    if file_path is not None:
        urls = read_lines_of_file(file_path)

    if url is not None:
        urls = [url]

    # We want to track a lot of things for our analysis
    # page load times
    page_load_times_allow = []
    page_load_times_block = []

    # number of requests
    number_of_requests_allow = []
    number_of_requests_block = []

    # number of distinct third-party domains
    number_of_third_party_domains_allow = []
    number_of_third_party_domains_block = []

    # number of distinct tracker domains
    number_of_tracker_domains_allow = []
    number_of_tracker_domains_block = []

    # number of distinct third-party domains that set a cookie with SameSite=None and without the Partitioned attribute
    number_of_third_party_domains_set_cookie_allow = []
    number_of_third_party_domains_set_cookie_block = []

    # number of get requests
    number_of_get_requests_allow = []
    number_of_get_requests_block = []

    # number of post requests
    number_of_post_requests_allow = []
    number_of_post_requests_block = []

    # We also want to analyze the Permissions-Policy headers for:
    # disable access to camera for all parties
    disable_camera_allow = []
    disable_camera_block = []

    # disable access to geolocation
    disable_geolocation_allow = []
    disable_geolocation_block = []

    # disable microphone for all parties
    disable_microphone_allow = []
    disable_microphone_block = []

    # We also want to analyze the Referrer-Policy headers for:
    # websites that use no-referrer
    no_referrer_allow = []
    no_referrer_block = []

    # websites that use the unsafe-url
    unsafe_url_allow = []
    unsafe_url_block = []

    # We should also analyze the Accept-CH headers
    # make a list of 3 high-entropy client hints that are requested on most websites:
    
    # TODO: No idea what they exactly want here

    # The three most prevalent distinct cross-domain http redirection pairs.
    # source domain -> target domain -> number of distinct websites
    # TODO: Not sure how to order this


    with sync_playwright() as playwright:
        # Browser part, we should do this for every nl_gov_sites/url there is

        print(url)
        for url_loop in tqdm(urls):
            # Once for accepting cookies
            crawler(playwright, url_loop, debug, False)

            # Once for denying cookies
            crawler(playwright, url_loop, debug, True)

if __name__ == "__main__":
    main()
