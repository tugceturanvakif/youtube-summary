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
    """YouTube transcript alma fonksiyonu - geliştirilmiş"""
    print(f"📝 Video ID {video_id} için transcript alınıyor...")
    
    # Önce youtube-transcript-api ile dene (daha agresif)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        print("🔄 YouTube Transcript API deneniyor...")
        
        # Mevcut transcript'leri listele
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # Önce manuel transcriptleri bul
            manual_transcripts = []
            auto_transcripts = []
            
            for transcript in transcript_list:
                if transcript.is_generated:
                    auto_transcripts.append(transcript)
                else:
                    manual_transcripts.append(transcript)
            
            print(f"📋 {len(manual_transcripts)} manuel, {len(auto_transcripts)} otomatik transcript bulundu")
            
            # Önce manuel transcriptleri dene
            for transcript in manual_transcripts:
                try:
                    data = transcript.fetch()
                    text = ' '.join([item['text'] for item in data])
                    if len(text) > 100:
                        print(f"✅ Manuel {transcript.language_code} transcript alındı!")
                        return text
                except:
                    continue
            
            # Sonra otomatik transcriptleri dene
            for transcript in auto_transcripts:
                try:
                    data = transcript.fetch()
                    text = ' '.join([item['text'] for item in data])
                    if len(text) > 100:
                        print(f"✅ Otomatik {transcript.language_code} transcript alındı!")
                        return text
                except:
                    continue
                    
        except Exception as list_error:
            print(f"⚠️ Transcript listesi hatası: {list_error}")
            
            # Direkt dil kodlarıyla dene
            language_codes = ['tr', 'en', 'auto']
            for lang in language_codes:
                try:
                    if lang == 'auto':
                        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
                    else:
                        transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=[lang])
                    
                    text = ' '.join([item['text'] for item in transcript_data])
                    if len(text) > 100:
                        print(f"✅ {lang} transcript direkt alındı!")
                        return text
                except Exception as lang_error:
                    print(f"⚠️ {lang} dili hatası: {lang_error}")
                    continue
                    
    except ImportError:
        print("❌ youtube-transcript-api kütüphanesi yok")
    except Exception as api_error:
        print(f"❌ youtube-transcript-api genel hatası: {api_error}")
    
    # yt-dlp dene
    try:
        print("🔄 yt-dlp deneniyor...")
        return try_ytdlp_transcript(video_id)
    except Exception as ytdlp_error:
        print(f"❌ yt-dlp hatası: {ytdlp_error}")
    
    # YouTube Data API ile video detaylarını dene
    try:
        print("🔄 Video detayları alınıyor...")
        return get_video_description(video_id)
    except Exception as desc_error:
        print(f"❌ Video detay hatası: {desc_error}")
    
    # Son çare mesajı
    return f"""Bu video (ID: {video_id}) için transcript alınamadı. 

Olası nedenler:
- Video altyazısı yok
- Video özel/kısıtlı
- Geçici API sorunu

Lütfen altyazılı bir video deneyin veya video sahibinden altyazı eklemesini isteyin."""

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