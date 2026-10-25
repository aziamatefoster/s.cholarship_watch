"""Scholarship Watch.

Visits each page listed in sources.json, finds links that look like scholarship
posts, compares them with what it saw last time (state.json) and emails a
digest of anything new.

Usage:
    python watch.py              check all sources and email new posts
    python watch.py --dry-run    check and print the digest, send nothing
"""
import datetime
import hashlib
import json
import os
import re
import smtplib
import sys
import time
from email.message import EmailMessage
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(HERE, "sources.json")
STATE_FILE = os.path.join(HERE, "state.json")

USER_AGENT = "ScholarshipWatch/1.0 (personal scholarship alerts for students in Ghana)"
KEYWORDS = re.compile(
    r"scholar|bursar|grant|fellowship|award|funding|funded|call for|apply|application|admission|opportunit",
    re.I,
)
SKIP_HREF = re.compile(r"^(mailto:|tel:|javascript:|#)|\.(jpg|jpeg|png|gif|svg|css|js)(\?|$)", re.I)
DEADLINE = re.compile(
    r"(?:deadline|closing date|closes?(?: on)?|apply (?:by|before))[^.\n]{0,60}?"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
    re.I,
)
MAX_DEADLINE_LOOKUPS = 12
PAUSE_SECONDS = 2  # be polite to the websites


def fetch(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    resp.raise_for_status()
    return resp.text


def extract_links(html, base_url):
    """Return {absolute_url: link_text} for links that look like scholarship posts."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if SKIP_HREF.search(href):
            continue
        text = " ".join(a.get_text(" ", strip=True).split())
        if len(text) < 15:
            continue
        url = urljoin(base_url, href).split("#")[0]
        if urlparse(url).scheme not in ("http", "https"):
            continue
        if not (KEYWORDS.search(text) or KEYWORDS.search(url)):
            continue
        found.setdefault(url, text[:200])
    return found


def link_id(url, text):
    return hashlib.sha1(f"{url}|{text}".encode("utf-8")).hexdigest()[:16]


def find_deadline(url):
    """Best-effort guess at a deadline on a post's own page. Always shown as unverified."""
    try:
        page = BeautifulSoup(fetch(url), "html.parser").get_text(" ", strip=True)
    except Exception:
        return None
    m = DEADLINE.search(page)
    return m.group(1) if m else None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True, ensure_ascii=False)


def build_digest(new_items, failures):
    lines, html = [], ["<div style='font-family:Arial,sans-serif;max-width:640px'>"]
    html.append(f"<h2 style='margin:0 0 12px'>{len(new_items)} new scholarship post(s)</h2>")
    for item in new_items:
        dl = f"Possible deadline: {item['deadline']} (check the page)" if item.get("deadline") else "Deadline: not found, open the page"
        lines += [f"[{item['scope']}] {item['source']}", item["text"], item["url"], dl, ""]
        html.append(
            "<div style='padding:12px 0;border-top:1px solid #ddd'>"
            f"<div style='font-size:12px;color:#555'>{item['scope']} · {item['source']}</div>"
            f"<div style='font-size:16px;margin:4px 0'><a href='{item['url']}'>{item['text']}</a></div>"
            f"<div style='font-size:13px;color:#555'>{dl}</div></div>"
        )
    if failures:
        lines.append("Sources that could not be checked today: " + ", ".join(failures))
        html.append(f"<p style='font-size:13px;color:#a33'>Could not check today: {', '.join(failures)}</p>")
    html.append("<p style='font-size:12px;color:#777'>Deadlines marked possible are guessed from the page text. Always confirm on the official page before forwarding to students.</p></div>")
    return "\n".join(lines), "".join(html)


def send_email(subject, text, html):
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to = os.environ.get("MAIL_TO") or user
    if not (user and password and to):
        print("Email settings missing (SMTP_USER, SMTP_PASS, MAIL_TO). Printing instead.\n")
        print(subject + "\n\n" + text)
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))) as s:
        s.login(user, password)
        s.send_message(msg)
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    with open(SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)
    state = load_state()
    new_items, failures = [], []

    for src in sources:
        name, url = src["name"], src["url"]
        try:
            links = extract_links(fetch(url), url)
        except Exception as exc:
            print(f"FAILED {name}: {exc}")
            failures.append(name)
            continue
        seen = set(state.get(url, []))
        ids = {link_id(u, t): (u, t) for u, t in links.items()}
        first_run = url not in state
        if not first_run:
            for lid, (u, t) in ids.items():
                if lid not in seen:
                    new_items.append({"source": name, "scope": src.get("scope", ""), "url": u, "text": t})
        # keep what we saw before so a page that loses a link does not re-alert later
        state[url] = sorted(seen | set(ids))
        print(f"{name}: {len(ids)} links" + (" (first run, saved as baseline)" if first_run else ""))
        time.sleep(PAUSE_SECONDS)

    for item in new_items[:MAX_DEADLINE_LOOKUPS]:
        item["deadline"] = find_deadline(item["url"])
        time.sleep(PAUSE_SECONDS)

    # keep a record of new posts for the dashboard (stored inside state.json)
    now = datetime.datetime.now(datetime.timezone.utc)
    posts = state.get("_posts", [])
    known = {p["url"] for p in posts}
    for item in new_items:
        if item["url"] in known:
            continue
        known.add(item["url"])
        posts.insert(0, {
            "source": item["source"], "scope": item["scope"], "title": item["text"],
            "url": item["url"], "found": now.strftime("%Y-%m-%d"), "deadline": item.get("deadline"),
        })
    state["_posts"] = posts[:200]
    if len(failures) < len(sources):
        state["_updated"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    if new_items:
        text, html = build_digest(new_items, failures)
        subject = f"Scholarship Watch: {len(new_items)} new post(s)"
        if dry_run:
            print("\n" + subject + "\n\n" + text)
        else:
            send_email(subject, text, html)
    else:
        print("Nothing new.")

    if not dry_run:
        save_state(state)
    if failures and len(failures) == len(sources):
        sys.exit(1)


if __name__ == "__main__":
    main()
