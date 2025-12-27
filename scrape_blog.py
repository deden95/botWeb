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

# Try to import mysql connector
try:
    import mysql.connector
    from mysql.connector import Error
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False
    print("⚠️  mysql-connector-python tidak terinstall. Install dengan: pip install mysql-connector-python")

# Try to import dateutil, fallback to manual parsing
try:
    from dateutil import parser as date_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False
    print("⚠️  python-dateutil tidak terinstall. Install dengan: pip install python-dateutil")

# Try to import mysql connector
try:
    import mysql.connector
    from mysql.connector import Error
    HAS_MYSQL = True
except ImportError:
    HAS_MYSQL = False
    # Don't print warning here, only when user tries to use database feature

class BlogScraper:
    def __init__(self, base_url="https://lanyardkilat.co.id/blog", max_pages=None, posts_per_page=10):
        self.base_url = base_url
        self.max_pages = max_pages  # None = semua halaman
        self.posts_per_page = posts_per_page
        self.posts = []
        self.images_dir = os.path.join(os.path.dirname(__file__), "images")
        
        # Create images directory
        os.makedirs(self.images_dir, exist_ok=True)
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def load_existing_posts(self):
        """Load existing posts from JSON to avoid duplicates"""
        filepath = os.path.join(os.path.dirname(__file__), 'scraped_posts.json')
        existing_slugs = set()
        existing_images = set()
        
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'posts' in data and isinstance(data['posts'], list):
                        for post in data['posts']:
                            if 'slug' in post:
                                existing_slugs.add(post['slug'])
                            if 'thumbnail_path' in post and post['thumbnail_path']:
                                existing_images.add(post['thumbnail_path'])
                        print(f"📋 Ditemukan {len(existing_slugs)} posts yang sudah ada di JSON")
            except Exception as e:
                print(f"⚠️  Error membaca file JSON: {e}")
        
        return existing_slugs, existing_images
    
    def scrape(self):
        """Main scraping function"""
        print(f"🚀 Memulai scraping dari: {self.base_url}")
        
        # Load existing posts untuk skip yang sudah ada
        existing_slugs, existing_images = self.load_existing_posts()
        
        if self.max_pages is None:
            print(f"📄 Mode: Semua halaman (tanpa limit)")
        else:
            print(f"📄 Mode: Maksimal {self.max_pages} halaman")
        
        if self.posts_per_page:
            print(f"📝 Limit: {self.posts_per_page} posts per halaman\n")
        else:
            print(f"📝 Limit: Semua posts per halaman\n")
        
        page = 1
        has_more = True
        total_scraped = 0
        skipped_count = 0
        
        while has_more:
            # Check max pages limit
            if self.max_pages is not None and page > self.max_pages:
                print(f"⏹️  Mencapai limit {self.max_pages} halaman, berhenti scraping.\n")
                break
            
            # Coba berbagai format pagination
            if page == 1:
                url = self.base_url
            else:
                # Coba format /page/{page} dulu (umum untuk WordPress/Laravel)
                url = f"{self.base_url}/page/{page}"
            
            print(f"📖 Scraping halaman {page}: {url}")
            
            posts = self.scrape_page(url, existing_slugs)
            
            if not posts:
                # Jika halaman kosong, coba format alternatif
                if page > 1:
                    alt_url = f"{self.base_url}?page={page}"
                    print(f"  🔄 Mencoba format alternatif: {alt_url}")
                    posts = self.scrape_page(alt_url, existing_slugs)
                
                if not posts:
                    has_more = False
                    print(f"⚠️  Tidak ada post di halaman {page}, berhenti scraping.\n")
            else:
                # Filter out posts that already exist
                new_posts = []
                for post in posts:
                    if post['slug'] in existing_slugs:
                        skipped_count += 1
                        print(f"  ⏭️  Skip: '{post['title']}' (sudah ada)")
                    else:
                        new_posts.append(post)
                        existing_slugs.add(post['slug'])  # Add to set to avoid duplicates in same run
                
                if not new_posts:
                    print(f"  ℹ️  Semua posts di halaman {page} sudah ada, skip halaman ini\n")
                    page += 1
                    continue
                
                # Limit posts per page if specified
                original_count = len(new_posts)
                if self.posts_per_page and len(new_posts) > self.posts_per_page:
                    new_posts = new_posts[:self.posts_per_page]
                    print(f"  ℹ️  Dibatasi dari {original_count} menjadi {self.posts_per_page} posts")
                
                # Download gambar dan ambil body lengkap untuk setiap post
                print(f"  📥 Memproses {len(new_posts)} posts baru...")
                success_count = 0
                failed_count = 0
                
                for i, post in enumerate(new_posts, 1):
                    try:
                        print(f"\n    [{i}/{len(new_posts)}] {post.get('title', 'N/A')}")
                        
                        # Scrape detail page untuk body lengkap dengan retry
                        if post.get('url'):
                            print(f"      → Mengambil konten lengkap: {post['url']}")
                            
                            # Retry mechanism untuk memastikan konten FULL ter-download
                            body = None
                            max_retries = 3
                            for retry in range(max_retries):
                                try:
                                    body = self.scrape_post_detail(post['url'])
                                    if body and len(body.strip()) > 50:
                                        break  # Berhasil, keluar dari retry loop
                                    elif retry < max_retries - 1:
                                        print(f"      ⚠️  Retry {retry + 1}/{max_retries} (konten terlalu pendek)...")
                                        time.sleep(3)  # Delay lebih lama sebelum retry
                                except Exception as e:
                                    if retry < max_retries - 1:
                                        print(f"      ⚠️  Error, retry {retry + 1}/{max_retries}: {e}")
                                        time.sleep(3)
                                    else:
                                        print(f"      ❌ Gagal setelah {max_retries} kali retry: {e}")
                            
                            post['body'] = body if body else ''
                            
                            if body and len(body.strip()) > 50:
                                success_count += 1
                                print(f"      ✅ Konten FULL berhasil diambil ({len(body)} karakter)")
                            else:
                                failed_count += 1
                                print(f"      ⚠️  Konten tidak berhasil diambil atau terlalu pendek")
                        else:
                            post['body'] = ''
                            failed_count += 1
                            print(f"      ⚠️  URL tidak tersedia")
                        
                        # Delay antar request lebih lama untuk memastikan semua ter-download FULL
                        if i < len(new_posts):  # Tidak delay untuk post terakhir
                            print(f"      ⏳ Menunggu 2 detik sebelum post berikutnya...")
                            time.sleep(2)  # Delay lebih lama untuk memastikan semua ter-download FULL
                            
                    except Exception as e:
                        failed_count += 1
                        post['body'] = ''
                        print(f"      ❌ Error memproses post: {e}")
                        import traceback
                        traceback.print_exc()
                        continue  # Lanjut ke post berikutnya meskipun ada error
                
                print(f"\n  ✅ Selesai memproses: {success_count} berhasil, {failed_count} gagal dari {len(new_posts)} posts")
                
                self.posts.extend(new_posts)
                total_scraped += len(new_posts)
                
                # Save to JSON after each page (incremental save)
                self.save_to_json()
                
                print(f"✅ Selesai halaman {page}: {len(new_posts)} post baru (Total: {total_scraped}, Skip: {skipped_count})\n")
                
                # If limited per page, stop after processing this page
                if self.posts_per_page:
                    has_more = False
                    print(f"⏹️  Selesai memproses {self.posts_per_page} posts per halaman.\n")
                elif len(new_posts) < original_count:
                    # Got less than expected, might be last page
                    has_more = False
                    print(f"ℹ️  Halaman {page} memiliki kurang dari expected posts, dianggap halaman terakhir.\n")
                else:
                    page += 1
            
            # Delay untuk menghindari rate limiting (lebih lama untuk memastikan semua ter-download FULL)
            print(f"  ⏳ Menunggu 3 detik sebelum halaman berikutnya...")
            time.sleep(3)
        
        print(f"📊 Total posts baru: {total_scraped}")
        if skipped_count > 0:
            print(f"⏭️  Posts dilewati (sudah ada): {skipped_count}")
        print(f"📁 Total semua posts di JSON: {len(self.posts)}\n")
    
    def scrape_page(self, url, existing_slugs=None):
        """Scrape posts from a page"""
        if existing_slugs is None:
            existing_slugs = set()
        
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Use html.parser (built-in, no extra dependencies needed)
            soup = BeautifulSoup(response.content, 'html.parser')
            posts = []
            
            # Cari semua artikel/post - berbagai selector yang mungkin
            articles = []
            
            # Try multiple selectors secara berurutan - lebih spesifik untuk lanyardkilat.co.id
            # Cari artikel berdasarkan struktur yang terlihat di website
            articles = []
            
            # Method 1: Cari article tag
            if soup.find_all('article'):
                articles = soup.find_all('article')
                print(f"  📋 Ditemukan {len(articles)} artikel dengan tag <article>")
            
            # Method 2: Cari div dengan class post/blog-item/entry
            if not articles:
                articles = soup.find_all('div', class_=re.compile(r'post|blog-item|entry|card'))
                if articles:
                    print(f"  📋 Ditemukan {len(articles)} artikel dengan class post/blog-item/entry/card")
            
            # Method 3: Cari heading dengan link (h2 a, h3 a)
            if not articles:
                articles = soup.select('h2 a, h3 a')
                if articles:
                    print(f"  📋 Ditemukan {len(articles)} artikel dari heading dengan link")
            
            # Method 4: Cari semua link yang mengarah ke /blog/ (bukan halaman blog itu sendiri)
            if not articles:
                all_blog_links = soup.find_all('a', href=re.compile(r'/blog/[^/]+/?$'))
                # Filter: hanya link yang bukan pagination dan bukan /blog/ saja
                articles = [link for link in all_blog_links 
                           if link.get('href') and 
                           not re.search(r'/blog/(page|category|tag)', link.get('href')) and
                           link.get('href') != '/blog' and link.get('href') != '/blog/']
                if articles:
                    print(f"  📋 Ditemukan {len(articles)} link artikel ke /blog/")
            
            # Method 5: Cari berdasarkan struktur card/blog post
            if not articles:
                # Cari div yang mengandung heading dan link
                potential_cards = soup.find_all('div', class_=re.compile(r'card|item|post'))
                for card in potential_cards:
                    heading = card.find(['h1', 'h2', 'h3', 'h4'])
                    link = card.find('a', href=re.compile(r'/blog/'))
                    if heading and link:
                        articles.append(card)
                if articles:
                    print(f"  📋 Ditemukan {len(articles)} artikel dari struktur card")
            
            # Extract data dari setiap artikel - PASTIKAN SEMUA DI-PROSES
            if not articles:
                print(f"  ⚠️  Tidak ada artikel ditemukan di halaman ini")
                return posts
            
            print(f"  🔄 Memproses {len(articles)} artikel...")
            extracted_count = 0
            skipped_count = 0
            
            for idx, article in enumerate(articles, 1):
                try:
                    post = self.extract_post_data(article, soup)
                    if post and post.get('title') and post.get('slug'):
                        # Pastikan URL ada (jika tidak ada, buat dari slug)
                        if not post.get('url'):
                            post['url'] = urljoin(self.base_url, f"/blog/{post['slug']}")
                            print(f"    ⚠️  URL dibuat dari slug: {post['url']}")
                        
                        # Cek duplicate dalam batch ini juga
                        if not any(p.get('slug') == post.get('slug') for p in posts):
                            posts.append(post)
                            extracted_count += 1
                            print(f"    ✅ [{idx}/{len(articles)}] Post: {post.get('title', 'N/A')[:50]} | URL: {post.get('url', 'N/A')[:60]}")
                        else:
                            skipped_count += 1
                            print(f"    ⏭️  [{idx}/{len(articles)}] Duplicate: {post.get('title', 'N/A')[:50]}")
                    else:
                        skipped_count += 1
                        print(f"    ⚠️  [{idx}/{len(articles)}] Post tidak valid (title: {post.get('title') if post else 'None'}, slug: {post.get('slug') if post else 'None'}, url: {post.get('url') if post else 'None'})")
                except Exception as e:
                    skipped_count += 1
                    print(f"    ❌ [{idx}/{len(articles)}] Error extracting post: {e}")
                    import traceback
                    traceback.print_exc()
                    continue  # Lanjut ke artikel berikutnya meskipun ada error
            
            print(f"  ✅ Berhasil extract {extracted_count} posts baru, {skipped_count} dilewati dari {len(articles)} artikel")
            
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
            
            # Extract link/URL - cari dengan berbagai cara (lebih agresif)
            link_elem = None
            href = None
            
            # Method 1: Jika article sendiri adalah link
            if article.name == 'a' and article.get('href'):
                link_elem = article
                href = article.get('href')
            
            # Method 2: Cari link dengan href yang mengandung /blog/ atau /post/ di dalam article
            if not href:
                link_elem = article.find('a', href=re.compile(r'/blog/|/post/'))
                if link_elem:
                    href = link_elem.get('href')
            
            # Method 3: Cari link pertama yang ada di dalam article (apapun href-nya)
            if not href:
                first_link = article.find('a', href=True)
                if first_link and first_link.get('href'):
                    href = first_link.get('href')
                    # Hanya gunakan jika href tidak kosong dan bukan anchor link
                    if href and not href.startswith('#') and not href.startswith('javascript:'):
                        link_elem = first_link
            
            # Method 4: Cari dari parent element
            if not href:
                parent = article.parent
                if parent:
                    parent_link = parent.find('a', href=re.compile(r'/blog/|/post/'))
                    if parent_link:
                        link_elem = parent_link
                        href = parent_link.get('href')
            
            # Method 5: Cari dari sibling elements
            if not href:
                # Cari di next sibling
                next_sibling = article.find_next_sibling()
                if next_sibling:
                    sibling_link = next_sibling.find('a', href=re.compile(r'/blog/|/post/'))
                    if sibling_link:
                        link_elem = sibling_link
                        href = sibling_link.get('href')
            
            # Method 6: Cari link yang mengandung title text
            if not href and post.get('title'):
                title_text = post['title'][:30]  # Ambil 30 karakter pertama
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    link_text = link.get_text(strip=True)
                    if title_text.lower() in link_text.lower() or link_text.lower() in title_text.lower():
                        if link.get('href') and re.search(r'/blog/|/post/', link.get('href')):
                            link_elem = link
                            href = link.get('href')
                            break
            
            if href:
                # Clean href (remove query string, fragment)
                href = href.split('?')[0].split('#')[0].strip()
                if not href.startswith('http'):
                    post['url'] = urljoin(self.base_url, href)
                else:
                    post['url'] = href
                
                # Extract slug from URL
                slug_match = re.search(r'/([^/]+)/?$', post['url'])
                if slug_match:
                    post['slug'] = slug_match.group(1).strip('/')
                else:
                    post['slug'] = self.slugify(post['title'])
            else:
                # Jika tidak ada URL, buat dari title (fallback)
                post['slug'] = self.slugify(post['title'])
                post['url'] = urljoin(self.base_url, f"/blog/{post['slug']}")
                print(f"      ⚠️  URL tidak ditemukan di HTML, menggunakan fallback: {post['url']}")
            
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
            date_text = date_elem.get_text(strip=True) if date_elem else None
            
            # Parse date to ISO format
            if date_text:
                try:
                    if HAS_DATEUTIL:
                        # Try to parse date string to datetime
                        dt = date_parser.parse(date_text, fuzzy=True)
                        post['published_at'] = dt.isoformat()
                    else:
                        # Manual parsing for common formats
                        # Try common date formats
                        date_formats = [
                            '%Y-%m-%d',
                            '%d %B %Y',
                            '%d %b %Y',
                            '%B %d, %Y',
                            '%b %d, %Y',
                            '%d/%m/%Y',
                            '%m/%d/%Y',
                        ]
                        parsed = False
                        for fmt in date_formats:
                            try:
                                dt = datetime.strptime(date_text, fmt)
                                post['published_at'] = dt.isoformat()
                                parsed = True
                                break
                            except:
                                continue
                        if not parsed:
                            post['published_at'] = datetime.now().isoformat()
                except Exception as e:
                    # If parsing fails, use current date
                    post['published_at'] = datetime.now().isoformat()
            else:
                post['published_at'] = None
            
            # Extract author
            author_elem = (
                article.find('span', class_=re.compile(r'author')) or
                article.find('div', class_=re.compile(r'author')) or
                article.find('a', class_=re.compile(r'author'))
            )
            post['author'] = author_elem.get_text(strip=True) if author_elem else 'Admin'
            
            # Extract image - download langsung saat extract
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
            
            # Body akan di-scrape nanti setelah semua post di-list
            # Ini untuk menghindari terlalu banyak request sekaligus
            post['body'] = ''  # Temporary, akan diisi nanti saat proses
            
            # Set defaults sesuai format Laravel
            post['type'] = 'post'
            post['status'] = 'draft'  # Set sebagai draft, bukan published
            post['is_featured'] = False
            post['price'] = None
            post['og_image'] = post['thumbnail_path']  # Fallback ke thumbnail jika tidak ada
            post['redirect_url'] = None
            post['meta_title'] = post['title']
            post['meta_description'] = post['excerpt']
            post['meta_keywords'] = ', '.join(post['tags']) if post['tags'] else None
            
            # Jika status draft, published_at harus None
            if post['status'] == 'draft':
                post['published_at'] = None
            else:
                # Pastikan published_at dalam format ISO8601 atau None
                if post['published_at'] and not isinstance(post['published_at'], str):
                    post['published_at'] = post['published_at'].isoformat() if hasattr(post['published_at'], 'isoformat') else None
            
            return post
        except Exception as e:
            print(f"  ⚠️  Error extracting post: {e}")
            return None
    
    def scrape_post_detail(self, url):
        """Scrape full content from post detail page"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Use html.parser (built-in, no extra dependencies needed)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cari konten artikel - berbagai selector (prioritas dari yang paling spesifik)
            content_selectors = [
                'article .entry-content',
                'article .post-content',
                'article .content',
                '.entry-content',
                '.post-content',
                '.article-content',
                '.content-body',
                '.post-body',
                'article main',
                'main .content',
                'article',
                'main article',
                '[role="article"]',
                '.blog-content',
                '.single-content',
            ]
            
            content = None
            for selector in content_selectors:
                try:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        # Hapus elemen yang tidak perlu (ads, related, share, comment, sidebar, nav)
                        for unwanted in content_elem.select('.ad, .ads, .advertisement, .related, .share, .share-buttons, .comment, .comments, aside, nav, .sidebar, .widget, .social-share, .author-box, .post-meta, .breadcrumb, .pagination, .navigation, .tags, .categories, header, footer'):
                            unwanted.decompose()
                        
                        # Hapus script dan style tags
                        for script in content_elem.find_all(['script', 'style']):
                            script.decompose()
                        
                        # Cek apakah ada konten yang cukup
                        text_content = content_elem.get_text(strip=True)
                        if text_content and len(text_content) > 100:  # Minimal 100 karakter
                            content = content_elem
                            print(f"      📄 Konten ditemukan dengan selector: {selector} ({len(text_content)} karakter)")
                            break
                except Exception as e:
                    continue
            
            if not content:
                # Fallback 1: ambil semua paragraf dari article atau main
                article_elem = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'content|post|article'))
                if article_elem:
                    paragraphs = article_elem.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'blockquote'])
                    if paragraphs:
                        content = soup.new_tag('div')
                        for elem in paragraphs:
                            text = elem.get_text(strip=True)
                            if text and len(text) > 30:  # Skip elemen terlalu pendek
                                content.append(elem)
                        text_content = content.get_text(strip=True)
                        if text_content and len(text_content) > 100:
                            print(f"      📄 Konten ditemukan dari paragraf (fallback 1) ({len(text_content)} karakter)")
                        else:
                            content = None
            
            if not content:
                # Fallback 2: ambil semua div dengan class yang mengandung 'content'
                content_divs = soup.find_all('div', class_=re.compile(r'content|post|article|body', re.I))
                if content_divs:
                    for div in content_divs:
                        text = div.get_text(strip=True)
                        if text and len(text) > 200:  # Minimal 200 karakter untuk fallback
                            # Hapus elemen yang tidak perlu
                            for unwanted in div.select('.ad, .ads, .related, .share, .comment, aside, nav, .sidebar, .widget'):
                                unwanted.decompose()
                            content = div
                            print(f"      📄 Konten ditemukan dari div dengan class content (fallback 2) ({len(text)} karakter)")
                            break
            
            if content:
                # Clean HTML dan preserve structure
                body = self.clean_html(str(content))
                if body and len(body.strip()) > 50:  # Pastikan ada konten
                    print(f"      ✅ Konten HTML FULL berhasil diambil ({len(body)} karakter)")
                    return body
                else:
                    print(f"      ⚠️  Konten terlalu pendek setelah cleaning ({len(body) if body else 0} karakter)")
                    # Fallback: buat HTML dari text content dengan struktur paragraf
                    text_content = content.get_text(separator='\n', strip=True)
                    if len(text_content) > 100:
                        # Convert text ke HTML dengan struktur paragraf
                        paragraphs = [p.strip() for p in text_content.split('\n') if p.strip() and len(p.strip()) > 20]
                        if paragraphs:
                            html_content = '\n'.join([f'<p>{p}</p>' for p in paragraphs])
                            print(f"      ℹ️  Menggunakan text content sebagai fallback dengan struktur HTML ({len(html_content)} karakter)")
                            return html_content
                    return None
            
            print(f"      ⚠️  Konten tidak ditemukan dengan selector, mencoba fallback terakhir...")
            # Fallback terakhir: ambil semua text dari body tag
            body_tag = soup.find('body')
            if body_tag:
                # Hapus script, style, nav, header, footer, aside
                for unwanted in body_tag.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                    unwanted.decompose()
                # Hapus juga elemen dengan class tertentu
                for unwanted in body_tag.select('.ad, .ads, .related, .share, .comment, .sidebar, .widget'):
                    unwanted.decompose()
                # Ambil text dari body tag dan convert ke HTML
                fallback_text = body_tag.get_text(separator='\n', strip=True)
                if len(fallback_text) > 200:
                    # Convert text ke HTML dengan struktur paragraf
                    paragraphs = [p.strip() for p in fallback_text.split('\n') if p.strip() and len(p.strip()) > 20]
                    if paragraphs:
                        html_content = '\n'.join([f'<p>{p}</p>' for p in paragraphs])
                        print(f"      ℹ️  Menggunakan body tag sebagai fallback terakhir dengan struktur HTML ({len(html_content)} karakter)")
                        return html_content
            
            return None
        except Exception as e:
            print(f"      ❌ Error scraping detail: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def clean_html(self, html):
        """Clean HTML content - format HTML rapi untuk Quill editor (tanpa gambar, link, dll)"""
        if not html:
            return ''
        
        # Parse dengan BeautifulSoup untuk manipulasi yang lebih baik
        soup = BeautifulSoup(html, 'html.parser')
        
        # Hapus semua elemen yang tidak diperlukan
        for tag in soup.find_all(['script', 'style', 'img', 'iframe', 'video', 'audio', 'embed', 'object', 'svg', 'canvas', 'figure', 'picture']):
            tag.decompose()
        
        # Hapus semua link (a tag) tapi simpan text-nya
        for link in soup.find_all('a'):
            # Ganti link dengan text-nya saja (tanpa href)
            link_text = link.get_text(strip=True)
            if link_text:
                link.replace_with(soup.new_string(link_text))
            else:
                link.decompose()
        
        # Hapus elemen yang tidak perlu (ads, related, share, dll)
        for unwanted in soup.find_all(['nav', 'header', 'footer', 'aside', 'form', 'button', 'input', 'select', 'textarea']):
            unwanted.decompose()
        
        # Hapus elemen dengan class tertentu yang tidak perlu
        for unwanted in soup.select('.ad, .ads, .advertisement, .related, .share, .share-buttons, .comment, .comments, .sidebar, .widget, .social-share, .author-box, .post-meta, .breadcrumb, .pagination, .navigation, .tags, .categories'):
            unwanted.decompose()
        
        # Hapus semua atribut dari tag yang tersisa (hanya simpan struktur)
        allowed_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'strong', 'em', 'b', 'i', 'u', 'br', 'hr', 'pre', 'code']
        for tag in soup.find_all():
            if tag.name in allowed_tags:
                # Hapus semua atribut, hanya simpan tag dan isinya
                tag.attrs = {}
            elif tag.name in ['div', 'span', 'section', 'article', 'main']:
                # Unwrap tag container tapi simpan isinya
                tag.unwrap()
            else:
                # Untuk tag lain, hapus tapi simpan text-nya
                if tag.name not in ['html', 'body']:
                    tag_text = tag.get_text(strip=True)
                    if tag_text:
                        tag.replace_with(soup.new_string(tag_text + ' '))
                    else:
                        tag.decompose()
        
        # Hapus tag kosong
        for tag in soup.find_all():
            if not tag.get_text(strip=True) and tag.name not in ['br', 'hr']:
                tag.decompose()
        
        # Pastikan struktur HTML rapi - wrap dalam div
        body_content = soup.find('body')
        if body_content:
            content = body_content
        else:
            content = soup
        
        # Buat HTML yang rapi
        result = str(content)
        
        # Remove comments
        result = re.sub(r'<!--.*?-->', '', result, flags=re.DOTALL)
        
        # Clean up whitespace dalam tag
        result = re.sub(r'<([^>]+)>\s+', r'<\1>', result)  # Remove space after opening tag
        result = re.sub(r'\s+</([^>]+)>', r'</\1>', result)  # Remove space before closing tag
        
        # Pastikan paragraf terpisah dengan baik
        result = re.sub(r'</p>\s*<p>', '</p>\n<p>', result)  # Add newline between paragraphs
        result = re.sub(r'</h[1-6]>\s*<p>', '</h1>\n<p>', result)  # Add newline after heading
        
        # Clean up multiple whitespaces (tapi preserve structure)
        result = re.sub(r'\s+', ' ', result)  # Multiple spaces to single (dalam text)
        result = re.sub(r'>\s+<', '><', result)  # Remove spaces between tags
        
        # Pastikan ada struktur dasar jika kosong
        if not result.strip() or len(result.strip()) < 10:
            return ''
        
        return result.strip()
    
    def download_image(self, url, slug):
        """Download image and return relative path (skip if already exists)"""
        try:
            if not url:
                return None
            
            # Get file extension from URL
            parsed = urlparse(url)
            ext = os.path.splitext(parsed.path)[1]
            
            # If no extension, try to detect from content-type
            if not ext:
                try:
                    head_response = self.session.head(url, timeout=10, allow_redirects=True)
                    content_type = head_response.headers.get('content-type', '')
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    elif 'gif' in content_type:
                        ext = '.gif'
                    else:
                        ext = '.jpg'  # default
                except:
                    ext = '.jpg'  # default if HEAD fails
            
            # Use slug as filename
            filename = f"{slug}{ext}"
            filepath = os.path.join(self.images_dir, filename)
            
            # Check if file already exists
            if os.path.exists(filepath):
                print(f"      ⏭️  Gambar sudah ada: {filename}")
                return f"images/{filename}"
            
            # If file exists with different extension, check common extensions
            base_name = os.path.splitext(filename)[0]
            for check_ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                check_file = os.path.join(self.images_dir, f"{base_name}{check_ext}")
                if os.path.exists(check_file):
                    print(f"      ⏭️  Gambar sudah ada: {os.path.basename(check_file)}")
                    return f"images/{os.path.basename(check_file)}"
            
            # Download image
            response = self.session.get(url, timeout=30, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"      ✅ Gambar disimpan: {filename}")
            return f"images/{filename}"
        except Exception as e:
            print(f"      ⚠️  Gagal download gambar {url}: {e}")
            return None
    
    def slugify(self, text):
        """Convert text to slug"""
        text = text.lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-')
    
    def save_to_json(self):
        """Save posts to JSON file (incremental - merge with existing)"""
        filepath = os.path.join(os.path.dirname(__file__), 'scraped_posts.json')
        
        # Load existing posts
        existing_posts = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'posts' in data and isinstance(data['posts'], list):
                        existing_posts = data['posts']
            except:
                existing_posts = []
        
        # Merge: existing + new (avoid duplicates by slug)
        existing_slugs = {post.get('slug') for post in existing_posts if post.get('slug')}
        merged_posts = existing_posts.copy()
        
        for new_post in self.posts:
            if new_post.get('slug') not in existing_slugs:
                merged_posts.append(new_post)
                existing_slugs.add(new_post.get('slug'))
        
        # Save merged data
        data = {
            'version': '1.0',
            'scraped_at': datetime.now().isoformat(),
            'source_url': self.base_url,
            'total': len(merged_posts),
            'posts': merged_posts
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 Data JSON disimpan: {len(merged_posts)} total posts ({len(self.posts)} baru ditambahkan)")


def get_db_credentials():
    """Get database credentials from user input or config file"""
    config_file = 'db_config.json'
    
    # Cek apakah ada file config
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"✅ Menggunakan konfigurasi dari {config_file}")
                use_saved = input("Gunakan konfigurasi yang tersimpan? (y/n, default: y): ").strip().lower()
                if use_saved != 'n':
                    return config
        except Exception as e:
            print(f"⚠️  Error membaca {config_file}: {e}")
    
    # Jika tidak ada atau user ingin input baru, minta input dari user
    print("\n" + "=" * 60)
    print("📊 Konfigurasi Database")
    print("=" * 60)
    print("Masukkan kredensial database:")
    print("(Tekan Enter untuk skip field yang tidak tahu)")
    print()
    
    host = input("Host (default: 127.0.0.1): ").strip() or "127.0.0.1"
    port = input("Port (default: 3306): ").strip() or "3306"
    database = input("Database name: ").strip()
    username = input("Username: ").strip()
    password = input("Password: ").strip()
    table_name = input("Nama tabel posts (default: posts): ").strip() or "posts"
    
    if not database or not username:
        print("⚠️  Database name dan username wajib diisi!")
        return None
    
    config = {
        'host': host,
        'port': int(port),
        'database': database,
        'username': username,
        'password': password,
        'table_name': table_name
    }
    
    # Simpan ke file config untuk下次使用
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f"\n✅ Konfigurasi disimpan ke {config_file}")
    except Exception as e:
        print(f"⚠️  Tidak bisa menyimpan config: {e}")
    
    return config

def fetch_from_database(config):
    """Fetch posts from database"""
    if not HAS_MYSQL:
        print("❌ mysql-connector-python tidak terinstall!")
        print("Install dengan: pip install mysql-connector-python")
        return []
    
    try:
        print(f"\n🔌 Menghubungkan ke database {config['database']}...")
        connection = mysql.connector.connect(
            host=config['host'],
            port=config['port'],
            database=config['database'],
            user=config['username'],
            password=config['password']
        )
        
        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)
            table_name = config['table_name']
            
            # Query untuk ambil semua posts
            query = f"""
                SELECT 
                    id, title, slug, type, excerpt, body, 
                    price, thumbnail_path, og_image, status, 
                    is_featured, published_at, redirect_url,
                    meta_title, meta_description, meta_keywords,
                    created_at, updated_at
                FROM {table_name}
                WHERE type = 'post'
                ORDER BY created_at DESC
            """
            
            cursor.execute(query)
            posts = cursor.fetchall()
            
            print(f"✅ Berhasil mengambil {len(posts)} posts dari database")
            
            # Convert ke format yang sama dengan scraping
            formatted_posts = []
            for post in posts:
                formatted_post = {
                    'title': post.get('title', ''),
                    'slug': post.get('slug', ''),
                    'type': post.get('type', 'post'),
                    'excerpt': post.get('excerpt', ''),
                    'body': post.get('body', ''),
                    'price': post.get('price'),
                    'thumbnail_path': post.get('thumbnail_path'),
                    'og_image': post.get('og_image'),
                    'status': 'draft',  # Set sebagai draft
                    'is_featured': bool(post.get('is_featured', False)),
                    'published_at': None,  # Set None untuk draft
                    'redirect_url': post.get('redirect_url'),
                    'meta_title': post.get('meta_title'),
                    'meta_description': post.get('meta_description'),
                    'meta_keywords': post.get('meta_keywords'),
                    'categories': [],  # TODO: bisa diisi dari pivot table jika ada
                    'tags': [],  # TODO: bisa diisi dari pivot table jika ada
                }
                formatted_posts.append(formatted_post)
            
            cursor.close()
            connection.close()
            
            return formatted_posts
            
    except Error as e:
        print(f"❌ Error koneksi database: {e}")
        return []
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def show_menu():
    """Show interactive menu"""
    print("\n" + "="*60)
    print("🤖 BOT SCRAPER BLOG LANYARDKILAT")
    print("="*60)
    print("\nPilih mode:")
    print("1. Scrape SEMUA halaman (tanpa limit)")
    print("2. Scrape per halaman (10 artikel + 10 gambar)")
    print("3. Import dari Database")
    print("0. Keluar")
    print("-"*60)
    print("ℹ️  Bot akan skip artikel/gambar yang sudah ada di JSON")
    print("-"*60)
    
    choice = input("\nPilih opsi (0-3): ").strip()
    return choice

def main():
    """Main function"""
    import argparse
    
    # Check if arguments provided (non-interactive mode)
    parser = argparse.ArgumentParser(description='Scrape blog posts dari LanyardKilat')
    parser.add_argument('--url', default='https://lanyardkilat.co.id/blog', help='URL blog yang akan di-scrape')
    parser.add_argument('--max-pages', type=int, default=None, help='Maksimal halaman yang di-scrape')
    parser.add_argument('--posts-per-page', type=int, default=None, help='Jumlah posts per halaman')
    parser.add_argument('--all', action='store_true', help='Scrape semua halaman tanpa limit')
    parser.add_argument('--non-interactive', action='store_true', help='Non-interactive mode (use arguments)')
    
    args = parser.parse_args()
    
    # If non-interactive or arguments provided, use arguments
    if args.non_interactive or any([args.max_pages is not None, args.posts_per_page is not None, args.all]):
        max_pages = None if args.all else args.max_pages
        posts_per_page = None if args.posts_per_page == 0 else args.posts_per_page
        scraper = BlogScraper(args.url, max_pages, posts_per_page)
        scraper.scrape()
        return
    
    # Interactive mode
    while True:
        choice = show_menu()
        
        if choice == '0':
            print("\n👋 Keluar dari program. Sampai jumpa!")
            break
        elif choice == '3':
            # Import dari database
            config = get_db_credentials()
            if not config:
                print("❌ Konfigurasi database tidak lengkap!")
                continue
            
            posts = fetch_from_database(config)
            if posts:
                scraper = BlogScraper(args.url)
                scraper.posts = posts
                scraper.save_to_json()
                print(f"\n✅ {len(posts)} posts berhasil di-export ke JSON!")
                print(f"📁 File: scraped_posts.json")
            else:
                print("❌ Tidak ada data yang diambil dari database")
        elif choice == '1':
            # Semua halaman, semua posts
            max_pages = None
            posts_per_page = None
        elif choice == '2':
            # Per halaman, 10 posts
            max_pages = None
            posts_per_page = 10
        else:
            print("\n❌ Pilihan tidak valid! Silakan pilih lagi.\n")
            continue
        
        # Start scraping (skip if choice was database import)
        if choice in ['1', '2']:
            print("\n" + "="*60)
            scraper = BlogScraper(args.url, max_pages, posts_per_page)
            scraper.scrape()
            
            # Ask if want to continue (only for per-page mode)
            if choice == '2':
                print("\n" + "="*60)
                continue_choice = input("\nLanjutkan ke halaman berikutnya? (y/n): ").strip().lower()
                if continue_choice != 'y':
                    print("\n👋 Selesai! Terima kasih.")
                    break
                print()
            else:
                # All pages mode - finish after all done
                print("\n👋 Selesai scraping semua halaman!")
                break


if __name__ == '__main__':
    main()

