import unittest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# Add the current directory to the path to import main
sys.path.insert(0, os.path.dirname(__file__))

from main import (
    Player,
    get_data_centers,
    parse_rankings,
    check_duplicate_player_ids,
    count_unknown_jobs,
)
from bs4 import BeautifulSoup
import httpx


class TestPlayer(unittest.TestCase):
    def test_player_creation(self):
        """Test that Player objects can be created."""
        player = Player()
        self.assertIsInstance(player, Player)

    def test_parse_rankings_basic(self):
        """Test parsing basic ranking HTML."""
        # Create a mock HTML structure based on the actual structure
        html = """
        <div class="ranking_set" data-href="/lodestone/character/12345/">
            <h3>Test Player</h3>
            <div class="order">1</div>
            <div class="prev_order">2</div>
            <div class="world">TestWorld [TestDC]</div>
            <div class="points">1000 +50</div>
            <div class="face-wrapper">
                <img src="https://img2.finalfantasyxiv.com/f/test_portrait.jpg"/>
            </div>
            <div class="tier">
                <img data-tooltip="Crystal"/>
            </div>
            <div class="wins">100 +5</div>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        ranking_div = soup.find(class_="ranking_set")
        
        player = Player()
        player.parse_rankings(ranking_div)
        
        self.assertEqual(player.name, "Test Player")
        self.assertEqual(player.id, 12345)
        self.assertEqual(player.cur_rank, 1)
        self.assertEqual(player.prev_rank, 2)
        self.assertEqual(player.world, "TestWorld")
        self.assertEqual(player.dc, "TestDC")
        self.assertEqual(player.points, 1000)
        self.assertEqual(player.points_delta, 50)
        self.assertEqual(player.portrait, "test_portrait.jpg")
        self.assertEqual(player.tier, "Crystal")
        self.assertEqual(player.wins, 100)
        self.assertEqual(player.wins_delta, 5)


class TestParseJob(unittest.TestCase):
    def test_parse_job_known_icon(self):
        """A known job icon URL should map to the correct job abbreviation."""
        html = """
        <div class="character__class_icon">
            <img src="https://img.finalfantasyxiv.com/h/E/d0Tx-vhnsMYfYpGe9MvslemEfg.png"/>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        player = Player()
        self.assertFalse(player.parse_job(soup))
        self.assertEqual(player.job, "PLD")

    def test_parse_job_unknown_icon(self):
        """An icon URL missing from jobicomap should fall back to UNK and report a real mapping gap."""
        html = """
        <div class="character__class_icon">
            <img src="https://img.finalfantasyxiv.com/h/Z/not_a_real_job_icon.png"/>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        player = Player()
        self.assertTrue(player.parse_job(soup))
        self.assertEqual(player.job, "UNK")

    def test_parse_job_missing_icon(self):
        """A page with no class icon at all (e.g. a blocked fetch) should fall back to UNK without reporting a mapping gap."""
        soup = BeautifulSoup("<html><body></body></html>", 'html.parser')
        player = Player()
        self.assertFalse(player.parse_job(soup))
        self.assertEqual(player.job, "UNK")


class TestUnknownJobDetection(unittest.TestCase):
    def _make_player(self, job: str) -> Player:
        player = Player()
        player.job = job
        return player

    def test_counts_only_unk(self):
        players = [
            self._make_player("PLD"),
            self._make_player("UNK"),
            self._make_player("WHM"),
            self._make_player("UNK"),
        ]
        self.assertEqual(count_unknown_jobs(players), 2)

    def test_zero_when_all_known(self):
        players = [self._make_player("PLD"), self._make_player("WHM")]
        self.assertEqual(count_unknown_jobs(players), 0)


class TestDataCenterParsing(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock(spec=httpx.AsyncClient)

    async def test_get_data_centers_success(self):
        """Test successful data center parsing."""
        mock_html = """
        <html>
        <body>
            <div class="cc-ranking__select__data_center__list">
                <ul>
                    <li><a href="/lodestone/ranking/crystallineconflict/?dcgroup=Chaos">Europe / Chaos</a></li>
                    <li><a href="/lodestone/ranking/crystallineconflict/?dcgroup=Materia">Oceania / Materia</a></li>
                    <li><a href="/lodestone/ranking/crystallineconflict/?dcgroup=Dynamis">North America / Dynamis</a></li>
                    <li><a href="/lodestone/ranking/crystallineconflict/?dcgroup=Elemental">Japan / Elemental</a></li>
                </ul>
            </div>
        </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        self.client.get.return_value = mock_response
        
        dcs = await get_data_centers(self.client)
        
        expected_dcs = ['Chaos', 'Materia', 'Dynamis', 'Elemental']
        self.assertEqual(sorted(dcs), sorted(expected_dcs))

    async def test_get_data_centers_http_error(self):
        """Test handling of HTTP errors when fetching data centers."""
        mock_response = Mock()
        mock_response.status_code = 500
        self.client.get.return_value = mock_response
        
        with self.assertRaises(httpx.HTTPError):
            await get_data_centers(self.client)

    async def test_get_data_centers_no_links(self):
        """Test handling when no data center links are found."""
        mock_html = "<html><body><p>No links here</p></body></html>"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        self.client.get.return_value = mock_response
        
        dcs = await get_data_centers(self.client)
        self.assertEqual(dcs, [])


class TestDuplicateDetection(unittest.TestCase):
    def _make_player(self, pid: int, name: str) -> Player:
        player = Player()
        player.id = pid
        player.name = name
        return player

    def test_duplicate_detection_logic(self):
        """check_duplicate_player_ids should report ids appearing more than once."""
        players = [
            self._make_player(123, "Player One"),
            self._make_player(456, "Player Two"),
            self._make_player(123, "Player One Duplicate"),
        ]

        duplicates = check_duplicate_player_ids(players)

        self.assertEqual(duplicates, {123: 2})

    def test_no_duplicates(self):
        """check_duplicate_player_ids should return an empty mapping when all ids are unique."""
        players = [
            self._make_player(123, "Player One"),
            self._make_player(456, "Player Two"),
            self._make_player(789, "Player Three"),
        ]

        duplicates = check_duplicate_player_ids(players)

        self.assertEqual(duplicates, {})


class TestMainIntegration(unittest.TestCase):
    def test_parse_rankings_multiple_players(self):
        """Test parsing multiple players from ranking HTML."""
        html = """
        <div class="ranking_set" data-href="/lodestone/character/111/">
            <h3>Player One</h3>
            <div class="order">1</div>
            <div class="prev_order">-</div>
            <div class="world">World1 [DC1]</div>
            <div class="points">1000</div>
            <div class="face-wrapper">
                <img src="https://img2.finalfantasyxiv.com/f/portrait1.jpg"/>
            </div>
            <div class="tier">
                <img data-tooltip="Crystal"/>
            </div>
            <div class="wins">100</div>
        </div>
        <div class="ranking_set" data-href="/lodestone/character/222/">
            <h3>Player Two</h3>
            <div class="order">2</div>
            <div class="prev_order">3</div>
            <div class="world">World2 [DC2]</div>
            <div class="points">950 -10</div>
            <div class="face-wrapper">
                <img src="https://img2.finalfantasyxiv.com/f/portrait2.jpg"/>
            </div>
            <div class="tier">
                <img data-tooltip="Diamond"/>
            </div>
            <div class="wins">95 +2</div>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        players = parse_rankings(soup)
        
        self.assertEqual(len(players), 2)
        
        # Check first player
        self.assertEqual(players[0].name, "Player One")
        self.assertEqual(players[0].id, 111)
        self.assertEqual(players[0].cur_rank, 1)
        self.assertEqual(players[0].prev_rank, 0)  # "-" becomes 0
        self.assertEqual(players[0].dc, "DC1")
        
        # Check second player
        self.assertEqual(players[1].name, "Player Two")
        self.assertEqual(players[1].id, 222)
        self.assertEqual(players[1].cur_rank, 2)
        self.assertEqual(players[1].prev_rank, 3)
        self.assertEqual(players[1].dc, "DC2")


class TestAsyncMethods(unittest.IsolatedAsyncioTestCase):
    """Test class for async methods using IsolatedAsyncioTestCase."""
    
    async def test_get_data_centers_async(self):
        """Test get_data_centers as an async method."""
        client = AsyncMock(spec=httpx.AsyncClient)
        
        mock_html = """
        <html>
        <body>
            <a href="/lodestone/ranking/crystallineconflict/?dcgroup=TestDC1">Test DC 1</a>
            <a href="/lodestone/ranking/crystallineconflict/?dcgroup=TestDC2&other=param">Test DC 2</a>
        </body>
        </html>
        """
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        client.get.return_value = mock_response
        
        dcs = await get_data_centers(client)
        
        # Should extract unique DC names
        expected_dcs = ['TestDC1', 'TestDC2']
        self.assertEqual(sorted(dcs), sorted(expected_dcs))


if __name__ == '__main__':
    unittest.main()