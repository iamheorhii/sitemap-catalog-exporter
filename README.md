# Sitemap Catalog Exporter

A universal Python script that extracts product data from any online shop using its `sitemap.xml` and exports the results to Excel.

This tool is designed for fast catalog extraction without relying on APIs, admin access, or platform-specific integrations.

---

## What This Script Does

- Reads a website’s sitemap (`sitemap.xml` or sitemap index)
- Recursively processes child sitemaps if present
- Filters product URLs using custom rules
- Visits each product page
- Extracts:
  - Product title
  - Price
  - Currency
  - Stock status
  - URL
- Exports everything into a clean Excel file

---

## Output File Format

```
domain_catalog.xlsx
```

---

## Requirements

- Python 3.9+
- Internet connection

Install dependencies:

```bash
pip install requests beautifulsoup4 lxml pandas openpyxl tqdm
```

---

## How to Find a Sitemap

Most websites have one of the following:

```
https://example.com/sitemap.xml
https://example.com/sitemap_index.xml
```

If not, check:

```
https://example.com/robots.txt
```

Look for a line starting with:

```
Sitemap:
```

---

## How to Use

Run the script:

```bash
python sitemap_catalog_exporter.py
```

You will be prompted to enter:

- Sitemap URL
- Product URL marker (optional)
- Include keywords (optional)
- Exclude keywords (optional)
- Whether to keep only in-stock items
- Request delay between pages
- Optional page limit

After processing, an Excel file will be generated in the same folder.

---

## Filtering Logic Explained

### Product URL Marker

Examples:

```
/product/
/a-
/p/
```

If provided, only URLs containing this marker will be processed.

---

### Include Keywords

Only URLs containing at least one of these keywords will be included.

Example:

```
frezen,frees,vhm
```

---

### Exclude Keywords

Exclude URLs containing these keywords.

Example:

```
blog,news,account
```

---

## Stock Detection

The script uses common phrases to detect availability.

Out-of-stock examples:

- out of stock  
- sold out  
- niet op voorraad  

In-stock examples:

- in stock  
- op voorraad  
- add to cart  

These lists can be extended inside the script if needed.

---

## Supported Shops

The script works best for shops that:

- Render prices server-side
- Use schema.org product markup
- Include price directly in page HTML

Works well with:

- WooCommerce  
- Shopify (non-JS-only themes)  
- Magento  
- Lightspeed  
- Custom PHP shops  

If a shop loads prices dynamically via JavaScript, browser automation (Playwright/Selenium) would be required.

---

## Example Use Cases

- Build competitor product lists  
- Extract supplier catalogs  
- Analyze product pricing  
- Generate internal inventory reports  
- Prepare bulk import data  

---

## Ethical Use Notice

Only use this tool on:

- Your own websites  
- Publicly accessible websites  
- Websites where scraping is legally permitted  

Always respect robots.txt and website terms of service.

---

## Limitations

- JavaScript-rendered prices may not be detected  
- Highly customized sites may require selector adjustments  
- Very large sitemaps may take time to process  

---
