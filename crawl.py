import argparse
from playwright.sync_api import sync_playwright
import re
from tqdm import tqdm

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

def sanitize_url(url):
    """Sanitize the URL to make it a valid directory name."""
    return re.sub(r"[^\w\s-]", '', url.replace("http://", "").replace("https://", "").replace("www.", "")).strip().replace("/", "_")

def read_lines_of_file(file_path):
    lines = []
    with open(file_path, 'r') as file:
        for line in file:
            lines.append(line.strip())
    return lines

def accept_cookie(page):
    accept_words = []
    
    with open("utils/accept_words.txt", 'r', encoding="utf-8") as file:
        for line in file:
            accept_words.append(line.strip())

    for word in accept_words:
        accept_button = page.query_selector(f'button:has-text("{word}")')
        if accept_button:
            accept_button.click()
            break

    return page


def crawler(playwright, url, debug, block_trackers):
    browser = playwright.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context()
    sanitized_url = sanitize_url(url)
    if block_trackers:
        record_video_dir = "videos/"+sanitized_url+"/deny/"
    else:
        record_video_dir = "videos/"+sanitized_url+"/accept/"
    context = browser.new_context(
    record_video_dir=record_video_dir,
    record_video_size={"width": 640, "height": 480}
    )
    page = context.new_page()
    
    page.goto(url)
    # Wait 10s
    if debug:
        print("Waiting for 10 seconds")
    page.wait_for_timeout(3000) # Change to 10s later

    # Accept all cookies
    if debug:
        print("Accepting all cookies")
        # TODO: Implement this
    page = accept_cookie(page)

    # If block_trackers is True, then we block the tracker requests here.
    cookies = context.cookies()

    # wait 3s
    if debug:
        print("Waiting for 3 seconds")
    page.wait_for_timeout(3000)

    # Scroll all the way down, in multiple steps
    if debug:
        print("Scrolling all the way down")
        # TODO: Implement this

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
