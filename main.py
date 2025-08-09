from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import requests
import json
import yt_dlp
import os
import datetime

app = FastAPI()

load_dotenv()

os.makedirs("downloads", exist_ok=True)
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
TRENDING_SONGS_FILE = "trending_songs.json"
TRENDING_ALBUMS_FILE = "trending_albums.json"

ARTIST_NAMES = [
    "Arijit Singh",
    "Yo Yo Honey Singh",
    "Shreya Ghoshal",
    "Badshah",
    "Neha Kakkar",
]

def fetch_and_store_trending_songs():
    url = (
        "https://www.googleapis.com/youtube/v3/videos"
        "?part=snippet"
        "&chart=mostPopular"
        "&regionCode=IN"
        "&videoCategoryId=10"
        f"&maxResults=10"
        f"&key={YOUTUBE_API_KEY}"
    )
    response = requests.get(url)
    data = response.json()
    trending_songs = [
        {
            "id": item["id"],
            "name": item["snippet"]["title"]
        }
        for item in data.get("items", [])
    ]
    today = datetime.date.today().isoformat()
    result = {
        "fetched_today": True,
        "fetch_date": today,
        "songs": trending_songs
    }
    with open(TRENDING_SONGS_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

def fetch_and_store_trending_albums():
    trending_albums = []
    today = datetime.date.today().isoformat()
    for artist in ARTIST_NAMES:
        url = (
            "https://www.googleapis.com/youtube/v3/search"
            "?part=snippet"
            "&type=video"
            f"&q={artist} song"
            "&maxResults=10"
            "&regionCode=IN"
            f"&key={YOUTUBE_API_KEY}"
        )
        response = requests.get(url)
        data = response.json()
        album = {
            "artist": artist,
            "songs": [
                {
                    "id": item["id"]["videoId"],
                    "title": item["snippet"]["title"]
                }
                for item in data.get("items", [])
                if item["id"].get("videoId")
            ]
        }
        trending_albums.append(album)
    result = {
        "fetched_today": True,
        "fetch_date": today,
        "albums": trending_albums
    }
    with open(TRENDING_ALBUMS_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

@app.get("/")
def welcome():
    fetch_and_store_trending_songs()
    fetch_and_store_trending_albums()
    return {"message": "Trending songs and albums updated!"}

class SongQuery(BaseModel):
    song_name: str

@app.post("/youtube")
def search_song(query: SongQuery):
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        'extract_flat': True,
        'playlistend': 5,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_query = f"ytsearch5:{query.song_name} song"
        info = ydl.extract_info(search_query, download=False)
        videos = info.get('entries', [])
    results = [{ "id": video['id'], "title": video['title'] } for video in videos]
    return {"results": results}

class DownloadRequest(BaseModel):
    video_id: str
    
@app.post("/download")
def download_song(request: DownloadRequest):
    video_url = f"https://www.youtube.com/watch?v={request.video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    
    file_name = f"{request.video_id}.mp3"
    download_url = f"/downloads/{file_name}"
    return {"message": "Song downloaded successfully!", "download_url": download_url}

@app.get("/stream/{video_id}")
def stream_song(video_id: str):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        audio_formats = [
            f for f in info['formats']
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none'
        ]
        
        if not audio_formats:
            return {"error": "No audio stream found for this video."}
        
        audio_formats.sort(key=lambda f: float(f.get('abr') or 0), reverse=True)
        audio_url = audio_formats[0]['url']
        
        def stream_generator():
            with requests.get(audio_url, stream=True) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk
                        
        return StreamingResponse(stream_generator(), media_type="audio/mpeg")


@app.get("/lists")
def show_lists():
    songs = {}
    albums = {}
    if os.path.exists(TRENDING_SONGS_FILE):
        with open(TRENDING_SONGS_FILE, "r", encoding="utf-8") as f:
            songs = json.load(f)
    if os.path.exists(TRENDING_ALBUMS_FILE):
        with open(TRENDING_ALBUMS_FILE, "r", encoding="utf-8") as f:
            albums = json.load(f)
    return {"songs": songs, "albums": albums}