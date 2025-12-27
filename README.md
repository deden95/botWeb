# Bot Scraper Blog LanyardKilat

Bot untuk scraping blog posts dari https://lanyardkilat.co.id/blog dan menyimpan ke format JSON yang sesuai untuk import ke Laravel.

## Instalasi

1. Install Python 3.8+ jika belum ada
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Cara Menggunakan

### Basic Usage
```bash
python scrape_blog.py
```

### Dengan Custom URL
```bash
python scrape_blog.py --url https://lanyardkilat.co.id/blog
```

### Dengan Limit Halaman
```bash
python scrape_blog.py --max-pages 5
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

