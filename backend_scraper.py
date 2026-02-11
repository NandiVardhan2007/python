# backend_scraper.py - FIXED VERSION
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
    "last_successful_update": None,  # NEW: Track when we actually got valid data
    "update_count": 0,
    "failed_attempts": 0  # NEW: Track failed attempts
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

        # Validate that we got actual user data
        if not user_data:
            logger.error(f"No user data found for username: {username}")
            return None

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
        
        logger.info(f"✅ Successfully scraped LeetCode data: {stats['Easy']+stats['Medium']+stats['Hard']} problems solved")
        return result
        
    except requests.exceptions.Timeout:
        logger.error("⏱️ Request timed out while scraping LeetCode")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"🌐 Network error scraping LeetCode: {e}")
        return None
    except Exception as e:
        logger.exception("❌ Unexpected error scraping LeetCode")
        return None

def update_all_stats():
    """Fetch and update cached_data - FIXED VERSION."""
    logger.info(f"⏰ Scheduled update triggered at {datetime.now().isoformat()}")
    
    # Always update the last_updated timestamp (when we tried)
    cached_data['last_updated'] = datetime.now().isoformat()
    
    try:
        leetcode_data = scrape_leetcode(LEETCODE_USERNAME)
        
        if leetcode_data:
            # SUCCESS: Update the cached data
            cached_data['leetcode'] = leetcode_data
            cached_data['update_count'] += 1
            cached_data['last_successful_update'] = datetime.now().isoformat()
            cached_data['failed_attempts'] = 0  # Reset failed attempts counter
            
            logger.info(f"✅ Stats updated successfully (Update #{cached_data['update_count']})")
            logger.info(f"📊 Total Solved: {leetcode_data['total_solved']} (E:{leetcode_data['easy']}, M:{leetcode_data['medium']}, H:{leetcode_data['hard']})")
            return True
        else:
            # FAILURE: Keep old data but track the failure
            cached_data['failed_attempts'] += 1
            logger.error(f"❌ Failed to fetch LeetCode data (Failure #{cached_data['failed_attempts']})")
            
            # If we have old data, keep using it
            if cached_data['leetcode']:
                logger.warning(f"⚠️ Keeping previous cached data from {cached_data.get('last_successful_update', 'unknown')}")
            
            return False
            
    except Exception as e:
        cached_data['failed_attempts'] += 1
        logger.exception(f"❌ Exception in update_all_stats (Failure #{cached_data['failed_attempts']}): {e}")
        return False

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Return cached stats."""
    logger.info(f"📊 Stats requested - Last updated: {cached_data.get('last_updated', 'Never')}, Last successful: {cached_data.get('last_successful_update', 'Never')}")
    
    # Return the full cached_data so frontend knows about failed attempts
    return jsonify(cached_data)

@app.route('/api/refresh', methods=['GET', 'POST'])
def force_refresh():
    """Manually trigger a stats update."""
    logger.info("🔄 Manual refresh triggered")
    
    # Attempt the update
    success = update_all_stats()
    
    if success:
        return jsonify({
            'status': 'success', 
            'message': 'Stats refreshed successfully',
            'last_updated': cached_data.get('last_updated'),
            'last_successful_update': cached_data.get('last_successful_update'),
            'update_count': cached_data.get('update_count', 0),
            'leetcode': cached_data.get('leetcode')  # Include the actual data
        })
    else:
        return jsonify({
            'status': 'error',
            'message': 'Failed to refresh stats',
            'last_updated': cached_data.get('last_updated'),
            'last_successful_update': cached_data.get('last_successful_update'),
            'failed_attempts': cached_data.get('failed_attempts', 0),
            'leetcode': cached_data.get('leetcode')  # Return old data if available
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    has_data = cached_data.get('leetcode') is not None
    
    return jsonify({
        'status': 'healthy', 
        'timestamp': datetime.now().isoformat(),
        'last_updated': cached_data.get('last_updated'),
        'last_successful_update': cached_data.get('last_successful_update'),
        'update_count': cached_data.get('update_count', 0),
        'failed_attempts': cached_data.get('failed_attempts', 0),
        'scheduler_enabled': not DISABLE_SCHEDULER,
        'has_cached_data': has_data
    })

# -------------------------
# Scheduler initialization
# -------------------------
scheduler = None

def start_scheduler():
    """Initialize and start the background scheduler."""
    global scheduler
    
    if DISABLE_SCHEDULER:
        logger.info("🔒 Scheduler disabled via DISABLE_SCHEDULER env var.")
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
        success = update_all_stats()
        if success:
            logger.info("🎉 Initial update completed successfully")
        else:
            logger.warning("⚠️ Initial update failed, will retry on next scheduled run")
    except Exception as e:
        logger.exception(f"❌ Initial update failed with exception: {e}")

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