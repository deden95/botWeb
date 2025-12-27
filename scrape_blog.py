#!/usr/bin/env python3
"""
Bot Scraper untuk Blog LanyardKilat
Output: JSON file sesuai format import Laravel
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import os
import re
import time
from datetime import datetime
import sys

class BlogScraper:
    def __init__(self, base_url="https://lanyardkilat.co.id/blog", max_pages=10):
        self.base_url = base_url
        self.max_pages = max_pages
        self.posts = []
        self.images_dir = os.path.join(os.path.dirname(__file__), "images")
        
        # Create images directory
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape(self):
        """Main scraping function"""
        print(f"🚀 Memulai scraping dari: {self.base_url}")
        print(f"📄 Maksimal halaman: {self.max_pages}\n")
        
        page = 1
        has_more = True
        
        while has_more and page <= self.max_pages:
            url = f"{self.base_url}?page={page}" if page > 1 else self.base_url
            print(f"📖 Scraping halaman {page}: {url}")
            
            posts = self.scrape_page(url)
            
            if not posts:
                has_more = False
                print(f"⚠️  Tidak ada post di halaman {page}, berhenti scraping.\n")
            else:
                self.posts.extend(posts)
                print(f"✅ Ditemukan {len(posts)} post di halaman {page}\n")
                page += 1
            
            # Delay untuk menghindari rate limiting
            time.sleep(2)
        
        print(f"📊 Total posts ditemukan: {len(self.posts)}\n")
        
        # Save to JSON
        self.save_to_json()
        
        print(f"✅ Selesai!")
        print(f"📁 Data JSON: {os.path.join(os.path.dirname(__file__), 'scraped_posts.json')}")
        print(f"🖼️  Gambar: {self.images_dir}")
    
    def scrape_page(self, url):
        """Scrape posts from a page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            posts = []
            
            # Cari semua artikel/post - berbagai selector yang mungkin
            articles = (
                soup.find_all('article') or
                soup.find_all('div', class_=re.compile(r'post|blog-item|entry')) or
                soup.select('h2 a, h3 a')  # Fallback: ambil dari heading dengan link
            )
            
            if not articles:
                # Try alternative: cari semua link yang mengarah ke /blog/
                articles = soup.find_all('a', href=re.compile(r'/blog/'))
            
            for article in articles:
                post = self.extract_post_data(article, soup)
                if post:
                    posts.append(post)
            
            return posts
        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            return []
    
    def extract_post_data(self, article, soup):
        """Extract post data from article element"""
        try:
            post = {}
            
            # Extract title
            title_elem = (
                article.find('h1') or
                article.find('h2') or
                article.find('h3') or
                article.find('a', class_=re.compile(r'title|post-title'))
            )
            
            if not title_elem:
                return None
            
            post['title'] = title_elem.get_text(strip=True)
            
            if not post['title'] or post['title'] == 'Untitled':
                return None
            
            # Extract link/URL
            link_elem = article.find('a', href=re.compile(r'/blog/|/post/'))
            if not link_elem and article.name == 'a':
                link_elem = article
            
            if link_elem and link_elem.get('href'):
                href = link_elem.get('href')
                post['url'] = urljoin(self.base_url, href)
                
                # Extract slug from URL
                slug_match = re.search(r'/([^/]+)/?$', href)
                if slug_match:
                    post['slug'] = slug_match.group(1)
                else:
                    post['slug'] = self.slugify(post['title'])
            else:
                post['url'] = ''
                post['slug'] = self.slugify(post['title'])
            
            # Extract excerpt
            excerpt_elem = (
                article.find('p') or
                article.find('div', class_=re.compile(r'excerpt|summary|description'))
            )
            post['excerpt'] = excerpt_elem.get_text(strip=True) if excerpt_elem else ''
            
            # Extract date
            date_elem = (
                article.find('time') or
                article.find('span', class_=re.compile(r'date')) or
                article.find('div', class_=re.compile(r'date'))
            )
            post['published_at'] = date_elem.get_text(strip=True) if date_elem else None
            
            # Extract author
            author_elem = (
                article.find('span', class_=re.compile(r'author')) or
                article.find('div', class_=re.compile(r'author')) or
                article.find('a', class_=re.compile(r'author'))
            )
            post['author'] = author_elem.get_text(strip=True) if author_elem else 'Admin'
            
            # Extract image
            img_elem = article.find('img')
            if img_elem:
                img_src = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('data-lazy-src')
                if img_src:
                    img_url = urljoin(self.base_url, img_src)
                    post['thumbnail_path'] = self.download_image(img_url, post['slug'])
                else:
                    post['thumbnail_path'] = None
            else:
                post['thumbnail_path'] = None
            
            # Extract categories
            category_elems = article.find_all('a', href=re.compile(r'category')) or article.find_all('span', class_=re.compile(r'category'))
            post['categories'] = [elem.get_text(strip=True) for elem in category_elems if elem.get_text(strip=True)]
            
            # Extract tags
            tag_elems = article.find_all('a', href=re.compile(r'tag')) or article.find_all('span', class_=re.compile(r'tag'))
            post['tags'] = [elem.get_text(strip=True) for elem in tag_elems if elem.get_text(strip=True)]
            
            # Scrape detail page untuk body lengkap
            if post['url']:
                print(f"  → Mengambil konten lengkap: {post['url']}")
                body = self.scrape_post_detail(post['url'])
                post['body'] = body if body else ''
            else:
                post['body'] = ''
            
            # Set defaults
            post['type'] = 'post'
            post['status'] = 'published'
            post['is_featured'] = False
            post['price'] = None
            post['og_image'] = post['thumbnail_path']
            post['redirect_url'] = None
            post['meta_title'] = post['title']
            post['meta_description'] = post['excerpt']
            post['meta_keywords'] = ', '.join(post['tags']) if post['tags'] else None
            
            return post
        except Exception as e:
            print(f"  ⚠️  Error extracting post: {e}")
            return None
    
    def scrape_post_detail(self, url):
        """Scrape full content from post detail page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cari konten artikel - berbagai selector
            content_selectors = [
                'article .content',
                'article .entry-content',
                'article .post-content',
                '.post-content',
                '.entry-content',
                '.article-content',
                'main .content',
                'article',
            ]
            
            content = None
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Hapus elemen yang tidak perlu
                    for unwanted in content_elem.select('.ad, .ads, .related, .share, .comment, aside, nav'):
                        unwanted.decompose()
                    
                    content = content_elem
                    break
            
            if not content:
                # Fallback: ambil semua paragraf
                paragraphs = soup.select('article p, main p')
                if paragraphs:
                    content = soup.new_tag('div')
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 50:
                            content.append(p)
            
            if content:
                # Clean HTML
                body = self.clean_html(str(content))
                print(f"    ✅ Konten lengkap berhasil diambil")
                return body
            
            return None
        except Exception as e:
            print(f"    ⚠️  Error scraping detail: {e}")
            return None
    
    def clean_html(self, html):
        """Clean HTML content"""
        if not html:
            return ''
        
        # Remove script and style tags
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove comments
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
        
        # Fix image src to absolute URLs
        def fix_img_src(match):
            src = match.group(2)
            if not src.startswith('http'):
                src = urljoin(self.base_url, src)
            return f'<img{match.group(1)}src="{src}"{match.group(3)}>'
        
        html = re.sub(r'<img([^>]*)src=["\']([^"\']+)["\']([^>]*)>', fix_img_src, html, flags=re.IGNORECASE)
        
        return html.strip()
    
    def download_image(self, url, slug):
        """Download image and return relative path"""
        try:
            if not url:
                return None
            
            # Get file extension
            parsed = urlparse(url)
            ext = os.path.splitext(parsed.path)[1] or '.jpg'
            filename = f"{slug}_{int(time.time())}{ext}"
            filepath = os.path.join(self.images_dir, filename)
            
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"    ✅ Gambar disimpan: {filename}")
            return f"images/{filename}"
        except Exception as e:
            print(f"    ⚠️  Gagal download gambar {url}: {e}")
            return None
    
    def slugify(self, text):
        """Convert text to slug"""
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-')
    
    def save_to_json(self):
        """Save posts to JSON file"""
        data = {
            'version': '1.0',
            'scraped_at': datetime.now().isoformat(),
            'source_url': self.base_url,
            'total': len(self.posts),
            'posts': self.posts
        }
        
        filepath = os.path.join(os.path.dirname(__file__), 'scraped_posts.json')
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Data disimpan ke: {filepath}\n")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape blog posts dari LanyardKilat')
    parser.add_argument('--url', default='https://lanyardkilat.co.id/blog', help='URL blog yang akan di-scrape')
    parser.add_argument('--max-pages', type=int, default=10, help='Maksimal halaman yang di-scrape')
    
    args = parser.parse_args()
    
    scraper = BlogScraper(args.url, args.max_pages)
    scraper.scrape()


if __name__ == '__main__':
    main()

