# backend_scraper.py
from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import atexit
import logging

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ---------- Config ----------
LEETCODE_USERNAME = os.environ.get("LEETCODE_USERNAME", "Nandu_2007_")
SCHEDULER_INTERVAL_HOURS = int(os.environ.get("SCHEDULER_INTERVAL_HOURS", 1))
DISABLE_SCHEDULER = os.environ.get("DISABLE_SCHEDULER", "0") == "1"
# ----------------------------

# Store cached data
cached_data = {
    "leetcode": None,
    "last_updated": None,
    "update_count": 0  # Track how many times we've updated
}

def scrape_leetcode(username):
    """Scrape LeetCode stats using LeetCode GraphQL."""
    try:
        logger.info(f"Starting LeetCode scrape for user: {username}")
        url = "https://leetcode.com/graphql"
        query = """
        query getUserProfile($username: String!) {
            matchedUser(username: $username) {
                username
                submitStats {
                    acSubmissionNum {
                        difficulty
                        count
                    }
                }
                profile {
                    ranking
                    reputation
                }
            }
            userContestRanking(username: $username) {
                attendedContestsCount
                rating
                globalRanking
            }
        }
        """
        calendar_query = """
        query userProfileCalendar($username: String!) {
            matchedUser(username: $username) {
                userCalendar {
                    activeYears
                    streak
                    totalActiveDays
                    submissionCalendar
                }
            }
        }
        """
        headers = {
            'Content-Type': 'application/json', 
            'Referer': f'https://leetcode.com/{username}/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.post(
            url, 
            json={'query': query, 'variables': {'username': username}}, 
            headers=headers, 
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        calendar_response = requests.post(
            url, 
            json={'query': calendar_query, 'variables': {'username': username}}, 
            headers=headers, 
            timeout=10
        )
        calendar_response.raise_for_status()
        calendar_data = calendar_response.json()

        if 'errors' in data or 'errors' in calendar_data:
            logger.error(f"GraphQL errors in response: {data.get('errors', calendar_data.get('errors'))}")
            return None

        user_data = data.get('data', {}).get('matchedUser', {}) or {}
        contest_data = data.get('data', {}).get('userContestRanking', {}) or {}
        calendar = calendar_data.get('data', {}).get('matchedUser', {}).get('userCalendar', {}) or {}

        stats = {'Easy': 0, 'Medium': 0, 'Hard': 0}
        for item in user_data.get('submitStats', {}).get('acSubmissionNum', []) or []:
            difficulty = item.get('difficulty', '')
            if difficulty in stats:
                stats[difficulty] = item.get('count', 0)

        submission_calendar = {}
        if calendar.get('submissionCalendar'):
            try:
                submission_calendar = json.loads(calendar.get('submissionCalendar', '{}'))
            except Exception as e:
                logger.warning(f"Failed to parse submission calendar: {e}")
                submission_calendar = {}

        result = {
            'username': username,
            'total_solved': stats['Easy'] + stats['Medium'] + stats['Hard'],
            'easy': stats['Easy'],
            'medium': stats['Medium'],
            'hard': stats['Hard'],
            'ranking': user_data.get('profile', {}).get('ranking', 'N/A'),
            'reputation': user_data.get('profile', {}).get('reputation', 0),
            'contest_rating': contest_data.get('rating', 'N/A') if contest_data else 'N/A',
            'contests_attended': contest_data.get('attendedContestsCount', 0) if contest_data else 0,
            'global_ranking': contest_data.get('globalRanking', 'N/A') if contest_data else 'N/A',
            'streak': calendar.get('streak', 0),
            'total_active_days': calendar.get('totalActiveDays', 0),
            'submission_calendar': submission_calendar
        }
        
        logger.info(f"Successfully scraped LeetCode data: {stats['Easy']+stats['Medium']+stats['Hard']} problems solved")
        return result
        
    except Exception as e:
        logger.exception("Error scraping LeetCode")
        return None

def update_all_stats():
    """Fetch and update cached_data."""
    logger.info(f"⏰ Scheduled update triggered at {datetime.now().isoformat()}")
    try:
        leetcode_data = scrape_leetcode(LEETCODE_USERNAME)
        if leetcode_data:
            cached_data['leetcode'] = leetcode_data
            cached_data['update_count'] += 1
            logger.info(f"✅ Stats updated successfully (Update #{cached_data['update_count']})")
        else:
            logger.error("❌ Failed to fetch LeetCode data")
            
        cached_data['last_updated'] = datetime.now().isoformat()
        
    except Exception:
        logger.exception("Failed to update stats")

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Return cached stats."""
    logger.info(f"Stats requested - Last updated: {cached_data.get('last_updated', 'Never')}")
    return jsonify(cached_data)

@app.route('/api/refresh', methods=['POST'])
def force_refresh():
    """Manually trigger a stats update."""
    logger.info("Manual refresh triggered")
    update_all_stats()
    return jsonify({
        'status': 'success', 
        'message': 'Stats refreshed',
        'last_updated': cached_data.get('last_updated')
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'last_updated': cached_data.get('last_updated'),
        'update_count': cached_data.get('update_count', 0),
        'scheduler_enabled': not DISABLE_SCHEDULER
    })

# -------------------------
# Scheduler initialization
# -------------------------
scheduler = None

def start_scheduler():
    """Initialize and start the background scheduler."""
    global scheduler
    
    if DISABLE_SCHEDULER:
        logger.info("📛 Scheduler disabled via DISABLE_SCHEDULER env var.")
        return

    if scheduler is not None:
        logger.warning("Scheduler already running, skipping initialization")
        return

    logger.info(f"🚀 Starting scheduler (interval: {SCHEDULER_INTERVAL_HOURS} hour(s))")
    scheduler = BackgroundScheduler(daemon=True)
    
    # Add the periodic job
    scheduler.add_job(
        func=update_all_stats, 
        trigger="interval", 
        hours=SCHEDULER_INTERVAL_HOURS, 
        id="update_stats_job", 
        replace_existing=True,
        max_instances=1  # Prevent overlapping runs
    )
    
    scheduler.start()
    logger.info("✅ Scheduler started successfully")
    
    # Initial update on startup
    try:
        logger.info("Running initial stats update...")
        update_all_stats()
    except Exception:
        logger.exception("Initial update failed")

    # Register shutdown handler
    atexit.register(lambda: scheduler.shutdown() if scheduler else None)

# Start scheduler when the module is loaded
# Only start in the main process (not reloader process)
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_scheduler()

# -------------------------
# Local dev entrypoint
# -------------------------
if __name__ == '__main__':
    # Local development server (not used by gunicorn)
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)