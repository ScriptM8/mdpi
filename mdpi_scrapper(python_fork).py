import requests
from bs4 import BeautifulSoup
import time
import json
import signal

journal = "sustainability"
country = "INDIA"
file_name = f"mdpi_{journal}_{country}_articles.json"


def signal_handler(signum, frame):
    print("Script interrupted. Saving current data to file.")
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)
    exit()


# Setup signal handler for keyboard interrupt (Ctrl+C)
signal.signal(signal.SIGINT, signal_handler)


def get_editors(article_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    response = requests.get(article_url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to retrieve article page. Status code: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    editors_div = soup.find('div', id='academic_editors')
    if not editors_div:
        return []

    editors = []
    for editor_container in editors_div.find_all('div', class_='academic-editor-container'):
        editor_name = editor_container.find('span', class_='sciprofiles-link__name')
        if editor_name:
            editors.append(editor_name.text.strip())

    return editors


def scrape_mdpi_articles(url, num_pages):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    global all_articles  # Make it global to access in the signal handler
    all_articles = []
    for page_no in range(1, num_pages + 1):  # Loop through the number of pages
        page_url = f"{url}&page_no={page_no}" if page_no > 1 else url  # Add page_no parameter for pages after first

        response = requests.get(page_url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to retrieve page {page_no}. Status code: {response.status_code}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = soup.find_all('div', class_='generic-item article-item')

        for article in articles:
            article_data = {}

            # Title and Link
            title_link = article.find('a', class_='title-link')
            if title_link:
                article_data['title'] = title_link.text.strip()
                article_data['link'] = title_link['href']
            else:
                article_data['title'] = ""
                article_data['link'] = ""

            # Authors
            authors = article.find('div', class_='authors')
            if authors:
                author_spans = authors.find_all('span', class_='inlineblock')
                article_data['authors'] = [author.find('strong').text.strip() for author in author_spans]
            else:
                article_data['authors'] = []

            # Journal and Year
            journal_info = article.find('div', class_='color-grey-dark')
            if journal_info:
                journal_text = journal_info.text.strip()
                journal_parts = journal_text.split(',')
                article_data['journal'] = journal_parts[0].strip().replace('<em>', '').replace('</em>', '')
                article_data['year'] = journal_parts[1].strip()
            else:
                article_data['journal'] = ""
                article_data['year'] = ""

            # Special Issue
            special_issue = article.find('div', class_='belongsTo')
            if special_issue:
                link = special_issue.find('a')
                if link:
                    article_data['special_issue'] = link.text.strip()
                else:
                    article_data['special_issue'] = ""
            else:
                article_data['special_issue'] = ""

            # Editors
            article_data['editors'] = get_editors('https://www.mdpi.com' + article_data['link'])

            all_articles.append(article_data)

            # Write to JSON after each article to ensure data is saved if interrupted
            with open(file_name, 'w', encoding='utf-8') as f:
                json.dump(all_articles, f, ensure_ascii=False, indent=2)

            time.sleep(1)  # Wait between requests to avoid overloading the server

    return all_articles


def main():
    base_url = f"https://www.mdpi.com/search?sort=pubdate&page_count=10&year_from=1996&year_to=2025&journals={journal}&countries={country}&view=default"
    num_pages = 150  # Number of pages to scrape, adjust as needed

    articles = scrape_mdpi_articles(base_url, num_pages)
    print(f"Scraped {len(articles)} articles.\n")
    for article in articles:
        print(f"Title: {article['title']}")
        print(f"URL: {article['link']}")
        print(f"Authors: {', '.join(article['authors'])}")
        print(f"Journal: {article['journal']}")
        print(f"Year: {article['year']}")
        print(f"Special Issue: {article['special_issue']}")
        print(f"Editors: {', '.join(article['editors'])}")
        print("---")

    # If the script completes normally, we save the final state
    print("Scraping completed. Saving all data to file.")
    with open(file_name, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
