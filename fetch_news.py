import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

TWO_WEEKS = timedelta(days=14)
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
CUTOFF = NOW - TWO_WEEKS

SOURCES = [
    {
        "name": "Reuters",
        "badge": "b-r",
        "urls": [
            "https://feeds.reuters.com/reuters/worldNews",
            "https://www.reutersagency.com/feed/?best-topics=africa&post_type=best",
        ],
    },
    {
        "name": "NYT",
        "badge": "b-nyt",
        "urls": [
            "https://rss.nytimes.com/services/xml/rss/nyt/Africa.xml",
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        ],
    },
    {
        "name": "BBC",
        "badge": "b-bbc",
        "urls": ["https://feeds.bbci.co.uk/news/world/africa/rss.xml"],
    },
    {
        "name": "CNN",
        "badge": "b-cnn",
        "urls": ["http://rss.cnn.com/rss/edition_africa.rss"],
    },
    {
        "name": "Africanews",
        "badge": "b-an",
        "urls": ["https://www.africanews.com/feed/rss"],
    },
    {
        "name": "Al Jazeera",
        "badge": "b-aj",
        "urls": ["https://www.aljazeera.com/xml/rss/all.xml"],
    },
    {
        "name": "AllAfrica",
        "badge": "b-aa",
        "urls": ["https://allafrica.com/tools/headlines/rdf/africa/headlines.rdf"],
    },
    {
        "name": "Rwanda",
        "badge": "b-rw",
        "urls": [
            "https://news.google.com/rss/search?q=Rwanda&hl=en-US&gl=US&ceid=US:en",
            "https://www.newtimes.co.rw/feed",
        ],
        "country_override": "Rwanda",
    },
]

COUNTRY_MAP = {
    "South Africa": r"south africa|cape town|johannesburg|pretoria|soweto",
    "Nigeria": r"nigeria|lagos|abuja",
    "Kenya": r"kenya|nairobi|mombasa",
    "Egypt": r"egypt|cairo|suez",
    "Ethiopia": r"ethiopia|addis ababa|addis",
    "Somalia": r"somalia|mogadishu",
    "DRC": r"\b(drc|congo)\b|kinshasa|virunga",
    "Sudan": r"\bsudan\b|khartoum|darfur|el.fasher",
    "Morocco": r"morocco|rabat|casablanca",
    "Ghana": r"ghana|accra",
    "Uganda": r"uganda|kampala",
    "Tanzania": r"tanzania|dar es salaam",
    "Angola": r"angola|luanda",
    "Namibia": r"namibia|windhoek",
    "Rwanda": r"rwanda|kigali",
    "Cameroon": r"cameroon",
    "Mali": r"\bmali\b|bamako",
    "Senegal": r"senegal|dakar",
    "Algeria": r"algeria|algiers",
    "South Sudan": r"south sudan|juba",
    "Mozambique": r"mozambique|maputo",
    "Zimbabwe": r"zimbabwe|harare",
    "Mauritius": r"mauritius",
    "Zambia": r"zambia|lusaka",
    "Burkina Faso": r"burkina faso|ouagadougou",
    "Niger": r"\bniger\b(?!ia)",
}

AFRICA_RE = re.compile(
    r"africa|nigeria|kenya|ghana|ethiopia|egypt|morocco|sudan|congo|angola|"
    r"south africa|somalia|tanzania|uganda|mozambique|senegal|cameroon|"
    r"zimbabwe|zambia|rwanda|sahel|mali|niger|burkina|sahara|nairobi|cairo|"
    r"lagos|addis|kinshasa|algeria|namibia|mauritius|juba",
    re.IGNORECASE,
)

TOPIC_RULES = [
    ("Iran & Africa", r"iran|hormuz|fuel price|oil surge|energy crisis|suez.*iran|iran.*africa|fertiliser.*iran"),
    ("Politics", r"election|president|minister|parliament|govern|coup|diplomat|sanction|vote|leader"),
    ("Economy", r"economy|gdp|trade|invest|market|bond|bank|fund|finance|eurobond|export|entrepreneur|refinery"),
    ("Environment", r"climate|environment|wildlife|forest|drought|flood|gorilla|nature|conservation|landslide|green"),
    ("Conflict", r"war|conflict|attack|military|troops|rebel|violence|terror|bomb|killed|boko|iswap|al.shabaab|rsf|jnim|airstrike"),
    ("Sport", r"sport|football|soccer|rally|olympic|champion|match|league|afcon|cup|wrc"),
    ("Technology", r"tech|starlink|satellite|\bai\b|digital|internet|cyber|startup"),
    ("Humanitarian", r"food|hunger|famine|aid|relief|refugee|humanitarian|displaced"),
]

STOP_WORDS = {
    "africa", "african", "the", "and", "for", "with", "from", "that",
    "this", "into", "after", "over", "amid", "says", "said", "have",
    "been", "its", "was", "are", "has", "new", "will", "than", "more",
}


def guess_country(text):
    t = text.lower()
    for country, pattern in COUNTRY_MAP.items():
        if re.search(pattern, t):
            return country
    return "Regional"


def guess_topic(text):
    t = text.lower()
    for topic, pattern in TOPIC_RULES:
        if re.search(pattern, t):
            return topic
    return "Society"


def guess_keywords(title):
    words = re.sub(r"[^a-z\s]", " ", title.lower()).split()
    return [w for w in words if len(w) > 3 and w not in STOP_WORDS][:3]


def is_africa(text):
    return bool(AFRICA_RE.search(text))


def parse_date(date_str):
    if not date_str:
        return NOW
    fmts = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(KST)
        except ValueError:
            continue
    return NOW


def fetch_feed(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AfricaNewsBrief/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()
    except Exception as e:
        print(f"  Failed {url}: {e}")
        return None


def parse_feed(content):
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = root.findall(".//item") or root.findall(".//atom:entry", ns)

    articles = []
    for item in items:
        def get(tag, alt=None):
            el = item.find(tag)
            if el is None and alt:
                el = item.find(alt)
            return (el.text or "").strip() if el is not None else ""

        title = get("title")
        desc = re.sub(r"<[^>]+>", "", get("description") or get("summary", "summary"))
        desc = desc.strip()[:160]
        link = get("link") or get("guid")
        pub = get("pubDate") or get("published") or get("updated")
        articles.append((title, desc, link, pub))

    return articles


def fetch_source(source):
    articles = []
    for url in source["urls"]:
        print(f"  Trying {url}")
        content = fetch_feed(url)
        if not content:
            continue

        items = parse_feed(content)
        if not items:
            continue

        for title, desc, link, pub in items:
            combined = title + " " + desc
            if not title:
                continue
            # Skip Africa filter if source has a country override (e.g. Rwanda)
            if not source.get("country_override") and not is_africa(combined):
                continue

            pub_dt = parse_date(pub)
            if pub_dt < CUTOFF:
                continue

            articles.append({
                "title": title,
                "desc": desc + ("…" if len(desc) >= 160 else ""),
                "url": link or url,
                "time": pub_dt.isoformat(),
                "timeAgo": time_ago(pub_dt),
                "topic": guess_topic(combined),
                "country": guess_country(combined),
                "keywords": guess_keywords(title),
                "src": source["name"],
                "badge": source["badge"],
            })

        if articles:
            print(f"  Got {len(articles)} articles")
            break

    return articles[:20]


def time_ago(dt):
    diff = NOW - dt
    secs = int(diff.total_seconds())
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    if secs < 604800:
        return f"{secs // 86400}d ago"
    return dt.strftime("%-d %b")


def main():
    all_articles = []

    for source in SOURCES:
        print(f"\nFetching {source['name']}...")
        arts = fetch_source(source)
        all_articles.extend(arts)
        print(f"  Total from {source['name']}: {len(arts)}")

    # Sort by time descending
    all_articles.sort(key=lambda a: a["time"], reverse=True)

    output = {
        "updated": NOW.strftime("%-d %b %Y %H:%M KST"),
        "count": len(all_articles),
        "articles": all_articles,
    }

    with open("articles.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(all_articles)} articles saved to articles.json")


if __name__ == "__main__":
    main()
