import os
import re
import requests
from flask import Flask, request, jsonify, send_from_directory
from youtube_transcript_api import YouTubeTranscriptApi

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/summarize', methods=['POST', 'OPTIONS'])
def summarize():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        video_url = data.get('videoUrl')

        video_id = extract_video_id(video_url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Geçersiz YouTube URL'})

        transcript = get_transcript(video_id)
        if not transcript:
            return jsonify({'success': False, 'error': 'Transcript bulunamadı'})

        video_info = get_video_info(video_id)
        summary = gemini_ozet_yap(transcript)

        return jsonify({
            'success': True,
            'title': video_info['title'],
            'channel': video_info['channel'],
            'thumbnail': video_info['thumbnail'],
            'summary': summary
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def extract_video_id(url):
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return match.group(1) if match else None

def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['tr', 'en'])
        return ' '.join([item['text'] for item in transcript])
    except Exception as e:
        print(f"Transcript alınamadı: {e}")
        return None

def get_video_info(video_id):
    try:
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return {
                'title': data.get('title', 'YouTube Video'),
                'channel': data.get('author_name', 'YouTube Kanalı'),
                'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
            }
    except:
        pass
    return {
        'title': 'YouTube Video',
        'channel': 'YouTube Kanalı',
        'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
    }

def gemini_ozet_yap(transcript):
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API key bulunamadı!"

    if len(transcript) > 15000:
        transcript = transcript[:15000] + "..."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"""Bu YouTube video metnini Türkçe olarak özetle. 

Kurallar:
- 4-5 paragraf yaz
- Ana konular ve önemli noktaları vurgula
- Net, akıcı ve sade Türkçe kullan
- Gereksiz detayları çıkar
- Sonda 3-4 bullet point çıkarım ekle

Metin:
{transcript}"""
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1500,
        }
    }

    try:
        response = requests.post(url, json=data, timeout=90)
        if response.status_code == 200:
            result = response.json()
            summary = result['candidates'][0]['content']['parts'][0]['text']
            return summary
        return f"Hata ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Gemini API Hatası: {str(e)}"

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)