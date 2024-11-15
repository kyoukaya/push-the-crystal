from statistics import median
from typing import Any, List, Tuple
from bs4 import BeautifulSoup
import httpx
import time
import csv
import asyncio
from urllib.parse import urlparse
import logging as logs
from ratelimit import limits, sleep_and_retry
from backoff import on_exception, expo
from datetime import datetime
import pytz
import concurrent.futures

logs.basicConfig(
    encoding="utf-8",
    level=logs.INFO,
    filemode="w",
    format="[%(levelname)s]%(asctime)s - %(message)s",
    datefmt="%d-%m-%y %H:%M:%S",
)

# TODO: automatically get DC groups by parsing the first page.
dcs = [
    "Chaos",
    "Materia",
    "Primal",
    "Gaia",
]

region = "eu"  # na/eu - eu has marginally faster pageload speeds
base_url = f"https://{region}.finalfantasyxiv.com"

# host https://img.finalfantasyxiv.com stripped
jobicomap = {
    "/h/U/F5JzG9RPIKFSogtaKNBk455aYA.png": "GLA",
    "/h/V/iW7IBKQ7oglB9jmbn6LwdZXkWw.png": "PGL",
    "/h/N/St9rjDJB3xNKGYg-vwooZ4j6CM.png": "MRD",
    "/h/k/tYTpoSwFLuGYGDJMff8GEFuDQs.png": "LNC",
    "/h/Q/ZpqEJWYHj9SvHGuV9cIyRNnIkk.png": "ARC",
    "/h/s/gl62VOTBJrm7D_BmAZITngUEM8.png": "CNJ",
    "/h/4/IM3PoP6p06GqEyReygdhZNh7fU.png": "THM",
    "/h/v/YCN6F-xiXf03Ts3pXoBihh2OBk.png": "CRP",
    "/h/5/EEHVV5cIPkOZ6v5ALaoN5XSVRU.png": "BSM",
    "/h/G/Rq5wcK3IPEaAB8N-T9l6tBPxCY.png": "ARM",
    "/h/L/LbEjgw0cwO_2gQSmhta9z03pjM.png": "GSM",
    "/h/b/ACAcQe3hWFxbWRVPqxKj_MzDiY.png": "LTW",
    "/h/X/E69jrsOMGFvFpCX87F5wqgT_Vo.png": "WVR",
    "/h/C/bBVQ9IFeXqjEdpuIxmKvSkqalE.png": "ALC",
    "/h/m/1kMI2v_KEVgo30RFvdFCyySkFo.png": "CUL",
    "/h/A/aM2Dd6Vo4HW_UGasK7tLuZ6fu4.png": "MIN",
    "/h/I/jGRnjIlwWridqM-mIPNew6bhHM.png": "BTN",
    "/h/x/B4Azydbn7Prubxt7OL9p1LZXZ0.png": "FSH",
    "/h/E/d0Tx-vhnsMYfYpGe9MvslemEfg.png": "PLD",
    "/h/K/HW6tKOg4SOJbL8Z20GnsAWNjjM.png": "MNK",
    "/h/y/A3UhbjZvDeN3tf_6nJ85VP0RY0.png": "WAR",
    "/h/m/gX4OgBIHw68UcMU79P7LYCpldA.png": "DRG",
    "/h/F/KWI-9P3RX_Ojjn_mwCS2N0-3TI.png": "BRD",
    "/h/7/i20QvSPcSQTybykLZDbQCgPwMw.png": "WHM",
    "/h/P/V01m8YRBYcIs5vgbRtpDiqltSE.png": "BLM",
    "/h/e/VYP1LKTDpt8uJVvUT7OKrXNL9E.png": "ACN",
    "/h/h/4ghjpyyuNelzw1Bl0sM_PBA_FE.png": "SMN",
    "/h/7/WdFey0jyHn9Nnt1Qnm-J3yTg5s.png": "SCH",
    "/h/y/wdwVVcptybfgSruoh8R344y_GA.png": "ROG",
    "/h/0/Fso5hanZVEEAaZ7OGWJsXpf3jw.png": "NIN",
    "/h/E/vmtbIlf6Uv8rVp2YFCWA25X0dc.png": "MCH",
    "/h/l/5CZEvDOMYMyVn2td9LZigsgw9s.png": "DRK",
    "/h/1/erCgjnMSiab4LiHpWxVc-tXAqk.png": "AST",
    "/h/m/KndG72XtCFwaq1I1iqwcmO_0zc.png": "SAM",
    "/h/q/s3MlLUKmRAHy0pH57PnFStHmIw.png": "RDM",
    "/h/p/jdV3RRKtWzgo226CC09vjen5sk.png": "BLU",
    "/h/8/hg8ofSSOKzqng290No55trV4mI.png": "GNB",
    "/h/t/HK0jQ1y7YV9qm30cxGOVev6Cck.png": "DNC",
    "/h/7/cLlXUaeMPJDM2nBhIeM-uDmPzM.png": "RPR",
    "/h/g/_oYApASVVReLLmsokuCJGkEpk0.png": "SGE",
    "/h/C/WojNTqMJ_Ye1twvkIhw825zc20.png": "VPR",
    "/h/_/kLob-U-yh652LQPX1NHpLlUYQY.png": "PCT",
}


class Player:
    name: str
    id: int
    cur_rank: int
    prev_rank: int
    world: str
    dc: str
    points: int
    points_delta: int
    portrait: str  # prefix stripped https://img2.finalfantasyxiv.com/f/
    tier: str
    wins: int
    wins_delta: int
    job: str

    def __str__(self) -> str:
        return (
            f"Name:{self.name} ({self.world} [{self.dc}]) {self.tier} "
            "({self.prev_rank} -> {self.cur_rank})\nwins: {self.wins} pts: {self.points}\n"
            "portrait: {self.portrait} id: {self.id}"
        )

    def parse_rankings(self, v: BeautifulSoup):
        self.name = v.h3.text
        if len(self.name) == 0:
            raise Exception(f"name cannot be empty: {v.prettify()}")
        # data-href should be of form '/lodestone/character/123456/'
        self.id = int(v["data-href"].removeprefix("/lodestone/character/").strip("/"))
        self.cur_rank = int(v.find(class_="order").text.strip())
        try:
            self.prev_rank = int(v.find(class_="prev_order").text.strip())
        except ValueError:
            self.prev_rank = 0
        self.world, player_dc = v.find(class_="world").text.split(" ")
        if len(self.world) == 0:
            raise Exception(f"world cannot be empty: {v.prettify()}")
        self.dc = player_dc.strip("[]")
        if len(self.dc) == 0:
            raise Exception(f"dc cannot be empty: {v.prettify()}")
        try:
            self.points, self.points_delta = parse_points_or_wins(
                v.find(class_="points").text.strip()
            )
        except ValueError:
            self.points, self.points_delta = 0, 0
        self.portrait = (
            v.find(class_="face-wrapper")
            .img["src"]
            .removeprefix("https://img2.finalfantasyxiv.com/f/")
        )
        if len(self.portrait) == 0:
            raise Exception(f"portrait cannot be empty: {v.prettify()}")
        try:
            self.tier = v.find(class_="tier").img["data-tooltip"]
        except TypeError:
            self.tier = "None"

        if len(self.tier) == 0:
            raise Exception(f"tier cannot be empty: {v.prettify()}")
        try:
            self.wins, self.wins_delta = parse_points_or_wins(
                v.find(class_="wins").text.strip()
            )
        except ValueError:
            self.wins, self.wins_delta = 0, 0

    def parse_job(self, v: BeautifulSoup):
        try:
            url = urlparse(v.find(class_="character__class_icon").img["src"])
            self.job = jobicomap[url.path]
        except Exception as e:
            logs.error(f"failed to parse job: {e}")
            self.job = "UNK"


def parse_points_or_wins(s: str) -> Tuple[int, int]:
    if len(s) == 0:
        raise ValueError()
    tmp = s.split(" ")
    if len(tmp) == 1:
        return (int(tmp[0]), 0)
    return (int(tmp[0]), int(tmp[1]))


@sleep_and_retry
@on_exception(expo, httpx.HTTPError, max_tries=8)
@limits(calls=2, period=1)
async def get_ranking(client: httpx.AsyncClient, dc: str, page: int) -> str:
    r = await client.get(
        f"{base_url}/lodestone/ranking/crystallineconflict/?dcgroup={dc}&page={page}"
    )
    if r.status_code != 200:
        logs.error(f"get_ranking({dc},{page}): http status code: {r.status_code}")
        raise httpx.HTTPError(str(r.status_code))
    return r.text


get_player_stats = []


@sleep_and_retry
@on_exception(expo, httpx.HTTPError, max_tries=8)
@limits(calls=3, period=1)
async def get_player(client: httpx.AsyncClient, pid: int) -> str:
    r = await client.get(f"{base_url}/lodestone/character/{pid}")
    if r.status_code == 403:
        return ""
    if r.status_code != 200:
        logs.error(f"get_player({pid}): http status code: {r.status_code}")
        raise httpx.HTTPError(str(r.status_code))
    get_player_stats.append(r.elapsed.total_seconds())
    return r.text


def parse_rankings(v: BeautifulSoup) -> List[Player]:
    players: List[Player] = []
    for v in v.find_all(class_="ranking_set"):
        p = Player()
        p.parse_rankings(v)
        players.append(p)
    return players


def save_rankings(players: List[Player]):
    filename = "./archive/" + datetime.now(pytz.utc).strftime("%Y_%m_%d.csv")
    with open(filename, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, vars(players[0]).keys())
        w.writeheader()
        for player in players:
            w.writerow(vars(player))


async def worker(
    name: str, queue: asyncio.Queue, client: httpx.AsyncClient, n_players: int
):
    while True:
        try:
            # Get task from queue
            i, player = await queue.get()

            try:
                logs.info(
                    f"Worker {name}: parsing player {player.name}: {player.id} "
                    f"({i / n_players * 100:.1f}%)"
                )
                player_resp = await get_player(client, player.id)
                player.parse_job(BeautifulSoup(player_resp, "html.parser"))
            finally:
                # Always mark task as done, even if it fails
                queue.task_done()
        except asyncio.CancelledError:
            break


async def main():
    logs.info("parser started")
    t0 = time.time()
    players: List[Player] = []

    async with httpx.AsyncClient(http2=True) as client:
        # Fetch all players first
        for dc in dcs:
            for page in range(1, 7):
                logs.info(f"start parsing dc {dc} page {page}")
                dc_resp = await get_ranking(client, dc, page)
                new_players = parse_rankings(BeautifulSoup(dc_resp, "html.parser"))
                players.extend(new_players)
                if len(new_players) != 50:
                    logs.warning(
                        f"total number of players in dc {dc} is {len(new_players)}, not 100"
                    )
                    break

            logs.info(f"parsed rankings for {dc}")

        n_players = len(players)

        # Create a queue for tasks
        queue = asyncio.Queue()

        workers = [
            asyncio.create_task(worker(f"worker-{i}", queue, client, n_players))
            for i in range(3)
        ]

        # Add all players to the queue
        for i, player in enumerate(players):
            await queue.put((i, player))

        # Wait for all tasks to complete
        await queue.join()

        # Cancel workers
        for w in workers:
            w.cancel()

        # Wait for workers to finish
        await asyncio.gather(*workers, return_exceptions=True)

    save_rankings(players)
    logs.info(f"parsing finished, total time taken {time.time() - t0}s")
    logs.info(
        f"get_player_stats: {min(get_player_stats)}, {max(get_player_stats)}, {median(get_player_stats)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
