"""뉴스 수집 모듈 - 네이버/구글 뉴스 헤드라인을 가져오고 재료 키워드를 찾습니다."""
import urllib.parse
import xml.etree.ElementTree as ET

import config
import random
import re
import time

import requests
from bs4 import BeautifulSoup


def fetch_html(url, params=None):
    """User-Agent를 붙이고 잠깐 쉬었다가 HTML을 받아 파싱한다."""
    time.sleep(random.uniform(config.SLEEP_MIN, config.SLEEP_MAX))
    res = requests.get(url, params=params, headers=config.HEADERS, timeout=config.TIMEOUT)
    res.raise_for_status()
    return BeautifulSoup(res.text, "html.parser")


def naver_news(keyword):
    """네이버 뉴스 검색 결과에서 (제목, 요약, 링크) 목록."""
    soup = fetch_html("https://search.naver.com/search.naver", {"where": "news", "query": keyword, "sort": 1})
    items = []
    for a in soup.select("a[href][class*='news_tit'], a[data-heatmap-target='.tit']")[: config.NEWS_PER_SOURCE]:
        box = a.find_parent("div", class_=re.compile("news_area|sds-comps-base-layout"))
        desc = box.select_one("[class*='dsc'], [class*='desc']") if box else None
        items.append({"source": "네이버", "title": a.get_text(strip=True),
                      "summary": desc.get_text(strip=True) if desc else "", "link": a["href"]})
    return items


def google_news(keyword):
    """구글 뉴스 RSS에서 (제목, 요약, 링크) 목록."""
    time.sleep(random.uniform(config.SLEEP_MIN, config.SLEEP_MAX))
    url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(keyword + " 주식") + "&hl=ko&gl=KR&ceid=KR:ko"
    res = requests.get(url, headers=config.HEADERS, timeout=config.TIMEOUT)
    root = ET.fromstring(res.content)
    items = []
    for it in root.iter("item"):
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description", ""))
        items.append({"source": "구글", "title": it.findtext("title", ""),
                      "summary": re.sub(r"\s+", " ", desc).strip(), "link": it.findtext("link", "")})
        if len(items) >= config.NEWS_PER_SOURCE:
            break
    return items


def match_keywords(articles, own_name=""):
    """기사 제목·요약에 재료 키워드가 있는지 검사. 겹치는 키워드('삼성'⊂'삼성전자')는 긴 것만 남긴다."""
    text = " ".join(a["title"] + " " + a["summary"] for a in articles)
    text = text.replace(own_name, "") if own_name else text  # 종목 자신의 이름은 재료로 치지 않는다
    hits = [k for k in config.THEME_KEYWORDS if k in text]
    return [k for k in hits if not any(k != o and k in o for o in hits)]


def analyze_news(name, log):
    """한 종목의 뉴스를 모아 {articles, keywords} 로 돌려준다. 한 곳이 실패해도 계속 진행."""
    articles = []
    for func in (naver_news, google_news):
        try:
            articles += func(name)
        except Exception as e:
            log(f"  {name} {func.__name__} 실패: {e}")
    return {"articles": articles, "keywords": match_keywords(articles, name)}
