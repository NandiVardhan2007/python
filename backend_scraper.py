from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import os
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
CORS(app)

# Store cached data
cached_data = {
    'leetcode': None,
    'last_updated': None
}

# Configure your username here
LEETCODE_USERNAME = 'Nandu_2007_'  # Change this to your LeetCode username

def scrape_leetcode(username):
    """Scrape LeetCode stats including heatmap data"""
    try:
        # GraphQL query for user profile
        url = "https://leetcode.com/graphql"
        
        # Query for user stats
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
        
        # Query for submission calendar (heatmap)
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
            'Referer': f'https://leetcode.com/{username}/'
        }
        
        # Get user stats
        response = requests.post(url, json={
            'query': query,
            'variables': {'username': username}
        }, headers=headers, timeout=10)
        
        data = response.json()
        
        # Get calendar data
        calendar_response = requests.post(url, json={
            'query': calendar_query,
            'variables': {'username': username}
        }, headers=headers, timeout=10)
        
        calendar_data = calendar_response.json()
        
        if 'errors' in data or 'errors' in calendar_data:
            return None
            
        user_data = data.get('data', {}).get('matchedUser', {})
        contest_data = data.get('data', {}).get('userContestRanking', {})
        calendar = calendar_data.get('data', {}).get('matchedUser', {}).get('userCalendar', {})
        
        # Parse submission stats
        stats = {'Easy': 0, 'Medium': 0, 'Hard': 0}
        for item in user_data.get('submitStats', {}).get('acSubmissionNum', []):
            difficulty = item.get('difficulty', '')
            if difficulty in stats:
                stats[difficulty] = item.get('count', 0)
        
        # Parse calendar data
        submission_calendar = {}
        if calendar.get('submissionCalendar'):
            calendar_json = json.loads(calendar.get('submissionCalendar', '{}'))
            submission_calendar = calendar_json
        
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
        print(f"Error scraping LeetCode: {e}")
        return None

def update_all_stats():
    """Update stats from LeetCode"""
    global cached_data
    
    print(f"Updating stats at {datetime.now()}")
    
    # Scrape LeetCode
    leetcode_data = scrape_leetcode(LEETCODE_USERNAME)
    if leetcode_data:
        cached_data['leetcode'] = leetcode_data
    
    cached_data['last_updated'] = datetime.now().isoformat()
    print("Stats updated successfully")

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API endpoint to get all coding stats"""
    return jsonify(cached_data)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    # Initialize scheduler
    scheduler = BackgroundScheduler()
    
    # Update stats immediately on startup
    update_all_stats()
    
    # Schedule updates every 6 hours
    scheduler.add_job(func=update_all_stats, trigger="interval", hours=6)
    scheduler.start()
    
    # Get port from environment variable (for Render deployment)
    port = int(os.environ.get('PORT', 5000))
    
    try:
        app.run(host='0.0.0.0', port=port, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()