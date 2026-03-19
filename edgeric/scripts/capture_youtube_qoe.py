#!/usr/bin/env python3
"""
Capture YouTube QoE metrics using Selenium
Runs inside UE network namespace for cellular testing

Usage:
    sudo ip netns exec ue1 python3 capture_youtube_qoe.py --video "VIDEO_URL" --duration 60 --output qoe.json

Requirements:
    pip install selenium webdriver-manager
    Chrome or Firefox browser installed
"""

import json
import time
import argparse
import sys
import os
from datetime import datetime
from threading import Thread, Event


def get_chrome_driver(headless=True):
    """Initialize Chrome WebDriver"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.add_argument('--mute-audio')
    
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception:
        driver = webdriver.Chrome(options=options)
    
    return driver


def get_firefox_driver(headless=True):
    """Initialize Firefox WebDriver"""
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.set_preference('media.autoplay.default', 0)
    options.set_preference('media.volume_scale', '0.0')
    
    try:
        from webdriver_manager.firefox import GeckoDriverManager
        service = Service(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=options)
    except Exception:
        driver = webdriver.Firefox(options=options)
    
    return driver


# JavaScript to inject for capturing YouTube player metrics
YOUTUBE_METRICS_JS = """
function getYouTubeMetrics() {
    try {
        var player = document.getElementById('movie_player');
        if (!player) {
            return {error: 'Player not found'};
        }
        
        var videoData = player.getVideoData ? player.getVideoData() : {};
        var playbackQuality = player.getPlaybackQuality ? player.getPlaybackQuality() : 'unknown';
        var playerState = player.getPlayerState ? player.getPlayerState() : -2;
        var currentTime = player.getCurrentTime ? player.getCurrentTime() : 0;
        var duration = player.getDuration ? player.getDuration() : 0;
        var loadedFraction = player.getVideoLoadedFraction ? player.getVideoLoadedFraction() : 0;
        var playbackRate = player.getPlaybackRate ? player.getPlaybackRate() : 1;
        
        // Get available quality levels
        var availableQualities = player.getAvailableQualityLevels ? player.getAvailableQualityLevels() : [];
        
        // Get video stats (if available)
        var videoStats = {};
        try {
            var statsForNerds = player.getVideoStats ? player.getVideoStats() : {};
            videoStats = statsForNerds;
        } catch(e) {}
        
        // Get adaptive format info
        var adaptiveFmts = {};
        try {
            if (player.getPlaybackQualityLabel) {
                adaptiveFmts.qualityLabel = player.getPlaybackQualityLabel();
            }
        } catch(e) {}
        
        // Player state mapping
        var stateMap = {
            '-1': 'unstarted',
            '0': 'ended',
            '1': 'playing',
            '2': 'paused',
            '3': 'buffering',
            '5': 'cued'
        };
        
        return {
            timestamp_ms: Date.now(),
            video_id: videoData.video_id || '',
            title: videoData.title || '',
            current_time_s: currentTime,
            duration_s: duration,
            buffered_fraction: loadedFraction,
            buffered_seconds: loadedFraction * duration,
            playback_quality: playbackQuality,
            quality_label: adaptiveFmts.qualityLabel || playbackQuality,
            player_state: stateMap[String(playerState)] || 'unknown',
            player_state_code: playerState,
            playback_rate: playbackRate,
            available_qualities: availableQualities,
            video_stats: videoStats,
            is_buffering: playerState === 3,
            is_playing: playerState === 1
        };
    } catch(e) {
        return {error: e.toString()};
    }
}
return getYouTubeMetrics();
"""


class YouTubeQoECapture:
    def __init__(self, video_url, output_file, duration, interval_ms=100, browser='chrome', headless=True, force_quality=None):
        self.video_url = video_url
        self.output_file = output_file
        self.duration = duration
        self.interval_ms = interval_ms
        self.browser = browser
        self.headless = headless
        self.force_quality = force_quality
        self.driver = None
        self.metrics = []
        self.stop_event = Event()
        
        # QoE tracking
        self.stall_events = []
        self.quality_switches = []
        self.last_quality = None
        self.last_state = None
        self.stall_start_time = None
        self.startup_time = None
        self.first_play_time = None
        
    def start_browser(self):
        """Start the browser"""
        print(f"Starting {self.browser} browser (headless={self.headless})...")
        if self.browser == 'chrome':
            self.driver = get_chrome_driver(self.headless)
        else:
            self.driver = get_firefox_driver(self.headless)
        
    def load_video(self):
        """Load the YouTube video"""
        print(f"Loading video: {self.video_url}")
        self.driver.get(self.video_url)
        time.sleep(3)  # Wait for page load
        
        # Try to dismiss any popups/consent dialogs
        try:
            self.driver.execute_script("""
                // Try to click consent button
                var buttons = document.querySelectorAll('button');
                buttons.forEach(function(btn) {
                    if (btn.textContent.includes('Accept') || btn.textContent.includes('I agree')) {
                        btn.click();
                    }
                });
            """)
            time.sleep(1)
        except Exception:
            pass
        
        # Try to start playback and set highest quality
        try:
            self.driver.execute_script("""
                var player = document.getElementById('movie_player');
                if (player && player.playVideo) {
                    player.playVideo();
                }
            """)
        except Exception:
            pass
        
        time.sleep(2)
        
        # Force highest available quality
        if self.force_quality:
            print(f"Forcing quality to: {self.force_quality}")
            try:
                result = self.driver.execute_script(f"""
                    var player = document.getElementById('movie_player');
                    if (player && player.setPlaybackQualityRange) {{
                        var qualities = player.getAvailableQualityLevels();
                        console.log('Available qualities:', qualities);
                        
                        var targetQuality = '{self.force_quality}';
                        if (targetQuality === 'highest') {{
                            // Get highest non-auto quality
                            targetQuality = qualities.find(q => q !== 'auto') || qualities[0];
                        }}
                        
                        if (qualities.includes(targetQuality)) {{
                            player.setPlaybackQualityRange(targetQuality, targetQuality);
                            return 'Set quality to: ' + targetQuality;
                        }} else {{
                            return 'Quality not available: ' + targetQuality + ', available: ' + qualities.join(',');
                        }}
                    }}
                    return 'Player quality API not available';
                """)
                print(f"  {result}")
            except Exception as e:
                print(f"  Could not set quality: {e}")
        
    def capture_metrics(self):
        """Capture metrics at specified interval"""
        start_time = time.time()
        sample_count = 0
        
        print(f"Capturing metrics every {self.interval_ms}ms for {self.duration}s...")
        
        while not self.stop_event.is_set():
            elapsed = time.time() - start_time
            if elapsed >= self.duration:
                break
            
            try:
                # Execute JavaScript to get metrics
                result = self.driver.execute_script(YOUTUBE_METRICS_JS)
                
                if result and 'error' not in result:
                    # Add local timestamp
                    result['local_timestamp_ms'] = int(time.time() * 1000)
                    result['elapsed_s'] = elapsed
                    result['sample_index'] = sample_count
                    
                    # Track QoE events
                    self._track_qoe_events(result)
                    
                    self.metrics.append(result)
                    sample_count += 1
                    
                    # Progress indicator
                    if sample_count % 100 == 0:
                        print(f"  Captured {sample_count} samples, {elapsed:.1f}s elapsed, "
                              f"state={result.get('player_state', 'unknown')}, "
                              f"quality={result.get('playback_quality', 'unknown')}")
                
            except Exception as e:
                print(f"  Error capturing metrics: {e}", file=sys.stderr)
            
            # Sleep for interval
            time.sleep(self.interval_ms / 1000.0)
        
        print(f"Captured {sample_count} total samples")
        
    def _track_qoe_events(self, result):
        """Track QoE events like stalls, quality switches"""
        current_state = result.get('player_state')
        current_quality = result.get('playback_quality')
        current_time = result.get('local_timestamp_ms', 0)
        
        # Track startup time
        if self.first_play_time is None and current_state == 'playing':
            self.first_play_time = current_time
            self.startup_time = result.get('elapsed_s', 0)
            print(f"  First play at {self.startup_time:.2f}s")
        
        # Track stall events
        if current_state == 'buffering' and self.last_state != 'buffering':
            self.stall_start_time = current_time
        elif self.last_state == 'buffering' and current_state != 'buffering' and self.stall_start_time:
            stall_duration = current_time - self.stall_start_time
            self.stall_events.append({
                'start_ms': self.stall_start_time,
                'end_ms': current_time,
                'duration_ms': stall_duration
            })
            print(f"  Stall event: {stall_duration}ms")
            self.stall_start_time = None
        
        # Track quality switches
        if current_quality and current_quality != self.last_quality and self.last_quality is not None:
            self.quality_switches.append({
                'timestamp_ms': current_time,
                'from': self.last_quality,
                'to': current_quality
            })
            print(f"  Quality switch: {self.last_quality} -> {current_quality}")
        
        self.last_state = current_state
        self.last_quality = current_quality
        
    def save_results(self):
        """Save captured metrics to file"""
        output = {
            'video_url': self.video_url,
            'capture_start': datetime.now().isoformat(),
            'duration_s': self.duration,
            'interval_ms': self.interval_ms,
            'total_samples': len(self.metrics),
            'qoe_summary': {
                'startup_time_s': self.startup_time,
                'total_stalls': len(self.stall_events),
                'total_stall_duration_ms': sum(s['duration_ms'] for s in self.stall_events),
                'quality_switches': len(self.quality_switches),
                'stall_events': self.stall_events,
                'quality_switch_events': self.quality_switches,
            },
            'metrics': self.metrics
        }
        
        with open(self.output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nSaved results to: {self.output_file}")
        print(f"\nQoE Summary:")
        print(f"  Startup time: {self.startup_time:.2f}s" if self.startup_time else "  Startup time: N/A")
        print(f"  Total stalls: {len(self.stall_events)}")
        print(f"  Total stall duration: {sum(s['duration_ms'] for s in self.stall_events)}ms")
        print(f"  Quality switches: {len(self.quality_switches)}")
        
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
            self.load_video()
            self.capture_metrics()
            self.save_results()
        finally:
            self.cleanup()


def main():
    parser = argparse.ArgumentParser(
        description='Capture YouTube QoE metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo ip netns exec ue1 python3 capture_youtube_qoe.py --video "https://www.youtube.com/watch?v=VIDEO_ID" --duration 60
  python3 capture_youtube_qoe.py -v "https://youtu.be/VIDEO_ID" -d 120 -o qoe_metrics.json
  
  # Force 4K quality to stress test throughput:
  python3 capture_youtube_qoe.py -v "URL" -d 120 --quality hd2160
        """
    )
    parser.add_argument('--video', '-v', type=str, required=True,
                       help='YouTube video URL')
    parser.add_argument('--duration', '-d', type=int, default=60,
                       help='Capture duration in seconds (default: 60)')
    parser.add_argument('--output', '-o', type=str, default='youtube_qoe.json',
                       help='Output JSON file (default: youtube_qoe.json)')
    parser.add_argument('--interval', '-i', type=int, default=100,
                       help='Capture interval in ms (default: 100)')
    parser.add_argument('--browser', '-b', type=str, choices=['chrome', 'firefox'],
                       default='chrome', help='Browser to use (default: chrome)')
    parser.add_argument('--no-headless', action='store_true',
                       help='Run browser in visible mode (not headless)')
    parser.add_argument('--quality', '-q', type=str, default=None,
                       choices=['highest', 'hd2160', 'hd1440', 'hd1080', 'hd720', 'large', 'medium', 'small'],
                       help='Force specific quality level (default: auto/ABR)')
    
    args = parser.parse_args()
    
    capture = YouTubeQoECapture(
        video_url=args.video,
        output_file=args.output,
        duration=args.duration,
        interval_ms=args.interval,
        browser=args.browser,
        headless=not args.no_headless,
        force_quality=args.quality
    )
    
    capture.run()


if __name__ == '__main__':
    main()
