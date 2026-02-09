"""
Test script to verify LeetCode scraping functionality
Run this locally before deploying to check if everything works
"""

from backend_scraper import scrape_leetcode, LEETCODE_USERNAME
import json

def test_scraping():
    print("=" * 60)
    print("LEETCODE STATS BACKEND - TEST SCRIPT")
    print("=" * 60)
    print()
    
    print(f"📋 Testing with username: {LEETCODE_USERNAME}")
    print()
    
    # Test LeetCode
    print("🔍 Testing LeetCode scraper...")
    try:
        leetcode_data = scrape_leetcode(LEETCODE_USERNAME)
        if leetcode_data:
            print("✅ LeetCode: SUCCESS")
            print(f"   - Total Solved: {leetcode_data.get('total_solved', 'N/A')}")
            print(f"   - Easy: {leetcode_data.get('easy', 'N/A')}")
            print(f"   - Medium: {leetcode_data.get('medium', 'N/A')}")
            print(f"   - Hard: {leetcode_data.get('hard', 'N/A')}")
            print(f"   - Contest Rating: {leetcode_data.get('contest_rating', 'N/A')}")
            print(f"   - Streak: {leetcode_data.get('streak', 'N/A')} days")
            print(f"   - Ranking: {leetcode_data.get('ranking', 'N/A')}")
            
            # Check heatmap data
            calendar = leetcode_data.get('submission_calendar', {})
            if calendar:
                print(f"   - Heatmap Data: {len(calendar)} days available")
            else:
                print("   - Heatmap Data: No data")
        else:
            print("❌ LeetCode: FAILED (Check username or profile privacy)")
    except Exception as e:
        print(f"❌ LeetCode: ERROR - {str(e)}")
    print()
    
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print()
    print("💡 Tips:")
    print("   - If test failed, double-check the username")
    print("   - Make sure your LeetCode profile is PUBLIC")
    print("   - If test passes, you're ready to deploy! 🚀")
    print()

if __name__ == '__main__':
    test_scraping()