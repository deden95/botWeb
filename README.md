# Bot Scraper Blog LanyardKilat

Bot untuk scraping blog posts dari https://lanyardkilat.co.id/blog dan menyimpan ke format JSON yang sesuai untuk import ke Laravel.

## Instalasi

1. Install Python 3.8+ jika belum ada
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Cara Menggunakan

### Mode Interaktif (Recommended)
Jalankan tanpa argument untuk masuk ke menu interaktif:
```bash
python scrape_blog.py
```

Menu yang muncul:
1. Scrape SEMUA halaman (tanpa limit)
2. Scrape 10 posts per halaman (semua halaman)
3. Scrape 20 posts per halaman (semua halaman)
4. Scrape 50 posts per halaman (semua halaman)
5. Scrape semua posts per halaman (tanpa limit posts)
6. Custom (tentukan sendiri)
0. Keluar

Setelah scraping selesai, akan ditanya apakah ingin melanjutkan ke halaman berikutnya.

### Mode Non-Interaktif (Command Line)
```bash
# Scrape semua halaman
python scrape_blog.py --all

# Scrape dengan limit halaman
python scrape_blog.py --max-pages 5

# Scrape dengan limit posts per halaman
python scrape_blog.py --posts-per-page 10

# Kombinasi
python scrape_blog.py --max-pages 5 --posts-per-page 10 --non-interactive
```

## Output

1. **scraped_posts.json** - File JSON dengan format sesuai untuk import ke Laravel
2. **images/** - Folder berisi semua gambar yang di-download

## Format Output JSON

```json
{
  "version": "1.0",
  "scraped_at": "2025-12-27T...",
  "source_url": "https://lanyardkilat.co.id/blog",
  "total": 10,
  "posts": [
    {
      "title": "...",
      "slug": "...",
      "type": "post",
      "excerpt": "...",
      "body": "<p>...</p>",
      "thumbnail_path": "images/...",
      "categories": ["..."],
      "tags": ["..."],
      ...
    }
  ]
}
```

## Import ke Laravel

Setelah scraping selesai, gunakan file `scraped_posts.json` untuk import via:
- Admin panel: `/lanyardkilat/posts` → klik "Import"
- Atau gunakan fitur import yang sudah ada

