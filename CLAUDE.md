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

Everything lives in `main.py` (single-file application). Function/method docstrings there describe behavior — start with:
- **Player class**: `parse_rankings()`, `parse_job()`
- **Async scraping**: `get_data_centers()`, `get_ranking()`, `get_player()`, `worker()`

### Data Flow

1. `get_data_centers()` discovers data centers dynamically from the main ranking page
2. `get_ranking()` + `Player.parse_rankings()` scrape ranking pages 1-6 per data center, stopping early once a page returns zero players
3. `worker()` + `Player.parse_job()` asynchronously fetch each player's character page for job/class data
4. `save_rankings()` writes everything to `archive/YYYY_MM_DD.csv` (UTC date)

### Rate Limiting & Error Handling

- Rate limited to 2 calls/second for rankings, 3 calls/second for player pages
- Exponential backoff retry logic with up to 8 attempts
- Comprehensive error handling for HTTP errors and parsing failures
- Sanity checks (data center count, duplicate player IDs, unrecognized job icons) are non-fatal — see the `main()` docstring in main.py and the comments in `update.yml` for how archiving vs. CI failure are decoupled

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