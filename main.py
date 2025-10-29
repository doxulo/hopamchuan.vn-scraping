import requests, re, json, time
from bs4 import BeautifulSoup

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
session.headers.update({"User-Agent": "Mozilla/5.0"})  # set a friendly User-Agent

for cat in categories:
    offset = 0
    while True:
        url = f"{BASE_URL}{cat}?offset={offset}"
        res = session.get(url)
        if res.status_code != 200:
            break  # page not found or end of category
        soup = BeautifulSoup(res.text, 'html.parser')
        song_links = soup.select('a[href^="/song/"]')
        if not song_links:
            break  # no songs on this page, end pagination
        for a in song_links:
            song_url = BASE_URL + a['href']
            res_song = session.get(song_url)
            if res_song.status_code != 200:
                continue
            soup_song = BeautifulSoup(res_song.text, 'html.parser')
            # Title
            title = soup_song.find('h1').get_text(strip=True) if soup_song.find('h1') else None
            # Artist(s)
            artist = None
            author_label = soup_song.find(text=re.compile(r"Tác giả:"))
            if author_label:
                artist_link = author_label.find_next('a')
                if artist_link:
                    artist = artist_link.get_text(strip=True)
                else:
                    # If artist is not a link (unlikely), get text next to label
                    artist = author_label.split(":", 1)[-1].strip()
            # Lyrics & chords text
            lyrics_text = ""
            # Assuming lyrics are contained in a div or within the page before the "Danh sách hợp âm" section:
            chord_list_header = soup_song.find(lambda tag: tag.name.startswith('h') and "Danh sách hợp âm" in tag.text)
            if chord_list_header:
                # Collect all text from the start of lyrics up to this header
                lyrics_parts = []
                node = chord_list_header
                # Traverse backwards through siblings to gather lyrics lines
                while node.previous_sibling:
                    node = node.previous_sibling
                    # Stop when reaching the control section (e.g., a tag that indicates end of lyrics)
                    if node.name and "Hợp âm dễ" in (node.get_text() or ""):
                        break
                    if getattr(node, 'text', '').strip():  # if node has text
                        lyrics_parts.append(node.get_text()) 
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
            views_match = soup_song.find(text=re.compile(r"Lượt xem:"))
            if views_match:
                # extract the number after "Lượt xem:"
                views = re.sub(r"\D", "", views_match.split(":",1)[-1])  # remove non-digits
                views = int(views) if views.isdigit() else views
            favorites = None
            fav_match = soup_song.find(text=re.compile(r"Yêu thích:"))
            if fav_match:
                fav_num = re.sub(r"\D", "", fav_match.split(":",1)[-1])
                favorites = int(fav_num) if fav_num.isdigit() else fav_num
            updated = None
            upd_match = soup_song.find(text=re.compile(r"Cập nhật:"))
            if upd_match:
                date_text = upd_match.parent.get_text()  # e.g. "Cập nhật: ngày 3 tháng 02, 2019"
                updated = date_text.split(":",1)[-1].strip()
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
            time.sleep(1)  # delay to be polite
        offset += 10  # go to next page in category
# Write results to JSON file
with open("hopamchuan_songs.json", "w", encoding="utf-8") as f:
    json.dump(song_data_list, f, ensure_ascii=False, indent=2)
