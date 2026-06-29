import re
from urllib.parse import urlparse

def run(params: dict) -> dict:
    status = 'success'
    message = ''
    urls = []
    
    try:
        text = params.get('text')
        
        if not text:
            raise ValueError("Input text is missing")
        
        pattern = r'https?://\S+'
        matches = re.findall(pattern, text)
        
        for url in matches:
            parsed_url = urlparse(url)
            if parsed_url.scheme in ['http', 'https']:
                urls.append(url)
    except Exception as e:
        status = 'error'
        message = str(e)
    
    return {
        'status': status,
        'message': message,
        'urls': sorted(urls) if status == 'success' else []
    }