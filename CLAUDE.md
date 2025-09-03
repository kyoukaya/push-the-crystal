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
  - `get_ranking()`: Fetches ranking pages for data centers
  - `get_player()`: Fetches individual player character pages  
  - `worker()`: Async worker for processing player data in parallel

### Data Flow

1. Scrapes ranking pages for each data center (Chaos, Materia, Primal, Gaia)
2. Parses player ranking data from HTML using BeautifulSoup
3. Asynchronously fetches individual player pages to get job/class data
4. Saves all player data to CSV file in `archive/` directory with YYYY_MM_DD.csv format

### Rate Limiting & Error Handling

- Rate limited to 2 calls/second for rankings, 3 calls/second for player pages
- Exponential backoff retry logic with up to 8 attempts
- Comprehensive error handling for HTTP errors and parsing failures

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