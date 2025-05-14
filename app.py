from flask import Flask, render_template, request, jsonify, redirect, url_for, Response
import os
import subprocess
import json
import socket
import qrcode
import requests
from io import BytesIO
import urllib.parse
import base64
from flask_sock import Sock
import threading
import logging
import time
import yt_dlp
import shlex

app = Flask(__name__)
sock = Sock(app)
app.config['SECRET_KEY'] = 'your-secret-key'

# Setup logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
CONFIG_FILE = 'config.json'
IMAGES_DIR = os.path.join(app.static_folder, 'images')

# Connected cast clients
cast_clients = set()
# Lock for thread-safe access to clients
clients_lock = threading.Lock()

# Current player process
current_process = None
process_lock = threading.Lock()

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    else:
        # Default configuration
        config = {
            'grafana_url': 'http://your-grafana-server:3000',
            'grafana_dashboards': [
                {'name': 'Main Dashboard', 'url': '/d/abcd1234/main-dashboard'},
                {'name': 'System Metrics', 'url': '/d/efgh5678/system-metrics'},
            ],
            'preset_youtube': [
                {
                    'name': 'Lofi Hip Hop Radio',
                    'description': 'Beats to relax/study to',
                    'url': 'https://www.youtube.com/watch?v=jfKfPfyJRdk',
                    'thumbnail': None
                },
                {
                    'name': 'Ambient Music',
                    'description': 'Relaxing ambient sounds',
                    'url': 'https://www.youtube.com/watch?v=5qap5aO4i9A',
                    'thumbnail': None
                },
                {
                    'name': 'Nature Scenery',
                    'description': 'Beautiful landscapes in 4K',
                    'url': 'https://www.youtube.com/watch?v=BHACKCNDMW8',
                    'thumbnail': None
                },
                {
                    'name': 'Aquarium',
                    'description': 'Relaxing aquarium view',
                    'url': 'https://www.youtube.com/watch?v=mF4VYzL1Ggs',
                    'thumbnail': None
                },
                {
                    'name': 'Fireplace',
                    'description': 'Crackling fireplace with sounds',
                    'url': 'https://www.youtube.com/watch?v=L_LUpnjgPso',
                    'thumbnail': None
                }
            ],
            'cast_settings': {
                'device_name': 'PiMedia Player',
                'allow_external_networks': False,
                'require_pin': True,
                'default_pin': '1234',
                'auto_accept_cast': False
            },
            'display_settings': {
                'browser_path': '/usr/bin/chromium-browser',
                'audio_output': 'hdmi',
                'resolution': '1080p',
                'brightness': 100,
            },
            'current_display': None,
            'display_type': None,
            'server_port': 5000,
        }
        save_config(config)
        return config

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def get_ip_address():
    """Get the local IP address of the device"""
    try:
        # Get all network interfaces
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Doesn't actually send any packets
        ip_address = s.getsockname()[0]
        s.close()
        return ip_address
    except Exception as e:
        logger.error(f"Error getting IP address: {e}")
        return "localhost"

def generate_cast_url():
    """Generate a URL for casting to this device"""
    ip = get_ip_address()
    config = load_config()
    port = config.get('server_port', 5000)
    device_name = config.get('cast_settings', {}).get('device_name', 'PiMedia')
    device_name_encoded = device_name.replace(' ', '+')
    
    # Include cast parameters in the URL
    require_pin = config.get('cast_settings', {}).get('require_pin', False)
    pin = ""
    if require_pin:
        pin = f"&pin={config.get('cast_settings', {}).get('default_pin', '1234')}"
    
    # Generate a URL for casting
    cast_url = f"http://{ip}:{port}/cast?device={device_name_encoded}{pin}"
    return cast_url

def generate_qr_code():
    """Generate a QR code for the cast URL"""
    url = generate_cast_url()
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save to BytesIO
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return img_io

# Routes
@app.route('/')
def index():
    config = load_config()
    ip_address = get_ip_address()
    return render_template('index.html', config=config, ip_address=ip_address)

@app.route('/cast_qr')
def cast_qr():
    """Return a QR code for casting"""
    img_io = generate_qr_code()
    return Response(img_io, mimetype='image/png')

@app.route('/cast')
def cast_page():
    """A page for casting to this device"""
    device_name = request.args.get('device', 'Unknown Device')
    
    # Check PIN if required
    config = load_config()
    if config.get('cast_settings', {}).get('require_pin', False):
        pin = request.args.get('pin')
        default_pin = config.get('cast_settings', {}).get('default_pin', '1234')
        if pin != default_pin:
            return render_template('cast_error.html', 
                                  error="Incorrect PIN. Please scan the QR code again.")
    
    return render_template('cast.html', device_name=device_name)

@app.route('/youtube_player')
def youtube_player():
    """Serve the YouTube player page"""
    video_id = request.args.get('v', '')
    return render_template('youtube_player.html', video_id=video_id)

@app.route('/api/play-youtube', methods=['POST'])
def play_youtube():
    config = load_config()
    url = request.form.get('youtube_url')
    
    if not url:
        return jsonify({'status': 'error', 'message': 'No URL provided'}), 400
    
    # Stop any currently running display
    stop_current_display()
    
    # Start a background thread to handle video playback
    threading.Thread(target=play_youtube_background, args=(url,)).start()
    
    config['current_display'] = url
    config['display_type'] = 'youtube'
    save_config(config)
    
    # Broadcast status update to all connected cast clients
    broadcast_status_update()
    
    return jsonify({'status': 'success', 'message': 'Playing YouTube video'})

def play_youtube_background(url):
    """Play YouTube video using embedded player in browser"""
    try:
        # Extract video ID from the URL
        video_id = None
        if "youtube.com" in url:
            query = urllib.parse.urlparse(url).query
            params = urllib.parse.parse_qs(query)
            if "v" in params:
                video_id = params["v"][0]
        elif "youtu.be" in url:
            video_id = url.split("/")[-1].split("?")[0]
        
        if not video_id:
            logger.error(f"Could not extract YouTube video ID from URL: {url}")
            return
        
        # Get browser path from config
        config = load_config()
        browser_path = config.get('display_settings', {}).get('browser_path', '/usr/bin/chromium-browser')
        
        # Create the URL to the local YouTube player with the video ID
        player_url = f"http://localhost:5000/youtube_player?v={video_id}"
        
        # Launch browser in kiosk mode
        cmd = f"{browser_path} --kiosk --incognito --disable-infobars --autoplay-policy=no-user-gesture-required {player_url}"
        cmd_parts = shlex.split(cmd)
        
        with process_lock:
            global current_process
            current_process = subprocess.Popen(cmd_parts, env={"DISPLAY": ":0"})
    
    except Exception as e:
        logger.error(f"Error in YouTube playback thread: {e}")

@app.route('/api/show-dashboard', methods=['POST'])
def show_dashboard():
    config = load_config()
    dashboard_url = request.form.get('dashboard_url')
    
    if not dashboard_url:
        return jsonify({'status': 'error', 'message': 'No dashboard URL provided'}), 400
    
    # Stop any currently running display
    stop_current_display()
    
    # Get the full dashboard URL
    full_url = config['grafana_url'] + dashboard_url
    
    # Get browser path from config
    browser_path = config.get('display_settings', {}).get('browser_path', '/usr/bin/chromium-browser')
    
    # Launch browser in kiosk mode
    cmd = f"{browser_path} --kiosk --incognito {full_url}"
    cmd_parts = shlex.split(cmd)
    
    with process_lock:
        global current_process
        current_process = subprocess.Popen(cmd_parts, env={"DISPLAY": ":0"})
    
    config['current_display'] = dashboard_url
    config['display_type'] = 'dashboard'
    save_config(config)
    
    # Broadcast status update to all connected cast clients
    broadcast_status_update()
    
    return jsonify({'status': 'success', 'message': 'Displaying dashboard'})

@app.route('/api/stop', methods=['POST'])
def stop_display():
    stop_current_display()
    
    config = load_config()
    config['current_display'] = None
    config['display_type'] = None
    save_config(config)
    
    # Broadcast status update to all connected cast clients
    broadcast_status_update()
    
    return jsonify({'status': 'success', 'message': 'Display stopped'})

def stop_current_display():
    """Stop any currently running display processes"""
    with process_lock:
        global current_process
        if current_process:
            try:
                # Try to terminate gracefully
                current_process.terminate()
                
                # Give it some time to terminate
                for _ in range(5):  # Wait up to 5 seconds
                    if current_process.poll() is not None:  # Process has terminated
                        break
                    time.sleep(1)
                
                # Force kill if still running
                if current_process.poll() is None:
                    current_process.kill()
                    current_process.wait()
                
                current_process = None
            except Exception as e:
                logger.error(f"Error stopping process: {e}")
    
    # More aggressive VLC cleanup
    try:
        subprocess.run("killall -9 vlc", shell=True)
        subprocess.run("killall -9 cvlc", shell=True)
    except Exception as e:
        logger.error(f"Error killing VLC processes: {e}")

    # Small delay to ensure cleanup is complete
    time.sleep(1)

@app.route('/api/status', methods=['GET'])
def get_status():
    config = load_config()
    return jsonify({
        'current_display': config['current_display'],
        'display_type': config['display_type']
    })

@app.route('/api/cast-media', methods=['POST'])
def cast_media():
    """Handle media casting from external devices"""
    data = request.json
    if not data or 'media_url' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400
    
    url = data['media_url']
    media_type = data.get('media_type', 'video')
    
    # Stop any currently running display
    stop_current_display()
    
    if 'youtube.com' in url or 'youtu.be' in url:
        # Start a background thread to handle YouTube video playback
        threading.Thread(target=play_youtube_background, args=(url,)).start()
        
        config = load_config()
        config['current_display'] = url
        config['display_type'] = 'youtube_cast'
        save_config(config)
    else:
        # Handle as direct media URL using VLC
        cmd = f"vlc --fullscreen --no-video-title-show --no-osd '{url}'"
        cmd_parts = shlex.split(cmd)
        
        with process_lock:
            global current_process
            current_process = subprocess.Popen(cmd_parts, env={"DISPLAY": ":0"})
        
        config = load_config()
        config['current_display'] = url
        config['display_type'] = 'media_cast'
        save_config(config)
    
    # Broadcast status update to all connected cast clients
    broadcast_status_update()
    
    return jsonify({'status': 'success', 'message': f'Playing {media_type} from cast'})

# WebSocket endpoint for cast
@sock.route('/ws/cast')
def cast_socket(ws):
    """WebSocket endpoint for cast connections"""
    # Add client to the list
    with clients_lock:
        cast_clients.add(ws)
    
    try:
        # Send welcome message
        ws.send(json.dumps({
            'type': 'welcome',
            'message': 'Connected to PiMedia Player'
        }))
        
        # Receive messages
        while True:
            data = ws.receive()
            if data is None:
                break
            
            try:
                message = json.loads(data)
                logger.info(f"Received message: {message}")
                
                # Handle message types
                if message.get('type') == 'connect':
                    # Client connecting
                    ws.send(json.dumps({
                        'type': 'connected',
                        'device': message.get('device', 'Unknown Device')
                    }))
                    
                    # Broadcast to all other clients
                    broadcast_message({
                        'type': 'connect',
                        'device': message.get('device', 'Unknown Device')
                    }, exclude=ws)
                
                elif message.get('type') == 'cast':
                    # Process media URL
                    if 'url' in message:
                        media_type = 'youtube' if ('youtube.com' in message['url'] or 'youtu.be' in message['url']) else 'media'
                        
                        # Handle the cast through the API
                        if media_type == 'youtube':
                            threading.Thread(target=play_youtube_background, args=(message['url'],)).start()
                            
                            config = load_config()
                            config['current_display'] = message['url']
                            config['display_type'] = 'youtube_cast'
                            save_config(config)
                        else:
                            cmd = f"vlc --fullscreen --no-video-title-show --no-osd '{message['url']}'"
                            cmd_parts = shlex.split(cmd)
                            
                            with process_lock:
                                global current_process
                                current_process = subprocess.Popen(cmd_parts, env={"DISPLAY": ":0"})
                            
                            config = load_config()
                            config['current_display'] = message['url']
                            config['display_type'] = 'media_cast'
                            save_config(config)
                        
                        # Broadcast status update
                        broadcast_status_update()
                        
                        # Send acknowledgment
                        ws.send(json.dumps({
                            'type': 'cast_ack',
                            'status': 'success',
                            'message': f'Playing {media_type}'
                        }))
                    else:
                        ws.send(json.dumps({
                            'type': 'error',
                            'message': 'No URL provided for cast'
                        }))
                
                elif message.get('type') == 'control':
                    # Handle media control commands
                    action = message.get('action')
                    
                    if action == 'stop':
                        stop_display()
                        
                        ws.send(json.dumps({
                            'type': 'control_ack',
                            'status': 'success',
                            'message': 'Stopped display'
                        }))
                    
                    elif action in ['pause', 'resume']:
                        # VLC can be controlled via dbus, but we'll implement a basic version here
                        if action == 'pause':
                            subprocess.run("dbus-send --type=method_call --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Pause", shell=True)
                        else:  # resume
                            subprocess.run("dbus-send --type=method_call --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Play", shell=True)
                        
                        ws.send(json.dumps({
                            'type': 'control_ack',
                            'status': 'success',
                            'message': f'{action.capitalize()} command sent'
                        }))
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {data}")
                ws.send(json.dumps({
                    'type': 'error',
                    'message': 'Invalid JSON format'
                }))
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")
                ws.send(json.dumps({
                    'type': 'error',
                    'message': f'Error: {str(e)}'
                }))
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        # Remove client from the list when disconnected
        with clients_lock:
            if ws in cast_clients:
                cast_clients.remove(ws)

def broadcast_message(message, exclude=None):
    """Broadcast a message to all connected cast clients except the excluded one"""
    message_json = json.dumps(message)
    with clients_lock:
        for client in cast_clients:
            if client != exclude:
                try:
                    client.send(message_json)
                except Exception as e:
                    logger.error(f"Error broadcasting message: {str(e)}")

def broadcast_status_update():
    """Broadcast current status to all connected cast clients"""
    config = load_config()
    status = {
        'type': 'status_update',
        'current_display': config['current_display'],
        'display_type': config['display_type']
    }
    broadcast_message(status)

if __name__ == '__main__':
    # Create images directory if it doesn't exist
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
    
    # Run the app
    app.run(host='0.0.0.0', port=load_config().get('server_port', 5000), debug=False)