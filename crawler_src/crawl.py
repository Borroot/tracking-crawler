from playwright.sync_api import sync_playwright
from tld import get_fld
import tqdm, tqdm.contrib.logging
import argparse
import os
import json
import time
import logging as log
import datetime


class StatisticsCrawler:
    # To keep track of the statistics for the analysis

    def __init__(self):
        self.stats = {
            "consent_click_failure_allow": set(),
            "consent_click_failure_block": set(),

            "page_load_timeout_allow":  set(),
            "page_load_timeout_block":  set(),

            "page_load_times_allow": [],
            "page_load_times_block": [],
        }


    def update_stat_single_set(self, stat_name, block, value):
        self.stats[stat_name + '_' + allow_block(block)].add(value)


    def export_to_json(self):
        def convert_to_serializable(obj):
            if isinstance(obj, set):
                return list(obj)
            return obj

        # timestamp = str(datetime.datetime.now())
        with open(f"../analysis/stats.json", "w") as file:
            json.dump(self.stats, file, indent=4, default=convert_to_serializable)


def parse_arguments():
    # To handle the arguments of running this script
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

    urls = []

    # We will use the file path if it is provided
    if file_path is not None:
        urls = read_lines_of_file(file_path)

    # We will use the url if it is provided, if a file is also provided we just ignore it
    if url is not None:
        urls = [url]

    log.basicConfig(format='%(levelname)s: %(message)s', level=log.DEBUG if debug else log.INFO)
    log.getLogger('asyncio').setLevel(log.WARNING)

    log.debug(f"Urls: {urls}")
    log.debug(f"Block trackers: {block_trackers}")

    return block_trackers, urls, file_path


def read_lines_of_file(file_path):
    lines = []
    with open(file_path, 'r') as file:
        for line in file:
            lines.append(line.strip())
    return lines


def allow_block(block):
    return 'block' if block else 'allow'


def accept_cookie(page, stats_crawler, url, block_trackers):
    # To find the accept button on the page using a file, and attempt to click it

    accept_words = []
    with open("../utils/accept_words.txt", 'r', encoding="utf-8") as file:
        for line in file:
            accept_words.append(line.strip())

    found_accept_button_or_link = False
    for word in accept_words:
        # Check for button with text containing the accept word
        accept_button = page.query_selector(f'button:has-text("{word}")')
        if accept_button:
            found_accept_button_or_link = True
            log.debug(f"Found button with word: {word}")
            accept_button.click()
            break

        # Some cookie accept buttons are not actual buttons but just links...
        # However sometimes on website links exist that contain some word of our accept_words list

        # Check for link with text containing the accept word
        # accept_link = page.query_selector(f'a:has-text("{word}")')
        # if accept_link:
        #     found_accept_button_or_link = True
        #     log.debug(f"Found link with word: {word}")
        #     accept_link.click()
        #     break

    if not found_accept_button_or_link:
        log.debug("Failed to find accept button or link")
        domain_of_url = get_fld(url)
        stats_crawler.update_stat_single_set("consent_click_failure", block_trackers, domain_of_url)

    return page


def scroll_to_bottom_in_multiple_steps(page):
    # Scroll to the bottom based on the max_height, not every website shows the full height, so scroll a little more
    max_height = page.evaluate("document.body.scrollHeight")
    scroll_step = 200
    scroll_position = 0
    while scroll_position < max_height:
        page.evaluate(f"window.scrollBy(0, {scroll_step})")
        scroll_position += scroll_step
        page.wait_for_timeout(100)
    page.evaluate(f"window.scrollBy(0, {scroll_step*20})")
    return page


def block_tracker_requests(route, request, block_list):
    # Using to handle the requests
    domain_of_request_url = get_fld(request.url)

    # Checking whether the request is in the block list
    if domain_of_request_url in block_list:
        log.debug(f"Blocking request to {domain_of_request_url}")
        return route.abort()
    return route.continue_()


def load_block_list():
    with open("../utils/services.json", "r", encoding="utf-8") as f:
        blocklist_data = json.load(f)

    block_list = []

    for category_name, category_data in blocklist_data['categories'].items():
        for entry in category_data:
            for _company_name, domains in entry.items():
                for _domain, block_domains in domains.items():
                    if isinstance(block_domains, list):
                        block_list.extend(block_domains)

    return list(set(block_list))


def crawler(playwright, url, block_trackers, stats_crawler, url_index):
    browser = playwright.chromium.launch(headless=True, slow_mo=50)
    context = browser.new_context()
    url_domain = get_fld(url)

    variant = allow_block(block_trackers)
    record_video_dir = f"../crawl_data_{variant}/"
    har_file_path = f"../crawl_data_{variant}/{url_domain}_{variant}.har"

    context = browser.new_context(
        record_video_dir=record_video_dir,
        record_video_size={"width": 640, "height": 480},
        record_har_path=har_file_path
    )
    page = context.new_page()

    # If block_trackers is True, then we block the tracker requests here
    block_list = load_block_list()
    if block_trackers:
        page.route("**/*", lambda route, request: block_tracker_requests(route, request, block_list))

    # Start tracking time so we can use it for load times
    log.debug('Loading the page')
    start_time = time.time()
    page.goto(url)

    page.wait_for_load_state('load')
    end_time = time.time()
    page_load_time = end_time - start_time

    stats_crawler.stats['page_load_times_' + allow_block(block_trackers)].append({
        'url': url, 'page_load_time': page_load_time})

    # Wait 10s
    page.wait_for_timeout(10000) # Change to 10s later

    # Screenshot of the page before accepting cookies
    page.screenshot(path=f"../crawl_data_{variant}/{url_domain}_{variant}_pre_consent.png")

    # Accept all cookies
    log.debug('Trying to accept cookies')
    try:
        page = accept_cookie(page, stats_crawler, url, block_trackers)
    except:
        stats_crawler.update_stat_single_set("page_load_timeout", block_trackers, url_domain)

    # We need the cookies one day probably
    cookies = context.cookies()

    # Screenshot of the page after accepting cookies
    page.screenshot(path=f"../crawl_data_{variant}/{url_domain}_{variant}_post_consent.png")

    # wait 3s
    page.wait_for_timeout(3000)

    # Scroll all the way down, in multiple steps
    log.debug('Scrolling down the page')
    page = scroll_to_bottom_in_multiple_steps(page)

    # wait 3s
    page.wait_for_timeout(3000)

    # Saving the video
    video_path = page.video.path()

    context.close()
    browser.close()

    new_video_path = os.path.dirname(video_path) + f"/{url_domain}_{variant}.webm"
    os.replace(video_path, new_video_path)


def run_crawler(playwright, url, block_trackers, stats_crawler, url_index, num_urls):
    log.debug(f'{url_index + 1}/{num_urls} Running crawler on {url} with {allow_block(block_trackers)}')
    try:
        crawler(playwright, url, block_trackers, stats_crawler, url_index)
    except Exception as e:
        print("Failed to crawl page:", url)
        print("Error:", e)


def main():
    # python crawl.py -u "https://business.gov.nl/" --debug --block-trackers
    # python crawl.py -l "../utils/nl-gov-sites.txt" --debug --block-trackers

    # Gather arguments in variables
    block_trackers, urls, file_path = parse_arguments()

    # Create a statistics crawler
    stats_crawler = StatisticsCrawler()

    with sync_playwright() as playwright:
        with tqdm.contrib.logging.logging_redirect_tqdm():
            # Two crawlers for every url, one with blocking trackers and one without
            for url_index, url in tqdm.tqdm(enumerate(urls), total=len(urls)):
            # for url_index, url in enumerate(urls):

                # Once for allowing trackers
                run_crawler(playwright, url, False, stats_crawler, url_index, len(urls))

                # Once for blocking trackers
                if block_trackers:
                    run_crawler(playwright, url, True, stats_crawler, url_index, len(urls))

    # Getting some statistics that cannot be retrieved from the har files
    stats_crawler.export_to_json()


if __name__ == "__main__":
    main()

