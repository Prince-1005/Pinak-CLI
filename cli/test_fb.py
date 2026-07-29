import requests
import re

url = 'https://www.facebook.com/share/p/1BZzH5M1H2/'
headers = {'User-Agent': 'Mozilla/5.0'}
r = requests.get(url, headers=headers)
print("og:video in HTML:", 'og:video' in r.text)
matches = re.findall(r'<meta property="og:image" content="([^"]+)"', r.text)
print("og:images found:", matches)
