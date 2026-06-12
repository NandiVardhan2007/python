from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import re
import time
import logging
import os

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- Config ----------
LEETCODE_USERNAME   = os.environ.get("LEETCODE_USERNAME",   "Nandu_2007_")
CODECHEF_USERNAME   = os.environ.get("CODECHEF_USERNAME",   "nandu_2007")
CODECHEF_PASSWORD   = os.environ.get("CODECHEF_PASSWORD",   "")   # optional: set for full profile data
HACKERRANK_USERNAME = os.environ.get("HACKERRANK_USERNAME", "24p31a1224")
HACKERRANK_PASSWORD = os.environ.get("HACKERRANK_PASSWORD", "")   # optional
GFG_USERNAME        = os.environ.get("GFG_USERNAME",        "24p31ap7i2")
GFG_PASSWORD        = os.environ.get("GFG_PASSWORD",        "")   # optional
# ----------------------------

# Load .env file if present (local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
    # Re-read after dotenv loads
    LEETCODE_USERNAME   = os.environ.get("LEETCODE_USERNAME",   LEETCODE_USERNAME)
    CODECHEF_USERNAME   = os.environ.get("CODECHEF_USERNAME",   CODECHEF_USERNAME)
    CODECHEF_PASSWORD   = os.environ.get("CODECHEF_PASSWORD",   CODECHEF_PASSWORD)
    HACKERRANK_USERNAME = os.environ.get("HACKERRANK_USERNAME", HACKERRANK_USERNAME)
    HACKERRANK_PASSWORD = os.environ.get("HACKERRANK_PASSWORD", HACKERRANK_PASSWORD)
    GFG_USERNAME        = os.environ.get("GFG_USERNAME",        GFG_USERNAME)
    GFG_PASSWORD        = os.environ.get("GFG_PASSWORD",        GFG_PASSWORD)
except ImportError:
    pass  # python-dotenv not installed; use system env vars directly


def get_selenium_driver():
    """Create and return a headless Chrome WebDriver."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


# ─────────────────────────────────────────────────────
# LeetCode  (GraphQL API — no Selenium needed)
# ─────────────────────────────────────────────────────
def get_leetcode_stats(username):
    """Fetch LeetCode stats via the official GraphQL API."""
    url = "https://leetcode.com/graphql"
    query = """
    query getUserProfile($username: String!) {
        matchedUser(username: $username) {
            username
            profile { ranking }
            submitStats {
                acSubmissionNum { difficulty count }
            }
        }
        userContestRanking(username: $username) {
            rating
            globalRanking
            attendedContestsCount
        }
    }
    """
    calendar_query = """
    query userCalendar($username: String!) {
        matchedUser(username: $username) {
            userCalendar { streak totalActiveDays }
        }
    }
    """
    headers = {
        "Content-Type": "application/json",
        "Referer": f"https://leetcode.com/{username}/",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        resp = requests.post(
            url,
            json={"query": query, "variables": {"username": username}},
            headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        cal_resp = requests.post(
            url,
            json={"query": calendar_query, "variables": {"username": username}},
            headers=headers, timeout=10
        )
        cal_resp.raise_for_status()
        cal_data = cal_resp.json().get("data", {})

        user = data.get("matchedUser") or {}
        contest = data.get("userContestRanking") or {}
        calendar = (cal_data.get("matchedUser") or {}).get("userCalendar") or {}

        stats = {"Easy": 0, "Medium": 0, "Hard": 0, "All": 0}
        for item in (user.get("submitStats") or {}).get("acSubmissionNum", []):
            diff = item.get("difficulty", "")
            if diff in stats:
                stats[diff] = item.get("count", 0)

        return {
            "username": username,
            "total_solved": stats["All"],
            "easy": stats["Easy"],
            "medium": stats["Medium"],
            "hard": stats["Hard"],
            "ranking": (user.get("profile") or {}).get("ranking", "N/A"),
            "contest_rating": round(contest.get("rating", 0), 2) if contest.get("rating") else "N/A",
            "contests_attended": contest.get("attendedContestsCount", 0),
            "global_ranking": contest.get("globalRanking", "N/A"),
            "streak": calendar.get("streak", 0),
            "total_active_days": calendar.get("totalActiveDays", 0),
        }
    except Exception as e:
        logger.error(f"LeetCode error: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────
# CodeChef  (authenticated session + public fallback)
# ─────────────────────────────────────────────────────
def _codechef_login(username, password):
    """Log in to CodeChef via Selenium using exact known element IDs.
    Returns a requests.Session with authenticated cookies, or None on failure.
    Credentials are read from env vars only — never hardcoded.
    """
    driver = None
    try:
        driver = get_selenium_driver()
        logger.info("CodeChef: navigating to login page...")
        driver.get("https://www.codechef.com/login")

        wait = WebDriverWait(driver, 20)

        # Wait for the username field to be clickable (not just present)
        user_field = wait.until(EC.element_to_be_clickable((By.ID, "edit-name")))
        user_field.clear()
        user_field.send_keys(username)
        time.sleep(0.5)

        # Password field
        pass_field = wait.until(EC.element_to_be_clickable((By.ID, "edit-pass")))
        pass_field.clear()
        pass_field.send_keys(password)
        time.sleep(0.5)

        # Click the login-specific submit button (not the registration one)
        submit_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input.cc-login-btn")
        ))
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_btn)
        time.sleep(0.3)
        submit_btn.click()

        # Wait for redirect away from /login (up to 20 s)
        try:
            WebDriverWait(driver, 20).until(
                lambda d: "/login" not in d.current_url
            )
            logger.info(f"CodeChef: login successful → {driver.current_url} ✅")
        except Exception:
            # Check if we're at least on a different page
            if "/login" in driver.current_url:
                # Try checking for error message on page
                err_el = driver.find_elements(By.CSS_SELECTOR, ".messages--error, .error-msg")
                if err_el:
                    logger.error(f"CodeChef login failed: {err_el[0].text}")
                else:
                    logger.warning("CodeChef: still on login page after submit — possible CAPTCHA or wrong credentials")
                return None

        # Transfer browser cookies → requests.Session
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"],
                                domain=cookie.get("domain", ".codechef.com"))
        logger.info("CodeChef: session cookies transferred ✅")
        return session

    except Exception as e:
        logger.error(f"CodeChef login error: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def get_codechef_stats(username, password=None):
    """Fetch CodeChef stats.
    - If a password is available (env var), logs in to get the full profile
      (rating, stars, highest rating, global/country rank).
    - Otherwise falls back to the unauthenticated HTML scrape.
    Credentials are NEVER stored in code — read from env vars only.
    """
    _password = password or CODECHEF_PASSWORD

    # ── Authenticated path ─────────────────────────────────────────────────────
    if _password:
        session = _codechef_login(username, _password)
        if session:
            try:
                page_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml",
                }
                resp = session.get(f"https://www.codechef.com/users/{username}",
                                   headers=page_headers, timeout=12)
                text = resp.text
                soup = BeautifulSoup(text, "html.parser")

                # Rating
                rating = "N/A"
                rating_el = soup.find("div", class_="rating-number")
                if rating_el:
                    rating = rating_el.text.strip()
                if rating == "N/A":
                    m = re.search(r'Drupal\.settings,\s*({.*?})\);', text, re.DOTALL)
                    if m:
                        s = json.loads(m.group(1))
                        v = s.get("user_initial_ratings", {}).get("all")
                        if v is not None:
                            rating = str(v)

                # Stars
                stars = "N/A"
                stars_el = soup.find("span", class_="rating")
                if stars_el:
                    stars = stars_el.text.strip()

                # Highest rating
                highest = "N/A"
                highest_el = soup.find("small")
                if highest_el and "Highest" in highest_el.text:
                    nums = re.findall(r'\d+', highest_el.text)
                    if nums:
                        highest = nums[0]

                # Ranks
                global_rank = country_rank = "N/A"
                rank_els = soup.select(".rating-ranks strong")
                if len(rank_els) >= 2:
                    global_rank  = rank_els[0].text.strip()
                    country_rank = rank_els[1].text.strip()

                # Problems solved
                total_problems = "N/A"
                m2 = re.search(r'Total Problems Solved:\s*(\d+)', text)
                if m2:
                    total_problems = m2.group(1)

                return {
                    "username": username,
                    "rating": rating,
                    "stars": stars,
                    "highest_rating": highest,
                    "total_problems_solved": total_problems,
                    "global_rank": global_rank,
                    "country_rank": country_rank,
                    "authenticated": True,
                }
            except Exception as e:
                logger.error(f"CodeChef authenticated scrape failed: {e}")
                # fall through to unauthenticated

    # ── Unauthenticated path (public HTML) ────────────────────────────────────
    try:
        page_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(f"https://www.codechef.com/users/{username}",
                            headers=page_headers, timeout=12)
        text = resp.text
        soup = BeautifulSoup(text, "html.parser")

        # Rating from Drupal.settings JSON
        rating = "N/A"
        m = re.search(r'Drupal\.settings,\s*({.*?})\);', text, re.DOTALL)
        if m:
            try:
                s = json.loads(m.group(1))
                v = s.get("user_initial_ratings", {}).get("all")
                if v is not None:
                    rating = str(v)
            except Exception:
                pass
        rating_el = soup.find("div", class_="rating-number")
        if rating_el:
            rating = rating_el.text.strip()

        stars_el = soup.find("span", class_="rating")
        stars = stars_el.text.strip() if stars_el else "N/A"

        rank_els = soup.select(".rating-ranks strong")
        global_rank  = rank_els[0].text.strip() if len(rank_els) > 0 else "N/A"
        country_rank = rank_els[1].text.strip() if len(rank_els) > 1 else "N/A"

        total_problems = "N/A"
        m2 = re.search(r'Total Problems Solved:\s*(\d+)', text)
        if m2:
            total_problems = m2.group(1)

        return {
            "username": username,
            "rating": rating,
            "stars": stars,
            "highest_rating": "N/A",
            "total_problems_solved": total_problems,
            "global_rank": global_rank,
            "country_rank": country_rank,
            "authenticated": False,
        }
    except Exception:
        pass  # fall through to Selenium
    driver = None
    try:
        driver = get_selenium_driver()
        url = f"https://www.codechef.com/users/{username}"
        logger.info(f"Fetching CodeChef via Selenium: {url}")
        driver.get(url)

        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(4)

        page_text = driver.page_source
        soup = BeautifulSoup(page_text, "html.parser")

        # ── Parse Drupal.settings JSON block (contains rating data) ──────────
        import json as _json
        rating = highest = global_rank = country_rank = stars = total_problems = "N/A"
        m = re.search(r'Drupal\.settings,\s*({.*?})\);', page_text, re.DOTALL)
        if m:
            try:
                settings = _json.loads(m.group(1))
                all_rating = settings.get("user_initial_ratings", {}).get("all", "N/A")
                rating = str(all_rating)
            except Exception:
                pass

        # ── BS4 fallbacks for remaining fields ───────────────────────────────
        rating_el = soup.find("div", class_="rating-number")
        if rating_el:
            rating = rating_el.text.strip()
        stars_el = soup.find("span", class_="rating")
        if stars_el:
            stars = stars_el.text.strip()
        rank_els = soup.select(".rating-ranks strong")
        if len(rank_els) >= 2:
            global_rank  = rank_els[0].text.strip()
            country_rank = rank_els[1].text.strip()
        solved_sec = soup.find("section", class_="problems-solved")
        if solved_sec:
            h5 = solved_sec.find("h5")
            if h5:
                total_problems = h5.text.split(":")[-1].strip()

        return {
            "username": username,
            "rating": rating,
            "stars": stars,
            "highest_rating": highest,
            "total_problems_solved": total_problems,
            "global_rank": global_rank,
            "country_rank": country_rank,
        }

    except Exception as e:
        logger.error(f"CodeChef Selenium error: {e}")
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()


# ─────────────────────────────────────────────────────
# HackerRank  (REST API — no Selenium needed)
# ─────────────────────────────────────────────────────
def get_hackerrank_stats(username):
    """Fetch HackerRank profile via their internal REST API."""
    url = f"https://www.hackerrank.com/rest/contests/master/hackers/{username}/profile"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        model = resp.json().get("model", {})

        # Fetch badge/certificate details
        badges = []
        try:
            badge_url = f"https://www.hackerrank.com/rest/hackers/{username}/badges"
            badge_resp = requests.get(badge_url, headers=headers, timeout=10)
            if badge_resp.status_code == 200:
                for badge in badge_resp.json().get("models", [])[:5]:
                    badges.append({
                        "name": badge.get("badge_name"),
                        "stars": badge.get("stars", 0),
                    })
        except Exception:
            pass

        return {
            "username": username,
            "name": model.get("name", "N/A"),
            "country": model.get("country", "N/A"),
            "level": model.get("level", "N/A"),
            "followers": model.get("followers_count", 0),
            "school": model.get("school", "N/A"),
            "badges": badges,
        }
    except Exception as e:
        logger.error(f"HackerRank error: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────────────
# GeeksforGeeks  (Selenium — JS-rendered page)
# ─────────────────────────────────────────────────────
def get_gfg_stats(username):
    """Scrape GeeksforGeeks profile using Selenium (JS-rendered). Waits for
    full JS execution then parses page source with BeautifulSoup + regex."""
    driver = None
    try:
        driver = get_selenium_driver()
        url = f"https://www.geeksforgeeks.org/user/{username}/"
        logger.info(f"Fetching GFG: {url}")
        driver.get(url)

        # Wait for JS to finish — then extra buffer for React rendering
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        text = driver.page_source

        # ── Parse score cards using stable partial class names ───────────────
        # GFG uses hashed CSS modules but class names always START with:
        #   ScoreContainer_label__  → label text
        #   ScoreContainer_value__  → numeric value
        coding_score = "N/A"
        total_solved = "N/A"
        institute_rank = "N/A"
        streak = "N/A"

        label_els = soup.find_all("p", class_=re.compile(r"ScoreContainer_label"))
        for lbl in label_els:
            label_text = lbl.get_text(strip=True)
            # The value lives in a sibling/cousin p with ScoreContainer_value class
            row = lbl.find_parent(class_=re.compile(r"ScoreContainer_header"))
            if not row:
                continue
            val_el = row.find("p", class_=re.compile(r"ScoreContainer_value"))
            if not val_el:
                # value might be one level up
                parent = row.find_parent()
                val_el = parent.find("p", class_=re.compile(r"ScoreContainer_value")) if parent else None
            val = val_el.get_text(strip=True) if val_el else "N/A"

            if "Coding Score" in label_text:
                coding_score = val
            elif "Problems Solved" in label_text or "Problem Solved" in label_text:
                total_solved = val
            elif "Institute Rank" in label_text:
                institute_rank = val

        # ── Streak (look for streak container) ───────────────────────────────
        streak_el = soup.find(attrs={"class": re.compile(r"Streak|streak")})
        if streak_el:
            nums = re.findall(r'\d+', streak_el.get_text())
            streak = nums[0] if nums else "N/A"

        # ── Difficulty breakdown ──────────────────────────────────────────────
        difficulty_data = {}
        # Try new DoughnutChart class first
        diff_labels = soup.find_all("span", class_=re.compile(r"DoughnutChart_legendText", re.I))
        if diff_labels:
            for dl in diff_labels:
                text = dl.get_text(strip=True)
                match = re.search(r'([A-Za-z]+)\s*\((\d+)\)', text)
                if match:
                    difficulty_data[match.group(1)] = match.group(2)
        else:
            diff_labels = soup.find_all("p", class_=re.compile(r"problemDifficulty|difficulty", re.I))
            for dl in diff_labels:
                parent = dl.find_parent()
                if parent:
                    nums = re.findall(r'\d+', parent.get_text())
                    if nums:
                        difficulty_data[dl.get_text(strip=True)] = nums[0]

        return {
            "username": username,
            "coding_score": coding_score,
            "total_solved": total_solved,
            "institute_rank": institute_rank,
            "streak": streak,
            "problems_by_difficulty": difficulty_data,
        }

    except Exception as e:
        logger.error(f"GFG Selenium error: {e}")
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()


import threading
from apscheduler.schedulers.background import BackgroundScheduler

# ─────────────────────────────────────────────────────
# Cache Setup
# ─────────────────────────────────────────────────────
CACHE_FILE = "stats_cache.json"

def load_cache():
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

# Global cache
STATS_CACHE = load_cache()

def update_all_stats():
    """Background task to fetch and cache all stats."""
    logger.info("Starting background scrape of all platforms...")
    new_stats = {
        "leetcode":   get_leetcode_stats(LEETCODE_USERNAME),
        "codechef":   get_codechef_stats(CODECHEF_USERNAME),
        "hackerrank": get_hackerrank_stats(HACKERRANK_USERNAME),
        "gfg":        get_gfg_stats(GFG_USERNAME),
    }
    
    global STATS_CACHE
    STATS_CACHE = new_stats
    save_cache(new_stats)
    logger.info("Background scrape complete. Cache updated.")

# ─────────────────────────────────────────────────────
# APScheduler Initialization
# ─────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
# Run every 6 hours
scheduler.add_job(func=update_all_stats, trigger="interval", hours=6)
scheduler.start()

# Also trigger an initial scrape asynchronously if cache is empty
if not STATS_CACHE:
    threading.Thread(target=update_all_stats).start()


# ─────────────────────────────────────────────────────
# Flask Routes
# ─────────────────────────────────────────────────────
@app.route("/api/stats", methods=["GET"])
def get_all_stats():
    """
    Return the cached stats for all platforms.
    """
    if not STATS_CACHE:
        return jsonify({"status": "fetching", "message": "Stats are currently being scraped for the first time. Please try again in a minute."}), 202
    return jsonify(STATS_CACHE)


@app.route("/api/leetcode", methods=["GET"])
def api_leetcode():
    return jsonify(STATS_CACHE.get("leetcode", {}))


@app.route("/api/codechef", methods=["GET"])
def api_codechef():
    return jsonify(STATS_CACHE.get("codechef", {}))


@app.route("/api/hackerrank", methods=["GET"])
def api_hackerrank():
    return jsonify(STATS_CACHE.get("hackerrank", {}))


@app.route("/api/gfg", methods=["GET"])
def api_gfg():
    return jsonify(STATS_CACHE.get("gfg", {}))


@app.route("/api/force-update", methods=["POST"])
def force_update():
    """Trigger a manual update of the stats."""
    threading.Thread(target=update_all_stats).start()
    return jsonify({"status": "started", "message": "Background scrape triggered."}), 202


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
    finally:
        scheduler.shutdown()