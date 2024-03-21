import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Crawler with options')
    parser.add_argument('--block-trackers', action='store_true', help='Block trackers if provided')
    parser.add_argument('-u', metavar='URL', help='Single URL to crawl')
    parser.add_argument('-l', metavar='FILE', help='File containing list of URLs to crawl')

    return parser.parse_args()

def main():
    args = parse_arguments()
    
    # Gather the options in a variable
    block_trackers = args.block_trackers
    url = args.u
    file_path = args.l

    # Now you can use these variables in your crawler code
    
    print("Block Trackers:", block_trackers)
    print("URL:", url)
    print("File Path:", file_path)

if __name__ == "__main__":
    main()
