"""Settings of the Hirpult World edition: sources, sections and languages."""
import os

# (outlet, feed url, allowed link hosts, section)
BBC = "http://feeds.bbci.co.uk/news/"
GUARDIAN = "https://www.theguardian.com/"
SOURCES = [
    ("BBC News", BBC + "world/rss.xml", ("bbc.co.uk", "bbc.com"), "World"),
    ("BBC News", BBC + "world/europe/rss.xml", ("bbc.co.uk", "bbc.com"), "Europe"),
    ("BBC News", BBC + "world/us_and_canada/rss.xml", ("bbc.co.uk", "bbc.com"), "Americas"),
    ("BBC News", BBC + "world/latin_america/rss.xml", ("bbc.co.uk", "bbc.com"), "Americas"),
    ("BBC News", BBC + "world/middle_east/rss.xml", ("bbc.co.uk", "bbc.com"), "Middle East"),
    ("BBC News", BBC + "world/asia/rss.xml", ("bbc.co.uk", "bbc.com"), "Asia-Pacific"),
    ("BBC News", BBC + "world/africa/rss.xml", ("bbc.co.uk", "bbc.com"), "Africa"),
    ("BBC News", BBC + "business/rss.xml", ("bbc.co.uk", "bbc.com"), "Business"),
    ("BBC News", BBC + "technology/rss.xml", ("bbc.co.uk", "bbc.com"), "Technology"),
    ("BBC News", BBC + "science_and_environment/rss.xml", ("bbc.co.uk", "bbc.com"), "Science"),
    ("BBC News", BBC + "health/rss.xml", ("bbc.co.uk", "bbc.com"), "Health"),
    ("BBC News", BBC + "entertainment_and_arts/rss.xml", ("bbc.co.uk", "bbc.com"), "Culture"),
    ("The Guardian", GUARDIAN + "world/rss", ("theguardian.com",), "World"),
    ("The Guardian", GUARDIAN + "world/europe-news/rss", ("theguardian.com",), "Europe"),
    ("The Guardian", GUARDIAN + "us-news/rss", ("theguardian.com",), "Americas"),
    ("The Guardian", GUARDIAN + "world/middleeast/rss", ("theguardian.com",), "Middle East"),
    ("The Guardian", GUARDIAN + "world/asia-pacific/rss", ("theguardian.com",), "Asia-Pacific"),
    ("The Guardian", GUARDIAN + "world/africa/rss", ("theguardian.com",), "Africa"),
    ("The Guardian", GUARDIAN + "business/rss", ("theguardian.com",), "Business"),
    ("The Guardian", GUARDIAN + "technology/rss", ("theguardian.com",), "Technology"),
    ("The Guardian", GUARDIAN + "science/rss", ("theguardian.com",), "Science"),
    ("The Guardian", GUARDIAN + "environment/climate-crisis/rss", ("theguardian.com",), "Climate"),
    ("The Guardian", GUARDIAN + "sport/rss", ("theguardian.com",), "Sport"),
    ("The Guardian", GUARDIAN + "culture/rss", ("theguardian.com",), "Culture"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", ("aljazeera.com",), "World"),
    ("DW", "https://rss.dw.com/rdf/rss-en-all", ("dw.com",), "World"),
    ("France 24", "https://www.france24.com/en/rss", ("france24.com",), "World"),
    ("NPR", "https://feeds.npr.org/1001/rss.xml", ("npr.org",), "World"),
    ("Euronews", "https://www.euronews.com/rss", ("euronews.com",), "Europe"),
]

# Languages with finished translations. More are added here as the edition grows.
LANGS = [x.strip() for x in (os.getenv("WORLD_LANGS") or "hu,de,es,fr,pt,pl").split(",") if x.strip()]
HOURS = 48          # a headline stays in the queue this long
QUEUE_LIMIT = 300
KEEP_DAYS = 2       # how long finished articles stay on the page
