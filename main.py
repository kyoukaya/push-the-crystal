from typing import List
from bs4 import BeautifulSoup
import httpx
import time
import csv
from urllib.parse import urlparse
import logging as logs
from ratelimit import limits, sleep_and_retry
from backoff import on_exception, expo
from datetime import datetime
import pytz
import os
import shutil

logs.basicConfig(encoding='utf-8', level=logs.DEBUG,
                 filemode='w',
                 format='[%(levelname)s]%(asctime)s - %(message)s',
                 datefmt='%d-%m-%y %H:%M:%S')

dcs = [
    "Aether",
    "Chaos",
    "Crystal",
    "Elemental",
    "Gaia",
    "Light",
    "Mana",
    "Materia",
    "Primal",
]

region = "eu"  # or na
base_url = f"https://{region}.finalfantasyxiv.com"

# host https://img.finalfantasyxiv.com stripped
jobicomap = {
    "/lds/h/U/F5JzG9RPIKFSogtaKNBk455aYA.png": "GLA",
    "/lds/h/V/iW7IBKQ7oglB9jmbn6LwdZXkWw.png": "PGL",
    "/lds/h/N/St9rjDJB3xNKGYg-vwooZ4j6CM.png": "MRD",
    "/lds/h/k/tYTpoSwFLuGYGDJMff8GEFuDQs.png": "LNC",
    "/lds/h/Q/ZpqEJWYHj9SvHGuV9cIyRNnIkk.png": "ARC",
    "/lds/h/s/gl62VOTBJrm7D_BmAZITngUEM8.png": "CNJ",
    "/lds/h/4/IM3PoP6p06GqEyReygdhZNh7fU.png": "THM",
    "/lds/h/v/YCN6F-xiXf03Ts3pXoBihh2OBk.png": "CRP",
    "/lds/h/5/EEHVV5cIPkOZ6v5ALaoN5XSVRU.png": "BSM",
    "/lds/h/G/Rq5wcK3IPEaAB8N-T9l6tBPxCY.png": "ARM",
    "/lds/h/L/LbEjgw0cwO_2gQSmhta9z03pjM.png": "GSM",
    "/lds/h/b/ACAcQe3hWFxbWRVPqxKj_MzDiY.png": "LTW",
    "/lds/h/X/E69jrsOMGFvFpCX87F5wqgT_Vo.png": "WVR",
    "/lds/h/C/bBVQ9IFeXqjEdpuIxmKvSkqalE.png": "ALC",
    "/lds/h/m/1kMI2v_KEVgo30RFvdFCyySkFo.png": "CUL",
    "/lds/h/A/aM2Dd6Vo4HW_UGasK7tLuZ6fu4.png": "MIN",
    "/lds/h/I/jGRnjIlwWridqM-mIPNew6bhHM.png": "BTN",
    "/lds/h/x/B4Azydbn7Prubxt7OL9p1LZXZ0.png": "FSH",
    "/lds/h/E/d0Tx-vhnsMYfYpGe9MvslemEfg.png": "PLD",
    "/lds/h/K/HW6tKOg4SOJbL8Z20GnsAWNjjM.png": "MNK",
    "/lds/h/y/A3UhbjZvDeN3tf_6nJ85VP0RY0.png": "WAR",
    "/lds/h/m/gX4OgBIHw68UcMU79P7LYCpldA.png": "DRG",
    "/lds/h/F/KWI-9P3RX_Ojjn_mwCS2N0-3TI.png": "BRD",
    "/lds/h/7/i20QvSPcSQTybykLZDbQCgPwMw.png": "WHM",
    "/lds/h/P/V01m8YRBYcIs5vgbRtpDiqltSE.png": "BLM",
    "/lds/h/e/VYP1LKTDpt8uJVvUT7OKrXNL9E.png": "ACN",
    "/lds/h/h/4ghjpyyuNelzw1Bl0sM_PBA_FE.png": "SMN",
    "/lds/h/7/WdFey0jyHn9Nnt1Qnm-J3yTg5s.png": "SCH",
    "/lds/h/y/wdwVVcptybfgSruoh8R344y_GA.png": "ROG",
    "/lds/h/0/Fso5hanZVEEAaZ7OGWJsXpf3jw.png": "NIN",
    "/lds/h/E/vmtbIlf6Uv8rVp2YFCWA25X0dc.png": "MCH",
    "/lds/h/l/5CZEvDOMYMyVn2td9LZigsgw9s.png": "DRK",
    "/lds/h/1/erCgjnMSiab4LiHpWxVc-tXAqk.png": "AST",
    "/lds/h/m/KndG72XtCFwaq1I1iqwcmO_0zc.png": "SAM",
    "/lds/h/q/s3MlLUKmRAHy0pH57PnFStHmIw.png": "RDM",
    "/lds/h/p/jdV3RRKtWzgo226CC09vjen5sk.png": "BLU",
    "/lds/h/8/hg8ofSSOKzqng290No55trV4mI.png": "GNB",
    "/lds/h/t/HK0jQ1y7YV9qm30cxGOVev6Cck.png": "DNC",
    "/lds/h/7/cLlXUaeMPJDM2nBhIeM-uDmPzM.png": "RPR",
    "/lds/h/g/_oYApASVVReLLmsokuCJGkEpk0.png": "SGE",
}


class Player:
    name: str
    id: int
    cur_rank: int
    prev_rank: int
    world: str
    dc: str
    points: int
    portrait: str  # prefix stripped https://img2.finalfantasyxiv.com/f/
    tier: str
    wins: int
    job: str

    def __str__(self) -> str:
        return f"Name:{self.name} ({self.world} [{self.dc}]) {self.tier} ({self.prev_rank} -> {self.cur_rank})\nwins: {self.wins} pts: {self.points}\nportrait: {self.portrait} id: {self.id}"

    def parse_rankings(self, v: BeautifulSoup):
        self.name = v.h3.text
        if len(self.name) == 0:
            raise Exception(f"name cannot be empty: {v.prettify()}")
        # data-href should be of form '/lodestone/character/123456/'
        self.id = int(
            v["data-href"].removeprefix("/lodestone/character/").strip("/"))
        self.cur_rank = int(v.find(class_="order").text.strip())
        try:
            self.prev_rank = int(v.find(class_="prev_order").text.strip())
        except ValueError as e:
            self.prev_rank = 0
        self.world, player_dc = v.find(
            class_="xiv-lds-home-world").next.split(" ")
        if len(self.world) == 0:
            raise Exception(f"world cannot be empty: {v.prettify()}")
        self.dc = player_dc.strip("[]")
        if len(self.dc) == 0:
            raise Exception(f"dc cannot be empty: {v.prettify()}")
        try:
            self.points = int(v.find(class_="points").text.strip())
        except ValueError as e:
            self.points = 0
        self.portrait = v.img["src"].removeprefix(
            "https://img2.finalfantasyxiv.com/f/")
        if len(self.portrait) == 0:
            raise Exception(f"portrait cannot be empty: {v.prettify()}")
        self.tier = v.find(class_="tier").img["data-tooltip"]
        if len(self.tier) == 0:
            raise Exception(f"tier cannot be empty: {v.prettify()}")
        try:
            self.wins = int(v.find(class_="wins").text.strip())
        except ValueError as e:
            self.wins = 0

    def parse_job(self, v: BeautifulSoup):
        url = urlparse(v.find(class_="character__class_icon").img["src"])
        try:
            self.job = jobicomap[url.path]
        except KeyError:
            logs.error(f"unknown jobicon url: {url.path}")
            self.job = "UNK"


@sleep_and_retry
@on_exception(expo, httpx.HTTPError, max_tries=8)
@limits(calls=2, period=1)
def get_ranking(client: httpx.Client, dc: str) -> str:
    r = client.get(
        f"{base_url}/lodestone/ranking/crystallineconflict/?dcgroup={dc}")
    if r.status_code != 200:
        logs.error(f"get_ranking({dc}): http status code: {r.status_code}")
        raise httpx.HTTPError(r.status_code)
    logs.info(f"get_ranking({dc}) in {r.elapsed}s")
    return r.text


@sleep_and_retry
@on_exception(expo, httpx.HTTPError, max_tries=8)
@limits(calls=2, period=1)
def get_player(client: httpx.Client, pid: int) -> str:
    r = client.get(f"{base_url}/lodestone/character/{pid}")
    if r.status_code != 200:
        logs.error(f"get_player({pid}): http status code: {r.status_code}")
        raise httpx.HTTPError(r.status_code)
    logs.info(f"get_player({pid}) in {r.elapsed}s")
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


def main(client: httpx.Client):
    logs.info("parser started")
    t0 = time.time()
    players: List[Player] = []
    for dc in dcs:
        logs.info(f"start parsing dc {dc}")
        dc_resp = get_ranking(client, dc)
        new_players = parse_rankings(BeautifulSoup(dc_resp, 'html.parser'))
        if len(new_players) != 100:
            # Uncommon, but can happen
            logs.warn(f"total number of players in dc {dc} is {len(new_players)}, not 100")
        players.extend(new_players)
        logs.info(f"parsed rankings for {dc}")

    n_players = len(players)
    for i, player in enumerate(players):
        logs.debug(
            f"parsing player {player.name}: {player.id} ({i / n_players * 100:.1f}%)")
        player_resp = get_player(client, player.id)
        player.parse_job(BeautifulSoup(player_resp, "html.parser"))

    save_rankings(players)
    # Estimated runtime: 15mins
    logs.info(f"parsing finished, total time taken {time.time() - t0}s")


with httpx.Client() as client:
    main(client)
