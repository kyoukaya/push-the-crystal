# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python web scraper that automatically collects FFXIV Crystalline Conflict PVP rankings from the official FFXIV Lodestone. The scraper runs daily via GitHub Actions and saves historical ranking data to CSV files.

## Commands

### Running the scraper
```bash
python main.py
```

### Installing dependencies
```bash
pip install -r requirements.txt
```

### Running tests
```bash
python -m unittest test_main.py
```
Tests use `unittest` (including `IsolatedAsyncioTestCase` for async functions) and mock `httpx.AsyncClient` rather than hitting the live Lodestone site. `test_data/` contains real saved HTML pages (`ranking_elemental.html`, `player_28151111.html`) for reference when updating parsing logic, though they aren't currently loaded by `test_main.py`.

### Code formatting (if needed)
```bash
autopep8 --in-place --recursive .
```

## Architecture

### Core Components

- **main.py**: Single-file application containing all scraping logic
- **Player class**: Data structure representing a ranked player with parsing methods
  - `parse_rankings()`: Extracts player data from ranking pages
  - `parse_job()`: Extracts job/class information from player character pages
- **Async scraping system**: Uses httpx with rate limiting and retry logic
  - `get_data_centers()`: Discovers the current list of data centers from the main ranking page (not hardcoded)
  - `get_ranking()`: Fetches ranking pages for a given data center/page
  - `get_player()`: Fetches individual player character pages
  - `worker()`: Async worker pool (3 workers) consuming a queue to fetch/parse player jobs in parallel

### Data Flow

1. Discovers data centers dynamically by parsing `dcgroup=` links off the main crystalline conflict ranking page
2. Scrapes ranking pages 1-6 per data center, stopping early for a DC once a page returns zero players
3. Parses player ranking data from HTML using BeautifulSoup
4. Asynchronously fetches individual player pages to get job/class data
5. Saves all player data to a CSV file in `archive/` directory named `YYYY_MM_DD.csv` (UTC date) — as long as at least one player was scraped, this happens regardless of whether sanity checks below passed
6. Returns `False` from `main()` (and a non-zero process exit code) if any sanity check failed, so a bad run still leaves data behind but is visible as a failure

### Rate Limiting & Error Handling

- Rate limited to 2 calls/second for rankings, 3 calls/second for player pages
- Exponential backoff retry logic with up to 8 attempts
- Comprehensive error handling for HTTP errors and parsing failures
- Sanity checks (too few data centers found, duplicate player IDs via `check_duplicate_player_ids()`, unrecognized job icons via `count_unknown_jobs()`) are collected as non-fatal issues rather than raised — the run always archives whatever it collected, then exits non-zero if any issue was found. This intentionally decouples "did we get data" from "was the data trustworthy," since failing fast would have meant losing a day's archive instead of just flagging it.
- The GitHub Actions workflow relies on this: the scrape step uses `continue-on-error: true` so the commit step still runs and archives partial/flagged data, then a final step fails the job if the scrape step's outcome was a failure — keeping the archive committed while still surfacing the failure in CI

### Data Structure

The CSV output contains these fields:
- Basic info: name, id, world, dc (data center)
- Ranking: cur_rank, prev_rank, points, points_delta
- PvP stats: wins, wins_delta, tier
- Character: portrait (image path), job (class abbreviation)

### Automation

GitHub Actions workflow (`.github/workflows/update.yml`) runs daily at 10:30 UTC to automatically update rankings and commit results to the repository.

## Development Notes

- Uses Python 3.13+ 
- HTML parsing relies on specific CSS class selectors from FFXIV Lodestone
- Job icons mapped via hardcoded URL-to-abbreviation dictionary
- Test data available in `test_data/` directory for development
- Archive contains daily CSV files dating back to 2022