import sys
import json
import trafilatura

def scrape(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return json.dumps({"error": "failed_to_fetch", "url": url}, ensure_ascii=False)
        
        # Extract metadata
        metadata = trafilatura.extract_metadata(downloaded)
        
        # Extract content
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True, no_fallback=False)
        
        if not text:
             return json.dumps({"error": "no_content_extracted", "url": url}, ensure_ascii=False)

        data = {
            "url": url,
            "title": metadata.title if metadata else None,
            "date": metadata.date if metadata else None,
            "sitename": metadata.sitename if metadata else None,
            "text": text
        }
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "no_url_provided"}))
        sys.exit(1)
    
    url = sys.argv[1]
    # Configure stdout to handle utf-8
    sys.stdout.reconfigure(encoding='utf-8')
    print(scrape(url))
