#!/usr/bin/env python3
"""
Capture WebRTC QoE metrics using Selenium with Jitsi Meet
Runs inside UE network namespace for cellular testing

Captures real-time metrics including:
- RTT (round-trip time)
- Jitter
- Packet loss
- Bitrate (audio/video)
- Frame rate
- Resolution

Usage:
    sudo ip netns exec ue1 python3 capture_webrtc_qoe.py --room "test-room" --duration 60 --output webrtc_qoe.json

Requirements:
    pip install selenium webdriver-manager
    Chrome browser installed
"""

import json
import time
import argparse
import sys
import os
import random
import string
from datetime import datetime
from threading import Event


def get_chrome_driver(headless=True):
    """Initialize Chrome WebDriver with WebRTC permissions"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    
    options = Options()
    if headless:
        options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    
    # WebRTC specific settings
    options.add_argument('--use-fake-ui-for-media-stream')  # Auto-allow camera/mic
    options.add_argument('--use-fake-device-for-media-stream')  # Use fake media
    options.add_argument('--allow-running-insecure-content')
    options.add_argument('--disable-web-security')
    
    # Reduce resource usage
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-infobars')
    
    # Performance improvements
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)
    
    # Set page load timeout
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    
    return driver


# JavaScript to extract WebRTC stats from peer connections
WEBRTC_STATS_JS = """
async function getWebRTCStats() {
    const stats = {
        timestamp_ms: Date.now(),
        peer_connections: [],
        audio: { inbound: [], outbound: [] },
        video: { inbound: [], outbound: [] },
        candidates: [],
        summary: {
            rtt_ms: null,
            jitter_ms: null,
            packet_loss_percent: null,
            audio_bitrate_kbps: null,
            video_bitrate_kbps: null,
            video_framerate: null,
            video_resolution: null,
            connection_state: 'unknown'
        }
    };
    
    // Find all RTCPeerConnections (Jitsi uses window.APP.conference)
    let pcs = [];
    
    // Try Jitsi-specific method first
    if (window.APP && window.APP.conference && window.APP.conference._room) {
        try {
            const jitsiRoom = window.APP.conference._room;
            if (jitsiRoom.jvbJingleSession && jitsiRoom.jvbJingleSession.peerconnection) {
                const pc = jitsiRoom.jvbJingleSession.peerconnection.peerconnection;
                if (pc) pcs.push(pc);
            }
        } catch(e) {}
    }
    
    // Also try to get from window if available
    if (window._peerConnections) {
        pcs = pcs.concat(Array.from(window._peerConnections));
    }
    
    // Fallback: intercept RTCPeerConnection
    if (pcs.length === 0 && window._rtcPeerConnections) {
        pcs = Array.from(window._rtcPeerConnections);
    }
    
    if (pcs.length === 0) {
        // Try to find through Jitsi's internal API
        try {
            if (window.JitsiMeetJS && window.APP && window.APP.conference) {
                const tracks = window.APP.conference.getLocalTracks();
                stats.has_local_tracks = tracks.length > 0;
            }
        } catch(e) {}
        
        return stats;
    }
    
    for (const pc of pcs) {
        try {
            const pcStats = await pc.getStats();
            let rtts = [];
            let jitters = [];
            let packetsLost = 0;
            let packetsReceived = 0;
            
            pcStats.forEach(report => {
                // Candidate pair stats (for RTT)
                if (report.type === 'candidate-pair' && report.state === 'succeeded') {
                    if (report.currentRoundTripTime !== undefined) {
                        rtts.push(report.currentRoundTripTime * 1000); // Convert to ms
                    }
                    stats.candidates.push({
                        local_candidate_id: report.localCandidateId,
                        remote_candidate_id: report.remoteCandidateId,
                        rtt_ms: report.currentRoundTripTime ? report.currentRoundTripTime * 1000 : null,
                        bytes_sent: report.bytesSent,
                        bytes_received: report.bytesReceived,
                        state: report.state
                    });
                }
                
                // Inbound RTP (receiving)
                if (report.type === 'inbound-rtp') {
                    const mediaType = report.kind || report.mediaType;
                    const entry = {
                        ssrc: report.ssrc,
                        packets_received: report.packetsReceived,
                        packets_lost: report.packetsLost,
                        bytes_received: report.bytesReceived,
                        jitter: report.jitter ? report.jitter * 1000 : null, // Convert to ms
                        codec: report.codecId
                    };
                    
                    if (report.jitter !== undefined) {
                        jitters.push(report.jitter * 1000);
                    }
                    packetsLost += report.packetsLost || 0;
                    packetsReceived += report.packetsReceived || 0;
                    
                    if (mediaType === 'audio') {
                        stats.audio.inbound.push(entry);
                    } else if (mediaType === 'video') {
                        entry.frames_received = report.framesReceived;
                        entry.frames_decoded = report.framesDecoded;
                        entry.frames_dropped = report.framesDropped;
                        entry.frame_width = report.frameWidth;
                        entry.frame_height = report.frameHeight;
                        entry.frames_per_second = report.framesPerSecond;
                        stats.video.inbound.push(entry);
                        
                        if (report.frameWidth && report.frameHeight) {
                            stats.summary.video_resolution = `${report.frameWidth}x${report.frameHeight}`;
                        }
                        if (report.framesPerSecond) {
                            stats.summary.video_framerate = report.framesPerSecond;
                        }
                    }
                }
                
                // Outbound RTP (sending)
                if (report.type === 'outbound-rtp') {
                    const mediaType = report.kind || report.mediaType;
                    const entry = {
                        ssrc: report.ssrc,
                        packets_sent: report.packetsSent,
                        bytes_sent: report.bytesSent,
                        target_bitrate: report.targetBitrate
                    };
                    
                    if (mediaType === 'audio') {
                        stats.audio.outbound.push(entry);
                    } else if (mediaType === 'video') {
                        entry.frames_encoded = report.framesEncoded;
                        entry.frame_width = report.frameWidth;
                        entry.frame_height = report.frameHeight;
                        entry.frames_per_second = report.framesPerSecond;
                        stats.video.outbound.push(entry);
                    }
                }
            });
            
            // Calculate summaries
            if (rtts.length > 0) {
                stats.summary.rtt_ms = rtts.reduce((a, b) => a + b, 0) / rtts.length;
            }
            if (jitters.length > 0) {
                stats.summary.jitter_ms = jitters.reduce((a, b) => a + b, 0) / jitters.length;
            }
            if (packetsReceived > 0) {
                stats.summary.packet_loss_percent = (packetsLost / (packetsReceived + packetsLost)) * 100;
            }
            
            stats.summary.connection_state = pc.connectionState || pc.iceConnectionState || 'unknown';
            
        } catch(e) {
            stats.error = e.toString();
        }
    }
    
    return stats;
}

return await getWebRTCStats();
"""

# JavaScript to intercept RTCPeerConnection creation
INTERCEPT_PC_JS = """
if (!window._rtcPeerConnections) {
    window._rtcPeerConnections = new Set();
    const OriginalRTCPeerConnection = window.RTCPeerConnection;
    window.RTCPeerConnection = function(...args) {
        const pc = new OriginalRTCPeerConnection(...args);
        window._rtcPeerConnections.add(pc);
        pc.addEventListener('connectionstatechange', () => {
            if (pc.connectionState === 'closed') {
                window._rtcPeerConnections.delete(pc);
            }
        });
        return pc;
    };
    window.RTCPeerConnection.prototype = OriginalRTCPeerConnection.prototype;
}
return true;
"""


class WebRTCQoECapture:
    def __init__(self, room_name, output_file, duration, interval_ms=100, 
                 headless=True, jitsi_server="meet.jit.si"):
        self.room_name = room_name
        self.output_file = output_file
        self.duration = duration
        self.interval_ms = interval_ms
        self.headless = headless
        self.jitsi_server = jitsi_server
        self.driver = None
        self.metrics = []
        self.stop_event = Event()
        
        # QoE tracking
        self.rtt_samples = []
        self.jitter_samples = []
        self.packet_loss_samples = []
        self.connection_established_time = None
        self.first_media_time = None
        
    def start_browser(self):
        """Start the browser"""
        print(f"Starting Chrome browser (headless={self.headless})...")
        self.driver = get_chrome_driver(self.headless)
        
        # Inject PeerConnection interceptor early
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': INTERCEPT_PC_JS.replace('return true;', '')
        })
        
    def join_room(self):
        """Join the Jitsi meeting room"""
        room_url = f"https://{self.jitsi_server}/{self.room_name}"
        print(f"Joining room: {room_url}")
        
        try:
            self.driver.get(room_url)
            print("  Page loaded successfully")
        except Exception as e:
            print(f"  Page load timeout or error: {e}")
            print("  Continuing anyway...")
        
        time.sleep(2)
        
        # Inject PC interceptor again after page load
        try:
            self.driver.execute_script(INTERCEPT_PC_JS)
            print("  Injected PeerConnection interceptor")
        except Exception as e:
            print(f"  Warning: Could not inject interceptor: {e}")
        
        # Wait for Jitsi to initialize
        print("Waiting for Jitsi to initialize...")
        
        # Wait up to 30 seconds for Jitsi to be ready
        for i in range(15):
            time.sleep(2)
            try:
                # Check page state
                ready_state = self.driver.execute_script("return document.readyState")
                print(f"  [{i*2}s] Page state: {ready_state}")
                
                # Check if Jitsi APP is loaded
                has_app = self.driver.execute_script("return typeof window.APP !== 'undefined'")
                if has_app:
                    print(f"  [{i*2}s] Jitsi APP loaded!")
                    break
            except Exception as e:
                print(f"  [{i*2}s] Checking... {e}")
        
        # Try to join without entering name (click prejoin button if exists)
        print("Attempting to join meeting...")
        try:
            self.driver.execute_script("""
                // Click "Join meeting" button if exists
                var joinBtns = document.querySelectorAll('button');
                joinBtns.forEach(function(btn) {
                    var text = btn.textContent.toLowerCase();
                    if (text.includes('join') || text.includes('start')) {
                        console.log('Clicking: ' + btn.textContent);
                        btn.click();
                    }
                });
                
                // Also try input field and enter
                var inputs = document.querySelectorAll('input');
                inputs.forEach(function(inp) {
                    if (inp.placeholder && inp.placeholder.toLowerCase().includes('name')) {
                        inp.value = 'EdgeRIC-Test';
                        inp.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                });
            """)
        except Exception as e:
            print(f"  Join attempt error: {e}")
        
        time.sleep(3)
        
        # Check if we're connected
        try:
            state = self.driver.execute_script("""
                if (window.APP && window.APP.conference && window.APP.conference._room) {
                    return 'connected';
                }
                if (window.APP && window.APP.conference) {
                    return 'conference_exists';
                }
                if (window.APP) {
                    return 'app_exists';
                }
                return 'waiting';
            """)
            print(f"  Jitsi state: {state}")
        except Exception as e:
            print(f"  State check error: {e}")
        
    def capture_metrics(self):
        """Capture WebRTC metrics at specified interval"""
        start_time = time.time()
        sample_count = 0
        
        print(f"Capturing WebRTC metrics every {self.interval_ms}ms for {self.duration}s...")
        
        while not self.stop_event.is_set():
            elapsed = time.time() - start_time
            if elapsed >= self.duration:
                break
            
            try:
                result = self.driver.execute_script(WEBRTC_STATS_JS)
                
                if result:
                    result['local_timestamp_ms'] = int(time.time() * 1000)
                    result['elapsed_s'] = elapsed
                    result['sample_index'] = sample_count
                    
                    # Track QoE metrics
                    self._track_qoe_metrics(result)
                    
                    self.metrics.append(result)
                    sample_count += 1
                    
                    # Progress indicator
                    if sample_count % 50 == 0:
                        summary = result.get('summary', {})
                        rtt = summary.get('rtt_ms')
                        jitter = summary.get('jitter_ms')
                        loss = summary.get('packet_loss_percent')
                        state = summary.get('connection_state', 'unknown')
                        
                        rtt_str = f"{rtt:.1f}ms" if rtt else "N/A"
                        jitter_str = f"{jitter:.1f}ms" if jitter else "N/A"
                        loss_str = f"{loss:.2f}%" if loss is not None else "N/A"
                        
                        print(f"  [{elapsed:.1f}s] samples={sample_count}, "
                              f"RTT={rtt_str}, jitter={jitter_str}, "
                              f"loss={loss_str}, state={state}")
                
            except Exception as e:
                print(f"  Error capturing metrics: {e}", file=sys.stderr)
            
            time.sleep(self.interval_ms / 1000.0)
        
        print(f"Captured {sample_count} total samples")
        
    def _track_qoe_metrics(self, result):
        """Track QoE metrics for summary"""
        summary = result.get('summary', {})
        
        # Track when connection is established
        if self.connection_established_time is None:
            state = summary.get('connection_state', '')
            if state in ['connected', 'completed']:
                self.connection_established_time = result.get('elapsed_s')
                print(f"  Connection established at {self.connection_established_time:.2f}s")
        
        # Collect samples for statistical analysis
        if summary.get('rtt_ms') is not None:
            self.rtt_samples.append(summary['rtt_ms'])
        if summary.get('jitter_ms') is not None:
            self.jitter_samples.append(summary['jitter_ms'])
        if summary.get('packet_loss_percent') is not None:
            self.packet_loss_samples.append(summary['packet_loss_percent'])
            
    def _calculate_stats(self, samples):
        """Calculate statistics for a list of samples"""
        if not samples:
            return None
        
        import statistics
        return {
            'min': min(samples),
            'max': max(samples),
            'mean': statistics.mean(samples),
            'median': statistics.median(samples),
            'stdev': statistics.stdev(samples) if len(samples) > 1 else 0,
            'p95': sorted(samples)[int(len(samples) * 0.95)] if samples else None,
            'p99': sorted(samples)[int(len(samples) * 0.99)] if samples else None,
            'count': len(samples)
        }
        
    def save_results(self):
        """Save captured metrics to file"""
        output = {
            'room_name': self.room_name,
            'jitsi_server': self.jitsi_server,
            'capture_start': datetime.now().isoformat(),
            'duration_s': self.duration,
            'interval_ms': self.interval_ms,
            'total_samples': len(self.metrics),
            'qoe_summary': {
                'connection_established_s': self.connection_established_time,
                'rtt_stats_ms': self._calculate_stats(self.rtt_samples),
                'jitter_stats_ms': self._calculate_stats(self.jitter_samples),
                'packet_loss_stats_percent': self._calculate_stats(self.packet_loss_samples),
            },
            'metrics': self.metrics
        }
        
        with open(self.output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nSaved results to: {self.output_file}")
        print(f"\nQoE Summary:")
        print(f"  Connection established: {self.connection_established_time:.2f}s" 
              if self.connection_established_time else "  Connection: Not established")
        
        if self.rtt_samples:
            rtt_stats = self._calculate_stats(self.rtt_samples)
            print(f"  RTT: mean={rtt_stats['mean']:.1f}ms, "
                  f"p95={rtt_stats['p95']:.1f}ms, max={rtt_stats['max']:.1f}ms")
        
        if self.jitter_samples:
            jitter_stats = self._calculate_stats(self.jitter_samples)
            print(f"  Jitter: mean={jitter_stats['mean']:.1f}ms, "
                  f"p95={jitter_stats['p95']:.1f}ms, max={jitter_stats['max']:.1f}ms")
        
        if self.packet_loss_samples:
            loss_stats = self._calculate_stats(self.packet_loss_samples)
            print(f"  Packet Loss: mean={loss_stats['mean']:.2f}%, max={loss_stats['max']:.2f}%")
        
    def cleanup(self):
        """Clean up browser"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            
    def run(self):
        """Main run method"""
        try:
            self.start_browser()
            self.join_room()
            self.capture_metrics()
            self.save_results()
        finally:
            self.cleanup()


def generate_room_name():
    """Generate a random room name"""
    return 'edgeric-test-' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def main():
    parser = argparse.ArgumentParser(
        description='Capture WebRTC QoE metrics from Jitsi Meet',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with random room
  sudo ip netns exec ue1 python3 capture_webrtc_qoe.py --duration 60

  # Join specific room
  python3 capture_webrtc_qoe.py --room my-test-room --duration 120 --output webrtc_qoe.json
  
  # Use different Jitsi server
  python3 capture_webrtc_qoe.py --server 8x8.vc --room test-room --duration 60
        """
    )
    parser.add_argument('--room', '-r', type=str, default=None,
                       help='Jitsi room name (default: random generated)')
    parser.add_argument('--server', '-s', type=str, default='meet.jit.si',
                       help='Jitsi server (default: meet.jit.si)')
    parser.add_argument('--duration', '-d', type=int, default=60,
                       help='Capture duration in seconds (default: 60)')
    parser.add_argument('--output', '-o', type=str, default='webrtc_qoe.json',
                       help='Output JSON file (default: webrtc_qoe.json)')
    parser.add_argument('--interval', '-i', type=int, default=100,
                       help='Capture interval in ms (default: 100)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Run browser in visible mode (not headless)')
    
    args = parser.parse_args()
    
    room_name = args.room if args.room else generate_room_name()
    
    print(f"Room: {room_name}")
    print(f"Server: {args.server}")
    
    capture = WebRTCQoECapture(
        room_name=room_name,
        output_file=args.output,
        duration=args.duration,
        interval_ms=args.interval,
        headless=not args.no_headless,
        jitsi_server=args.server
    )
    
    capture.run()


if __name__ == '__main__':
    main()
