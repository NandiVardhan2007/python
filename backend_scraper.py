# backend_scraper.py
from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ---------- Config ----------
LEETCODE_USERNAME = os.environ.get("LEETCODE_USERNAME", "Nandu_2007_")  # or set in Render env
SCHEDULER_INTERVAL_HOURS = int(os.environ.get("SCHEDULER_INTERVAL_HOURS", 1))
DISABLE_SCHEDULER = os.environ.get("DISABLE_SCHEDULER", "0") == "1"
# ----------------------------

# Store cached data
cached_data = {
    "leetcode": None,
    "last_updated": None
}

def scrape_leetcode(username):
    """Scrape LeetCode stats using LeetCode GraphQL."""
    try:
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
        headers = {'Content-Type': 'application/json', 'Referer': f'https://leetcode.com/{username}/'}
        response = requests.post(url, json={'query': query, 'variables': {'username': username}}, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        calendar_response = requests.post(url, json={'query': calendar_query, 'variables': {'username': username}}, headers=headers, timeout=10)
        calendar_response.raise_for_status()
        calendar_data = calendar_response.json()

        if 'errors' in data or 'errors' in calendar_data:
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
            except Exception:
                submission_calendar = {}

        return {
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
    except Exception as e:
        app.logger.exception("Error scraping LeetCode")
        return None

def update_all_stats():
    """Fetch and update cached_data."""
    app.logger.info(f"Updating stats at {datetime.now().isoformat()}")
    try:
        leetcode_data = scrape_leetcode(LEETCODE_USERNAME)
        if leetcode_data:
            cached_data['leetcode'] = leetcode_data
        cached_data['last_updated'] = datetime.now().isoformat()
        app.logger.info("Stats updated successfully")
    except Exception:
        app.logger.exception("Failed to update stats")

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify(cached_data)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# -------------------------
# Scheduler initialization
# -------------------------
_scheduler = None

def _start_scheduler_if_needed():
    global _scheduler
    if DISABLE_SCHEDULER:
        app.logger.info("Scheduler disabled via DISABLE_SCHEDULER env var.")
        return

    # Prevent starting multiple times if module reloaded
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler()
    # Run the update job periodically
    _scheduler.add_job(func=update_all_stats, trigger="interval", hours=SCHEDULER_INTERVAL_HOURS, id="update_stats_job", replace_existing=True)
    _scheduler.start()
    # Run once on startup to populate cache
    try:
        update_all_stats()
    except Exception:
        app.logger.exception("Initial update failed")

# Start scheduler when module is imported (Gunicorn imports this module)
# For Flask dev server with reloader, ensure we start only on the actual child process
if os.environ.get("WERKZEUG_RUN_MAIN") is None or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _start_scheduler_if_needed()

# -------------------------
# Local dev entrypoint
# -------------------------
if __name__ == '__main__':
    # Local development server (not used by gunicorn)
    # Use a small timeout to make dev quicker if needed
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=False)
