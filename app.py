import os
import json
import re
import requests
import subprocess
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# Environment variable'dan API key al - fallback yok!
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/summarize', methods=['POST', 'OPTIONS'])
def summarize():
    # CORS için OPTIONS
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        video_url = data.get('videoUrl')
        
        # Video ID çıkar
        match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_url)
        if not match:
            return jsonify({'success': False, 'error': 'Geçersiz YouTube URL'})
        
        video_id = match.group(1)
        print(f"✅ Video ID: {video_id}")
        
        # Transcript al
        transcript = get_youtube_transcript(video_id)
        print(f"📄 Transcript uzunluğu: {len(transcript)} karakter")
        
        # Video bilgilerini al
        video_info = get_video_info(video_id)
        
        # Gemini ile özet yap
        summary = gemini_ozet_yap(transcript)
        
        response = {
            'success': True,
            'title': video_info['title'],
            'channel': video_info['channel'],
            'thumbnail': video_info['thumbnail'],
            'summary': summary
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Hata: {e}")
        return jsonify({'success': False, 'error': str(e)})

def get_youtube_transcript(video_id):
    """YouTube transcript alma fonksiyonu - yt-dlp odaklı"""
    print("📝 YouTube transcript alınıyor...")
    
    # Direkt yt-dlp ile başla (daha güvenilir)
    try:
        print("🔄 yt-dlp ile transcript alınıyor...")
        
        cmd = [
            'yt-dlp',
            '--write-auto-sub',
            '--sub-lang', 'tr,en',
            '--skip-download',
            '--sub-format', 'vtt',
            '--output', f'temp_%(id)s.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            import glob
            vtt_files = glob.glob(f'temp_{video_id}*.vtt')
            
            if vtt_files:
                vtt_file = vtt_files[0]
                with open(vtt_file, 'r', encoding='utf-8') as f:
                    vtt_content = f.read()
                
                transcript = parse_vtt(vtt_content)
                
                # Dosyaları temizle
                for file in vtt_files:
                    try:
                        os.remove(file)
                    except:
                        pass
                
                print("✅ yt-dlp ile transcript alındı!")
                return transcript
        else:
            print(f"⚠️ yt-dlp stderr: {result.stderr}")
        
    except Exception as e:
        print(f"⚠️ yt-dlp hatası: {e}")
    
    # Son çare: Basit mesaj
    return f"Bu video için transcript alınamadı. Video ID: {video_id}. Lütfen altyazılı bir video deneyin."

def parse_vtt(vtt_content):
    """VTT dosyasını parse et"""
    lines = vtt_content.split('\n')
    transcript_lines = []
    
    for line in lines:
        line = line.strip()
        if (line and 
            not line.startswith('WEBVTT') and 
            not '-->' in line and 
            not line.startswith('NOTE') and
            not line.isdigit() and
            not line.startswith('<')):
            
            line = re.sub(r'<[^>]+>', '', line)
            if line:
                transcript_lines.append(line)
    
    return ' '.join(transcript_lines)

def get_video_info(video_id):
    """Video bilgilerini al"""
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
    """Google Gemini ile özet yap"""
    print("🤖 Gemini API'ye istek gönderiliyor...")
    
    if not GEMINI_API_KEY:
        return "⚠️ Gemini API key bulunamadı! Railway'de environment variable olarak ekleyin."
    
    # Transcript'i kısalt
    if len(transcript) > 15000:
        transcript = transcript[:15000] + "..."
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"""Bu YouTube video metnini Türkçe olarak özetle. 

Özet kuralları:
- 4-5 paragraf halinde yaz
- Ana konuları ve önemli noktaları dahil et
- Net, anlaşılır ve akıcı Türkçe kullan
- Gereksiz detayları çıkar, önemli bilgileri koru
- Video izleyicisi için değerli olsun
- Sonunda 3-4 önemli çıkarımı bullet point (•) olarak ekle

Video metni:
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
            
            if 'candidates' in result and len(result['candidates']) > 0:
                if 'content' in result['candidates'][0]:
                    summary = result['candidates'][0]['content']['parts'][0]['text']
                    print("✅ Gemini özet başarıyla alındı!")
                    return summary
        
        return f"Gemini API Hatası ({response.status_code}): {response.text}"
        
    except Exception as e:
        return f"Gemini API Hatası: {str(e)}"

# CORS middleware
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    # Render için port ayarı
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)