import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString

BASE_URL = "https://hopamchuan.com"
CATEGORY_PATHS: dict[str, str] = {
    "ballad": "/rhythm/v/ballad",
    "blues": "/rhythm/v/blues",
    "disco": "/rhythm/v/disco",
    "slow": "/rhythm/v/slow",
    "slow-rock": "/rhythm/v/slow-rock",
    "bollero": "/rhythm/v/bollero",
    "valse": "/rhythm/v/valse",
    "fox": "/rhythm/v/fox",
    "pop": "/rhythm/v/pop",
    "boston": "/rhythm/v/boston",
    "bossa-nova": "/rhythm/v/bossa-nova",
    "rock": "/rhythm/v/rock",
    "chachacha": "/rhythm/v/chachacha",
    "rhumba": "/rhythm/v/rhumba",
    "tango": "/rhythm/v/tango",
}


def resolve_categories(selected: list[str] | None) -> list[str]:
    if not selected:
        return list(CATEGORY_PATHS.values())
    resolved: list[str] = []
    for item in selected:
        key = item.lower()
        if key in CATEGORY_PATHS:
            resolved.append(CATEGORY_PATHS[key])
        elif item.startswith("/"):
            resolved.append(item)
        else:
            raise ValueError(f"Unknown category: {item}")
    return resolved


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )
    })
    return session


def collect_song_links(output_path: Path, categories: list[str]) -> None:
    session = build_session()
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            seen = set(existing)
            links = list(seen)
        except json.JSONDecodeError:
            seen = set()
            links = []
    else:
        seen = set()
        links = []

    try:
        for cat in categories:
            offset = 0
            while True:
                url = f"{BASE_URL}{cat}?offset={offset}"
                res = session.get(url, timeout=30)
                if res.status_code != 200:
                    break
                soup = BeautifulSoup(res.text, "html.parser")
                song_links = soup.select("div.song-item a.song-title")
                if not song_links:
                    break
                new_count = 0
                for a in song_links:
                    href = a.get("href")
                    if not href:
                        continue
                    song_url = urljoin(BASE_URL, href)
                    if song_url in seen:
                        continue
                    seen.add(song_url)
                    links.append(song_url)
                    new_count += 1
                offset += 10
                if new_count == 0:
                    break
    finally:
        output_path.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_song_details(session: requests.Session, song_url: str) -> dict[str, object] | None:
    res_song = session.get(song_url, timeout=30)
    if res_song.status_code != 200:
        return None
    soup_song = BeautifulSoup(res_song.text, "html.parser")
    title_tag = soup_song.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else None
    artist = None
    author_label = soup_song.find(string=re.compile(r"Tác giả:"))
    if author_label:
        artist_link = author_label.find_next("a")
        if artist_link:
            artist = artist_link.get_text(strip=True)
        else:
            artist = author_label.split(":", 1)[-1].strip()
    lyrics_text = ""
    lyric_container = soup_song.find("div", id="song-lyric")
    if lyric_container:
        parent_block = lyric_container.find("div", class_="pre") or lyric_container
        lyrics_lines = []
        for block in parent_block.find_all("div", recursive=False):
            classes = block.get("class", []) if hasattr(block, "get") else []
            if "empty_line" in classes:
                lyrics_lines.append("")
                continue
            if "chord_lyric_line" not in classes:
                continue
            parts = []
            for node in block.children:
                if isinstance(node, NavigableString):
                    text_piece = str(node)
                elif getattr(node, "get", None):
                    node_classes = node.get("class", [])
                    if node_classes and "hopamchuan_chord_inline" in node_classes:
                        chord_node = node.find("span", class_="hopamchuan_chord")
                        chord_text = chord_node.get_text(strip=True) if chord_node else node.get_text(strip=True)
                        text_piece = f"[{chord_text}]"
                    else:
                        text_piece = node.get_text()
                else:
                    text_piece = str(node)
                text_piece = text_piece.replace("\xa0", " ")
                parts.append(text_piece)
            line = "".join(parts)
            line = " ".join(line.split())
            for punct in [",", ".", "!", "?", ";", ":"]:
                line = line.replace(f" {punct}", punct)
            lyrics_lines.append(line)
        lyrics_text = "\n".join(lyrics_lines).strip()
    if not lyrics_text:
        chord_list_header = soup_song.find(
            lambda tag: tag.name and tag.name.startswith("h") and "Danh sách hợp âm" in tag.get_text()
        )
        if chord_list_header:
            lyrics_parts = []
            node = chord_list_header
            while node.previous_sibling:
                node = node.previous_sibling
                if getattr(node, "name", None) and "Hợp âm dễ" in node.get_text():
                    break
                if hasattr(node, "get_text"):
                    node_text = node.get_text().strip()
                else:
                    node_text = str(node).strip()
                if node_text:
                    lyrics_parts.append(node_text)
            lyrics_parts.reverse()
            lyrics_text = "\n".join(lyrics_parts).strip()
    genre = None
    genre_link = soup_song.find("a", href=re.compile(r"/genre/"))
    if genre_link:
        genre = genre_link.get_text(strip=True)
    return {
        "title": title,
        "artist": artist,
        "lyrics": lyrics_text,
        "genre": genre,
    }


def scrape_song_details(links_path: Path, output_path: Path, delay: float) -> None:
    if not links_path.exists():
        raise FileNotFoundError(f"Links file not found: {links_path}")
    links = json.loads(links_path.read_text(encoding="utf-8"))
    if not isinstance(links, list):
        raise ValueError("Links file must contain a JSON array of URLs")
    session = build_session()
    song_data_list: list[dict[str, object]] = []
    try:
        for idx, song_url in enumerate(links, start=1):
            data = fetch_song_details(session, song_url)
            if data:
                song_data_list.append(data)
            time.sleep(delay)
    finally:
        output_path.write_text(
            json.dumps(song_data_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape hopamchuan.com song data")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect", help="Collect song links")
    collect_parser.add_argument(
        "--output",
        default="song_links.json",
        type=Path,
        help="File to store collected song URLs",
    )
    collect_parser.add_argument(
        "--category",
        dest="categories",
        action="append",
        metavar="NAME",
        help="Category slug (e.g. ballad) or full path. Repeat to include multiple categories. Defaults to all.",
    )

    scrape_parser = subparsers.add_parser("scrape", help="Scrape song details from links")
    scrape_parser.add_argument(
        "--links",
        default="song_links.json",
        type=Path,
        help="Song link list generated by the collect phase",
    )
    scrape_parser.add_argument(
        "--output",
        default="hopamchuan_songs.json",
        type=Path,
        help="File to dump scraped song data",
    )
    scrape_parser.add_argument(
        "--delay",
        default=2.0,
        type=float,
        help="Delay in seconds between requests",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "collect":
        categories = resolve_categories(getattr(args, "categories", None))
        collect_song_links(args.output, categories)
    elif args.command == "scrape":
        scrape_song_details(args.links, args.output, args.delay)


if __name__ == "__main__":
    main()
