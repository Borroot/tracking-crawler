import argparse
from playwright.sync_api import sync_playwright
from tqdm import tqdm
from tld import get_fld
import json
import time
import os



# To keep track of the statistics for the analysis
class StatisticsCrawler:
    def __init__(self, amount_of_urls):
        self.stats = {
            "time_out":  set(),
            "failed_to_find_accept": set(),

            "page_load_times_allow": [[] for _ in range(amount_of_urls)],
            "page_load_times_block": [[] for _ in range(amount_of_urls)]
        }

    def update_stat_single_set(self, stat_name, value):
        self.stats[stat_name].add(value)

    def update_stat(self, stat_name, block, value, url_index):
        if block:
            self.stats[stat_name + "_block"][url_index].append(value)
        else:
            self.stats[stat_name + "_allow"][url_index].append(value)

    def get_stats(self):
        return self.stats

    def export_to_json(self):
        def convert_to_serializable(obj):
            if isinstance(obj, set):
                return list(obj)
            return obj

        with open("../analysis/stats.json", "w") as file:
            json.dump(self.stats, file, indent=4, default=convert_to_serializable)

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
def accept_cookie(page, debug, stats_crawler, url):
    accept_words = []
    found_accept_button_or_link = False
    with open("../utils/accept_words.txt", 'r', encoding="utf-8") as file:
        for line in file:
            accept_words.append(line.strip())

    for word in accept_words:
        # Check for button with text containing the accept word
        accept_button = page.query_selector(f'button:has-text("{word}")')
        if accept_button:
            found_accept_button_or_link = True
            if debug:
                print("\nfound button with word:", word)
            accept_button.click()
            break
        
        # Some cookie accept buttons are not actual buttons but just links...
        # However sometimes on website links exist that contain some word of our accept_words list

        # Check for link with text containing the accept word
        # accept_link = page.query_selector(f'a:has-text("{word}")')
        # if accept_link:
        #     found_accept_button_or_link = True
        #     if debug:
        #         print("found link with word:", word)
        #     accept_link.click()
        #     break
    if found_accept_button_or_link == False:
        domain_of_url = get_fld(url)
        stats_crawler.update_stat_single_set("failed_to_find_accept", domain_of_url)
    return page

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

def crawler(playwright, url, debug, block_trackers, stats_crawler, url_index):
    browser = playwright.chromium.launch(headless=False, slow_mo=50) # Can do headless=False/True
    context = browser.new_context()
    url_domain = get_fld(url)
    if block_trackers:
        record_video_dir = "../crawl_data_block/"
        har_file_path = "../crawl_data_block/" + url_domain+"_block.har"
    else:
        record_video_dir = "../crawl_data_allow/"
        har_file_path = "../crawl_data_allow/" + url_domain+"_allow.har"
    context = browser.new_context(
    record_video_dir=record_video_dir,
    record_video_size={"width": 640, "height": 480},
    record_har_path=har_file_path
    )
    page = context.new_page()

    # If block_trackers is True, then we block the tracker requests here.
    block_list = []
    with open("../utils/services.json", "r", encoding="utf-8") as f:
        blocklist_data = json.load(f)
    for category in blocklist_data['categories']['Email']:
        for key, value in category.items():
            if isinstance(value, dict):
                for inner_key, domain in value.items():
                    if isinstance(domain, list):
                        block_list.extend(domain)
    
    if block_trackers:
        page.route("**/*", lambda route, request: block_tracker_requests(route, request, block_list, debug))

    # Start tracking time so we can use it for load times
    start_time = time.time()
    page.goto(url)

    page.wait_for_load_state('load')
    end_time = time.time()
    page_load_time = end_time - start_time
    stats_crawler.update_stat("page_load_times", block_trackers, page_load_time, url_index)

    # Wait 10s
    page.wait_for_timeout(3000) # Change to 10s later

    # Screenshot of the page before accepting cookies
    if block_trackers:
        page.screenshot(path="../crawl_data_block/"+url_domain+"_block_pre_consent.png")
    else:
        page.screenshot(path="../crawl_data_allow/"+url_domain+"_allow_pre_consent.png")

    # Accept all cookies
    try:
        page = accept_cookie(page, debug, stats_crawler, url)
    except:
        stats_crawler.update_stat_single_set("time_out", url_domain)

    # We need the cookies one day probably
    cookies = context.cookies()

    # Screenshot of the page after accepting cookies
    if block_trackers:
        page.screenshot(path="../crawl_data_block/"+url_domain+"_block_post_consent.png")
    else:
        page.screenshot(path="../crawl_data_allow/"+url_domain+"_allow_post_consent.png")

    # wait 3s
    page.wait_for_timeout(3000)

    # Scroll all the way down, in multiple steps
    page = scroll_to_bottom_in_multiple_steps(page)

    # wait 3s
    page.wait_for_timeout(3000)

    video_path = page.video.path()


    context.close()
    browser.close()
    if block_trackers:
        new_video_path = os.path.dirname(video_path) + "\\" + url_domain +"_block.webm"
    else:
        new_video_path = os.path.dirname(video_path) + "\\" + url_domain +"_allow.webm"
    os.rename(video_path, new_video_path)
    return


def main():
    # python crawl.py -u "https://business.gov.nl/" --debug --block-trackers
    # python crawl.py -l utils/2-websites.txt --debug --block-trackers
    # python crawl.py -l "utils/nl-gov-sites.txt" --debug --block-trackers
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
            # Once for allowing trackers
            try:
                crawler(playwright, url_loop, debug, False, stats_crawler, url_index)
            except:
                print("failed to crawl page:", url_loop)

            # Once for blocking trackers
            if block_trackers:
                try:
                    crawler(playwright, url_loop, debug, True, stats_crawler, url_index)
                except:
                    print("failed to crawl page:", url_loop)
        

    # Getting some statistics that cannot be retrieved from the har files
    stats = stats_crawler.get_stats()
    print("load times:", stats["page_load_times_allow"])
    print("failed_to_find_accept", list(stats["failed_to_find_accept"]))
    print("time_out", list(stats["time_out"]))
    stats_crawler.export_to_json()

if __name__ == "__main__":
    main()
