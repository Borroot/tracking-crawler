import argparse
from playwright.sync_api import sync_playwright
import re

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


def deny_cookies(playwright, url): 
    browser = playwright.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context()
    sanitized_url = sanitize_url(url)
    record_video_dir = "videos/"+sanitized_url+"/deny/"
    context = browser.new_context(
    record_video_dir=record_video_dir,
    record_video_size={"width": 640, "height": 480}
    )
    page = context.new_page()
    
    page.goto(url)
    # Wait 10s

    # Accept all cookies, but block the trackers from the services.json list

    # wait 3s

    # Scroll all the way down, in multiple steps

    # wait 3s

    # Close the page

    context.close()
    
    browser.close()
    return "TODO"


def accept_cookies(playwright, url):
    browser = playwright.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context()
    sanitized_url = sanitize_url(url)
    record_video_dir = "videos/"+sanitized_url+"/accept/"
    context = browser.new_context(
    record_video_dir=record_video_dir,
    record_video_size={"width": 640, "height": 480}
    )
    page = context.new_page()
    
    page.goto(url)
    # Wait 10s

    # Accept the cookies by clicking

    # wait 3s

    # Scroll all the way down, in multiple steps

    # wait 3s

    # Close the page
    return "TODO"


def main():
    # Gather arguments in variables
    block_trackers, url, file_path, debug = parse_arguments()

    # All the url's we will visit
    nl_gov_sites = read_lines_of_file("utils/nl-gov-sites.txt")


    with sync_playwright() as playwright:
        # Browser part, we should do this for every nl_gov_sites/url there is

        # Maybe random user agent? Maybe need the same one for accepting/denying because the website may act differently on the user-agent

        # To debug and just use 1 website
        nl_gov_sites = ["https://playwright.dev"]
        print(url)
        for url in nl_gov_sites:
            # Once for denying cookies
            deny_cookies(playwright, url)

            # Once for accepting cookies
            accept_cookies(playwright, url)



if __name__ == "__main__":
    main()
