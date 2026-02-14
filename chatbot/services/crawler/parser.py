"""
Mahlatini Website Parser
========================
Parses HTTrack-mirrored HTML files into structured content documents
with metadata enrichment for the RAG knowledge base.
"""

import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

# ─── Content category mapping ───────────────────────────────
CATEGORY_PATTERNS = {
    "itinerary": [r"itineraries[\w]*\.html"],
    "destination": [
        r"^(botswana|egypt|kenya|malawi|morocco|mozambique|namibia|"
        r"republic-of-congo|rwanda|south-africa|tanzania|uganda|zambia|"
        r"zimbabwe|madagascar|maldives|mauritius|seychelles|bhutan|india|"
        r"nepal|sri-lanka|oman|united-arab-emirates)\.html$"
    ],
    "lodge": [
        r"^(botswana|kenya|south-africa|tanzania|namibia|zimbabwe|zambia|"
        r"mozambique|rwanda|uganda|mauritius|seychelles|maldives|madagascar|"
        r"malawi|india|sri-lanka|nepal|bhutan|egypt|morocco|republic-of-congo)/"
    ],
    "experience": [
        r"^(safaris|safari-and-beach|honeymoons|family-holidays|"
        r"couples-friends|adventure-seekers|solo-travellers|"
        r"gorilla-trekking|luxury-rail|natural-wonders|culture|"
        r"islands|great-migration)\.html$",
        r"^safaris/",
    ],
    "blog": [r"^blog/", r"^blog\.html$"],
    "review": [r"^reviews/", r"^reviews\.html$"],
    "travel_guide": [r"travel-guide", r"when-to-travel", r"packing", r"first-time-safari"],
    "company": [
        r"^(about-mahlatini|who-is-mahlatini|meet-the-team|how-to-book|"
        r"financial-protection|conservation-charity|international-awards|"
        r"press-media|contact|connect-with-us)\.html$"
    ],
    "policy": [r"^privacy-policy\.html$"],
    "special_offer": [r"^special-offers\.html$"],
}

DESTINATION_NAMES = {
    "botswana": "Botswana", "egypt": "Egypt", "kenya": "Kenya",
    "malawi": "Malawi", "morocco": "Morocco", "mozambique": "Mozambique",
    "namibia": "Namibia", "republic-of-congo": "Republic of Congo",
    "rwanda": "Rwanda", "south-africa": "South Africa", "tanzania": "Tanzania",
    "uganda": "Uganda", "zambia": "Zambia", "zimbabwe": "Zimbabwe",
    "madagascar": "Madagascar", "maldives": "Maldives",
    "mauritius": "Mauritius", "seychelles": "Seychelles",
    "bhutan": "Bhutan", "india": "India", "nepal": "Nepal",
    "sri-lanka": "Sri Lanka", "oman": "Oman",
    "united-arab-emirates": "United Arab Emirates",
}

REGION_MAP = {
    "botswana": "Africa", "egypt": "Africa", "kenya": "Africa",
    "malawi": "Africa", "morocco": "Africa", "mozambique": "Africa",
    "namibia": "Africa", "republic-of-congo": "Africa",
    "rwanda": "Africa", "south-africa": "Africa", "tanzania": "Africa",
    "uganda": "Africa", "zambia": "Africa", "zimbabwe": "Africa",
    "madagascar": "Indian Ocean", "maldives": "Indian Ocean",
    "mauritius": "Indian Ocean", "seychelles": "Indian Ocean",
    "bhutan": "Indian Subcontinent", "india": "Indian Subcontinent",
    "nepal": "Indian Subcontinent", "sri-lanka": "Indian Subcontinent",
    "oman": "Middle East", "united-arab-emirates": "Middle East",
}

# Elements to strip from HTML before extracting content
STRIP_ELEMENTS = [
    "nav", "header", "footer", "script", "style", "noscript",
    "iframe", "form", "button", "svg", "picture > source",
]

STRIP_CLASSES = [
    "site-header", "site-footer", "header-top-bar", "header-main",
    "main-nav", "sub-nav", "mobile-menu", "cookie-banner",
    "farewell-modal", "search-modal", "lang-curr-chooser",
    "breadcrumb", "back-to-top",
]


@dataclass
class ParsedDocument:
    """A parsed and enriched document from the Mahlatini website."""
    source_url: str
    page_title: str
    category: str
    destination_country: Optional[str]
    destination_region: Optional[str]
    content: str
    content_sections: list = field(default_factory=list)
    meta_description: Optional[str] = None
    content_hash: Optional[str] = None

    def is_valid(self) -> bool:
        """Check if document has enough content to be useful."""
        return len(self.content.strip()) > 100


def classify_page(relative_path: str) -> str:
    """Determine the content category from the file path."""
    clean_path = relative_path.lstrip("/")
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.match(pattern, clean_path):
                return category
    return "other"


def extract_destination(relative_path: str) -> tuple[Optional[str], Optional[str]]:
    """Extract destination country and region from the file path."""
    clean_path = relative_path.lstrip("/")
    parts = clean_path.replace(".html", "").split("/")

    if parts:
        country_slug = parts[0]
        if country_slug in DESTINATION_NAMES:
            country = DESTINATION_NAMES[country_slug]
            region = REGION_MAP.get(country_slug)
            return country, region

    return None, None


def extract_content(html: str) -> tuple[str, str, Optional[str], list]:
    """
    Extract clean text content from HTML, removing navigation,
    headers, footers, and other non-content elements.

    Returns: (title, clean_text, meta_description, sections)
    """
    soup = BeautifulSoup(html, "lxml")

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    # Clean common suffixes
    title = re.sub(r"\s*\|\s*Mahlatini.*$", "", title)
    title = re.sub(r"\s*-\s*Mahlatini.*$", "", title)

    # Extract meta description
    meta_desc = None
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "").strip()

    # Remove unwanted elements
    for selector in STRIP_ELEMENTS:
        for el in soup.select(selector):
            el.decompose()

    for class_name in STRIP_CLASSES:
        for el in soup.find_all(class_=re.compile(class_name)):
            el.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove HTTrack comments
    for comment in soup.find_all(string=lambda t: isinstance(t, str) and "HTTrack" in t):
        comment.extract()

    # Extract sections based on headings
    sections = []
    body = soup.find("body") or soup

    current_heading = "Introduction"
    current_content = []

    for element in body.descendants:
        if element.name in ("h1", "h2", "h3"):
            # Save previous section
            text = " ".join(current_content).strip()
            if text and len(text) > 50:
                sections.append({
                    "heading": current_heading,
                    "content": text,
                })
            current_heading = element.get_text(strip=True)
            current_content = []
        elif element.name in ("p", "li", "td", "span", "div", "blockquote"):
            text = element.get_text(strip=True)
            if text and len(text) > 10 and element.parent.name not in ("h1", "h2", "h3"):
                # Avoid duplicate content from nested elements
                if not any(child.name in ("p", "li", "div", "blockquote") for child in element.children if hasattr(child, "name")):
                    current_content.append(text)

    # Don't forget the last section
    text = " ".join(current_content).strip()
    if text and len(text) > 50:
        sections.append({
            "heading": current_heading,
            "content": text,
        })

    # Full clean text
    full_text = "\n\n".join(
        f"{s['heading']}\n{s['content']}" for s in sections
    )

    # Collapse whitespace
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)
    full_text = re.sub(r" {2,}", " ", full_text)

    return title, full_text.strip(), meta_desc, sections


def parse_file(filepath: str, base_dir: str) -> Optional[ParsedDocument]:
    """
    Parse a single HTML file into a structured document.

    Args:
        filepath: Absolute path to the HTML file
        base_dir: Base directory of the website mirror (e.g., /data/website)
    """
    try:
        relative_path = os.path.relpath(filepath, base_dir)

        # Skip non-content files
        if any(skip in relative_path for skip in [
            "cdn-cgi", "cpresources", "build/", "228h/",
            "my-account", "wishlist", "enquiry/",
        ]):
            return None

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()

        title, content, meta_desc, sections = extract_content(html)
        category = classify_page(relative_path)
        country, region = extract_destination(relative_path)

        doc = ParsedDocument(
            source_url=f"/{relative_path}",
            page_title=title,
            category=category,
            destination_country=country,
            destination_region=region,
            content=content,
            content_sections=sections,
            meta_description=meta_desc,
        )

        if not doc.is_valid():
            logger.debug(f"Skipping {relative_path} - insufficient content")
            return None

        return doc

    except Exception as e:
        logger.warning(f"Failed to parse {filepath}: {e}")
        return None


def parse_website(base_dir: str) -> list[ParsedDocument]:
    """
    Parse all HTML files in the website mirror directory.

    Args:
        base_dir: Path to the HTTrack mirror (e.g., /data/website)

    Returns:
        List of parsed documents
    """
    documents = []
    html_files = list(Path(base_dir).rglob("*.html"))
    total = len(html_files)

    logger.info(f"Found {total} HTML files in {base_dir}")

    for i, filepath in enumerate(html_files):
        doc = parse_file(str(filepath), base_dir)
        if doc:
            documents.append(doc)

        if (i + 1) % 100 == 0:
            logger.info(f"Parsed {i + 1}/{total} files ({len(documents)} valid)")

    logger.info(f"Parsing complete: {len(documents)} valid documents from {total} files")
    return documents
