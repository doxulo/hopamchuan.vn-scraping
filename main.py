import requests, re, json, time
from urllib.parse import urljoin
from bs4 import BeautifulSoup, NavigableString

BASE_URL = "https://hopamchuan.com"
# List all rhythm category endpoints to cover all songs
categories = [
    "/rhythm/v/ballad", "/rhythm/v/blues", "/rhythm/v/disco", "/rhythm/v/slow",
    "/rhythm/v/slow-rock", "/rhythm/v/bollero", "/rhythm/v/valse", "/rhythm/v/fox",
    "/rhythm/v/pop", "/rhythm/v/boston", "/rhythm/v/bossa-nova", "/rhythm/v/rock",
    "/rhythm/v/chachacha", "/rhythm/v/rhumba", "/rhythm/v/tango"
]

song_data_list = []

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
})  # set a friendly User-Agent

seen_song_urls = set()

try:
    for cat in categories:
        offset = 0
        while True:
            url = f"{BASE_URL}{cat}?offset={offset}"
            res = session.get(url)
            if res.status_code != 200:
                break  # page not found or end of category
            soup = BeautifulSoup(res.text, 'html.parser')
            song_links = soup.select('div.song-item a.song-title')
            if not song_links:
                break  # no songs on this page, end pagination
            for a in song_links:
                href = a.get('href')
                if not href:
                    continue
                song_url = urljoin(BASE_URL, href)
                if song_url in seen_song_urls:
                    continue  # skip duplicates across categories/pages
                seen_song_urls.add(song_url)
                res_song = session.get(song_url)
                if res_song.status_code != 200:
                    continue
                soup_song = BeautifulSoup(res_song.text, 'html.parser')
                # Title
                title_tag = soup_song.find('h1')
                title = title_tag.get_text(strip=True) if title_tag else None
                # Artist(s)
                artist = None
                author_label = soup_song.find(string=re.compile(r"Tác giả:"))
                if author_label:
                    artist_link = author_label.find_next('a')
                    if artist_link:
                        artist = artist_link.get_text(strip=True)
                    else:
                        # If artist is not a link (unlikely), get text next to label
                        artist = author_label.split(":", 1)[-1].strip()
                # Lyrics & chords text
                lyrics_text = ""
                lyric_container = soup_song.find('div', id='song-lyric')
                if lyric_container:
                    parent_block = lyric_container.find('div', class_='pre') or lyric_container
                    lyrics_lines = []
                    for block in parent_block.find_all('div', recursive=False):
                        classes = block.get('class', []) if hasattr(block, 'get') else []
                        if 'empty_line' in classes:
                            lyrics_lines.append("")
                            continue
                        if 'chord_lyric_line' not in classes:
                            continue
                        parts = []
                        for node in block.children:
                            if isinstance(node, NavigableString):
                                text_piece = str(node)
                            elif getattr(node, 'get', None):
                                node_classes = node.get('class', [])
                                if node_classes and 'hopamchuan_chord_inline' in node_classes:
                                    chord_node = node.find('span', class_='hopamchuan_chord')
                                    chord_text = chord_node.get_text(strip=True) if chord_node else node.get_text(strip=True)
                                    text_piece = f'[{chord_text}]'
                                else:
                                    text_piece = node.get_text()
                            else:
                                text_piece = str(node)
                            text_piece = text_piece.replace('\xa0', ' ')
                            parts.append(text_piece)
                        line = ''.join(parts)
                        line = ' '.join(line.split())
                        for punct in [',', '.', '!', '?', ';', ':']:
                            line = line.replace(f' {punct}', punct)
                        lyrics_lines.append(line)
                    lyrics_text = '\n'.join(lyrics_lines).strip()
                if not lyrics_text:
                    # Fallback: gather text before "Danh sách hợp âm" section
                    chord_list_header = soup_song.find(lambda tag: tag.name and tag.name.startswith('h') and "Danh sách hợp âm" in tag.get_text())
                    if chord_list_header:
                        lyrics_parts = []
                        node = chord_list_header
                        while node.previous_sibling:
                            node = node.previous_sibling
                            node_text = ""
                            if getattr(node, 'name', None) and "Hợp âm dễ" in node.get_text():
                                break
                            if hasattr(node, 'get_text'):
                                node_text = node.get_text().strip()
                            else:
                                node_text = str(node).strip()
                            if node_text:
                                lyrics_parts.append(node_text)
                        lyrics_parts.reverse()
                        lyrics_text = "\n".join(lyrics_parts).strip()
                # If needed, gather chords as list (using regex on the lyrics text)
                chords_used = re.findall(r'\[([^]]+)\]', lyrics_text)  # capture text inside [...]
                # Other metadata
                genre = None
                genre_link = soup_song.find('a', href=re.compile(r'/genre/'))
                if genre_link:
                    genre = genre_link.get_text(strip=True)
                views = None
                views_match = soup_song.find(string=re.compile(r"Lượt xem:"))
                if views_match:
                    # extract the number after "Lượt xem:"
                    views = re.sub(r"\D", "", views_match.split(":", 1)[-1])  # remove non-digits
                    views = int(views) if views.isdigit() else views
                favorites = None
                fav_match = soup_song.find(string=re.compile(r"Yêu thích:"))
                if fav_match:
                    fav_num = re.sub(r"\D", "", fav_match.split(":", 1)[-1])
                    favorites = int(fav_num) if fav_num.isdigit() else fav_num
                updated = None
                upd_match = soup_song.find(string=re.compile(r"Cập nhật:"))
                if upd_match:
                    date_text = upd_match.parent.get_text()  # e.g. "Cập nhật: ngày 3 tháng 02, 2019"
                    updated = date_text.split(":", 1)[-1].strip()
                # Save the song info
                song_data = {
                    "title": title,
                    "artist": artist,
                    "lyrics": lyrics_text,
                    "chords": chords_used,
                    "url": song_url,
                    "genre": genre,
                    "views": views,
                    "favorites": favorites,
                    "updated": updated
                }
                song_data_list.append(song_data)
                time.sleep(2)  # delay to be polite
            offset += 10  # go to next page in category
except KeyboardInterrupt:
    print("Interrupted. Writing partial data to hopamchuan_songs.json...")
finally:
    # Write results to JSON file
    with open("hopamchuan_songs.json", "w", encoding="utf-8") as f:
        json.dump(song_data_list, f, ensure_ascii=False, indent=2)
