# FOA Extract

CLI tool that extracts Funding Opportunity Announcement (FOA) metadata from Grants.gov and NSF pages, applies deterministic keyword tagging with while also trying completely optional TF-IDF classification, and exports results as JSON and CSV.

---

## Requirements

- Python 3.10+
- Google Chrome (used by Selenium for JavaScript-rendered pages)

---

## Setup

```bash
git clone <repo-url>
cd FOA

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

---

## Usage

```bash
python main.py --url "https://www.grants.gov/search-results-detail/353584"
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--url` | required | Grants.gov or NSF opportunity URL |
| `--out-dir` | `./out` | Directory to write output files |
| `--format` | `all` | Output format: `json`, `csv`, or `all` |
| `--no-nlp` | off | Skip TF-IDF tagging, use keyword matching only |
| `--verbose` | off | Enable debug logging |

**Examples:**

```bash
# Export only JSON
python main.py --url "<URL>" --format json

# Custom output directory
python main.py --url "<URL>" --out-dir ./results

# Faster run without NLP
python main.py --url "<URL>" --no-nlp
```

---

## Output

Files are written to `./out/` by default:

- `foa.json` — structured metadata as JSON
- `foa.csv` — same data in tabular format

```json
{
  "foa_id": "GRANTS-353584",
  "title": "...",
  "agency": "...",
  "open_date": "2026-01-01",
  "close_date": "2026-06-01",
  "description": "...",
  "tags": ["Artificial Intelligence", "Health"],
  "source_url": "https://www.grants.gov/...",
  "award_ceiling": "500000",
  "award_floor": "50000"
}
```

---

## Project Structure

```
FOA/
├── main.py              # Entry point
├── requirements.txt
├── README.md
├── foa_extract/
│   ├── __init__.py
│   ├── models.py        # Pydantic data models
│   ├── ingestor.py      # Scraping (Grants.gov + NSF)
│   ├── tagger.py        # Keyword + TF-IDF tagging
│   └── exporter.py      # JSON/CSV export
└── out/                 # Output files (generated)
```

---

## License

MIT
