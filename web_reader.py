"""Fetch bounded public webpage text without scripts, cookies or local-network access."""
import http.client
from html.parser import HTMLParser
import ipaddress
import socket
import time
from urllib.parse import urlsplit, urljoin, urldefrag

class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.skip=0; self.in_title=False; self.title=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','template'): self.skip+=1
        if tag=='title': self.in_title=True
        if tag in ('p','div','br','li','h1','h2','h3','tr','section','article'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','template') and self.skip: self.skip-=1
        if tag=='title': self.in_title=False
        if tag in ('p','div','li','section','article'): self.parts.append('\n')
    def handle_data(self,data):
        if self.skip:return
        if self.in_title:self.title.append(data)
        else:self.parts.append(data)

def public_target(url):
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Use a public http:// or https:// URL without login credentials.')
    port=parsed.port or (443 if parsed.scheme=='https' else 80)
    if port not in (80,443):raise ValueError('Only standard web ports are supported.')
    addresses=socket.getaddrinfo(parsed.hostname,port,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Only public websites can be read; local and private addresses are blocked.')
    return parsed,port,addresses[0][4][0]

def read_link(url):
    if not isinstance(url,str) or len(url)>4096:raise ValueError('Invalid URL.')
    url=urldefrag(url.strip())[0];deadline=time.monotonic()+40
    for redirect in range(6):
        parsed,port,address=public_target(url)
        cls=http.client.HTTPSConnection if parsed.scheme=='https' else http.client.HTTPConnection
        conn=cls(parsed.hostname,port,timeout=10)
        # Pin the connection to the validated IP; HTTPS still verifies the original hostname.
        conn._create_connection=lambda target,timeout=10,source_address=None: socket.create_connection((address,port),timeout,source_address)
        try:
            conn.request('GET',(parsed.path or '/')+('?' + parsed.query if parsed.query else ''),headers={'User-Agent':'OpenVINO-Chat/1.0','Accept':'text/html,text/plain','Accept-Encoding':'identity'})
            response=conn.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise ValueError('Website returned an invalid redirect.')
                url=urljoin(url,location);continue
            if response.status!=200:raise ValueError(f'Website returned HTTP {response.status}. It may require a login or block automated access.')
            kind=response.getheader('Content-Type','').split(';')[0].lower()
            if kind not in ('text/html','text/plain','application/xhtml+xml'):raise ValueError('This reader supports HTML and plain text pages, not PDFs or other downloads.')
            if response.getheader('Content-Encoding','identity')!='identity':raise ValueError('Website returned unsupported compressed content.')
            chunks=[];size=0
            while True:
                if time.monotonic()>deadline:raise ValueError('Website took too long to respond.')
                chunk=response.read(16384)
                if not chunk:break
                size+=len(chunk)
                if size>2_000_000:raise ValueError('Page exceeds the 2 MB download limit.')
                chunks.append(chunk)
            charset=response.headers.get_content_charset() or 'utf-8'
            try:text=b''.join(chunks).decode(charset,errors='replace')
            except LookupError:text=b''.join(chunks).decode('utf-8',errors='replace')
            title=parsed.hostname
            if kind!='text/plain':
                parser=PageText();parser.feed(text);text=''.join(parser.parts);title=' '.join(parser.title).strip() or title
            text='\n'.join(' '.join(line.split()) for line in text.splitlines() if line.strip())
            if len(text)<40:raise ValueError('No useful page text found. This page may need JavaScript or a login; paste its text instead.')
            return {'url':url,'title':title[:200],'text':text[:24000],'truncated':len(text)>24000}
        finally:conn.close()
    raise ValueError('Website redirected too many times.')
