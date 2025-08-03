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
    """YouTube transcript alma - çoklu yöntem"""
    print(f"📝 Video ID {video_id} için transcript alınıyor...")
    
    # Yöntem 1: youtube-dl (yt-dlp'den daha eski ve kararlı)
    transcript = try_youtube_dl(video_id)
    if transcript and len(transcript) > 100:
        return transcript
    
    # Yöntem 2: Direct YouTube API request
    transcript = try_direct_youtube_api(video_id)
    if transcript and len(transcript) > 100:
        return transcript
    
    # Yöntem 3: Web scraping
    transcript = try_web_scraping(video_id)
    if transcript and len(transcript) > 100:
        return transcript
    
    # Yöntem 4: youtube-transcript-api (en son)
    transcript = try_transcript_api(video_id)
    if transcript and len(transcript) > 100:
        return transcript
    
    # Yöntem 5: yt-dlp (son çare)
    transcript = try_ytdlp_transcript(video_id)
    if transcript and len(transcript) > 100:
        return transcript
    
    print("❌ Hiçbir yöntemle transcript alınamadı")
    return None

def try_youtube_dl(video_id):
    """youtube-dl ile dene"""
    try:
        print("🔄 youtube-dl deneniyor...")
        
        cmd = [
            'youtube-dl',
            '--write-auto-sub',
            '--sub-lang', 'tr,en',
            '--skip-download',
            '--sub-format', 'vtt',
            '-o', f'temp_%(id)s.%(ext)s',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            import glob
            vtt_files = glob.glob(f'temp_{video_id}*.vtt')
            
            if vtt_files:
                with open(vtt_files[0], 'r', encoding='utf-8') as f:
                    content = f.read()
                
                transcript = parse_vtt(content)
                
                # Cleanup
                for file in vtt_files:
                    try:
                        os.remove(file)
                    except:
                        pass
                
                print("✅ youtube-dl ile başarılı!")
                return transcript
                
    except Exception as e:
        print(f"⚠️ youtube-dl hatası: {e}")
    
    return None

def try_direct_youtube_api(video_id):
    """Direkt YouTube API isteği"""
    try:
        print("🔄 Direct YouTube API deneniyor...")
        
        # YouTube'un internal API'sine istek
        urls_to_try = [
            f"https://www.youtube.com/api/timedtext?lang=tr&v={video_id}&fmt=vtt",
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&fmt=vtt",
            f"https://www.youtube.com/api/timedtext?lang=tr&v={video_id}&kind=asr&fmt=vtt",
            f"https://www.youtube.com/api/timedtext?lang=en&v={video_id}&kind=asr&fmt=vtt"
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        for url in urls_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200 and len(response.text) > 100:
                    transcript = parse_vtt(response.text)
                    if transcript:
                        print("✅ Direct API ile başarılı!")
                        return transcript
            except:
                continue
                
    except Exception as e:
        print(f"⚠️ Direct API hatası: {e}")
    
    return None

def try_web_scraping(video_id):
    """Web scraping ile transcript alma"""
    try:
        print("🔄 Web scraping deneniyor...")
        
        # YouTube watch sayfasını al
        url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            html = response.text
            
            # Caption track URL'lerini ara
            import re
            
            # Captions player response'u ara
            pattern = r'"captions":\s*({[^}]+})'
            captions_match = re.search(pattern, html)
            
            if captions_match:
                print("📋 Caption bilgisi bulundu, parse ediliyor...")
                # Basit parsing - daha gelişmiş yapılabilir
                
            # Alternatif: Script tag'lerinde ara
            script_pattern = r'"captionTracks":\s*(\[[^\]]+\])'
            script_match = re.search(script_pattern, html)
            
            if script_match:
                print("📋 Script caption tracks bulundu")
                
        print("⚠️ Web scraping ile transcript bulunamadı")
        
    except Exception as e:
        print(f"⚠️ Web scraping hatası: {e}")
    
    return None

def try_transcript_api(video_id):
    """youtube-transcript-api ile dene"""
    try:
        print("🔄 youtube-transcript-api deneniyor...")
        from youtube_transcript_api import YouTubeTranscriptApi
        
        # Basit approach
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = ' '.join([item['text'] for item in transcript])
        print("✅ transcript-api ile başarılı!")
        return text
        
    except Exception as e:
        print(f"⚠️ transcript-api hatası: {e}")
    
    return None

def try_ytdlp_transcript(video_id):
    """yt-dlp ile transcript alma"""
    try:
        print("🔄 yt-dlp ile transcript alınıyor...")
        
        # Daha detaylı yt-dlp komutu
        cmd = [
            'yt-dlp',
            '--write-auto-sub',
            '--write-sub',
            '--sub-lang', 'tr,en,tr-auto,en-auto',
            '--skip-download',
            '--sub-format', 'vtt',
            '--output', f'temp_%(id)s.%(ext)s',
            '--no-warnings',
            f'https://www.youtube.com/watch?v={video_id}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        print(f"yt-dlp return code: {result.returncode}")
        
        if result.returncode == 0:
            import glob
            vtt_files = glob.glob(f'temp_{video_id}*.vtt')
            print(f"Bulunan VTT dosyaları: {vtt_files}")
            
            if vtt_files:
                # İlk dosyayı al
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
                
                if len(transcript) > 100:
                    print("✅ yt-dlp ile transcript alındı!")
                    return transcript
                else:
                    print("⚠️ yt-dlp transcript çok kısa")
        else:
            print(f"⚠️ yt-dlp stderr: {result.stderr}")
            print(f"⚠️ yt-dlp stdout: {result.stdout}")
        
    except Exception as e:
        print(f"⚠️ yt-dlp exception: {e}")
    
    return None

def get_video_description(video_id):
    """Video açıklamasını al ve özetle"""
    try:
        # YouTube oEmbed'den başlık al
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            title = data.get('title', '')
            author = data.get('author_name', '')
            
            # Basit bir içerik oluştur
            content = f"""
Video Başlığı: {title}
Kanal: {author}
Video ID: {video_id}

Bu video için otomatik transcript alınamadı. 
Video başlığından hareketle genel bir analiz yapılacak.
            """
            
            return content.strip()
    
    except Exception as e:
        print(f"Video description hatası: {e}")
    
    return f"Video ID {video_id} için herhangi bir içerik alınamadı."

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