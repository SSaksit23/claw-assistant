"""
Itinerary Analyzer Service.

Adapted from the itin-analyzer prototype. Provides:
- PDF text extraction using PyMuPDF (fitz)
- Structured itinerary data extraction via LLM
- Multi-itinerary comparison and competitive analysis
- Market intelligence pipeline (themes, web research, reports)
- Thai/English bilingual support with auto-detection

This service equips the Data Analysis Agent and Market Analysis Agent
with itinerary-level intelligence on top of the existing expense/booking
data extraction.
"""

import io
import os
import re
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import Counter

from openai import OpenAI

from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

ITINERARY_SCHEMA = {
    "tourName": "string - name of the tour",
    "duration": "string - e.g. '8 Days / 7 Nights'",
    "destinations": ["array of destination cities/countries"],
    "pricing": [{"period": "string", "price": "number", "currency": "string"}],
    "flights": [
        {
            "flightNumber": "string",
            "origin": "string",
            "destination": "string",
            "departureTime": "string",
            "arrivalTime": "string",
            "flightTime": "string",
        }
    ],
    "inclusions": ["array of included items"],
    "exclusions": ["array of excluded items"],
    "dailyBreakdown": [
        {
            "day": "number",
            "title": "string",
            "activities": "string",
            "meals": ["array"],
            "locations": ["array"],
        }
    ],
}


# ---------------------------------------------------------------------------
# PDF Extraction (ported from prototype backend/main.py using PyMuPDF)
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> dict:
    """
    Extract text from a PDF file using PyMuPDF with optimised settings
    for travel itineraries (prices, dates, Thai text).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF (fitz) not installed. Install with: pip install PyMuPDF")
        return {"success": False, "error": "PyMuPDF not installed", "text": ""}

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        extracted_pages = []
        full_text = ""

        total_chars = 0
        has_tables = False
        has_thai = False
        has_prices = False

        for page_num in range(total_pages):
            page = doc[page_num]

            # Method 1: Standard text extraction with reading-order sort
            text = page.get_text("text", sort=True)

            # Method 2: Blocks mode for sparse pages
            if len(text.strip()) < 50:
                blocks = page.get_text("blocks", sort=True)
                text = "\n".join(
                    [block[4] for block in blocks if block[6] == 0]
                )

            # Method 3: Dict mode for complex layouts (tables)
            if len(text.strip()) < 50:
                text_dict = page.get_text("dict", sort=True)
                lines = []
                for block in text_dict.get("blocks", []):
                    if block.get("type") == 0:
                        for line in block.get("lines", []):
                            line_text = " ".join(
                                span.get("text", "")
                                for span in line.get("spans", [])
                            )
                            if line_text.strip():
                                lines.append(line_text)
                if lines:
                    text = "\n".join(lines)

            text = _clean_text(text)

            # Detect content types
            if re.search(r"[\u0E00-\u0E7F]", text):
                has_thai = True
            if re.search(
                r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*(?:บาท|THB|฿|USD|\$|EUR)",
                text,
                re.IGNORECASE,
            ):
                has_prices = True
            if "|" in text or re.search(r"\t{2,}", text):
                has_tables = True

            total_chars += len(text)
            extracted_pages.append(
                {"page": page_num + 1, "text": text, "char_count": len(text)}
            )
            full_text += f"\n--- Page {page_num + 1} ---\n{text}\n"

        doc.close()

        avg_chars_per_page = total_chars / total_pages if total_pages > 0 else 0
        quality_score = (
            "high"
            if avg_chars_per_page > 500
            else "medium"
            if avg_chars_per_page > 100
            else "low"
        )

        return {
            "success": True,
            "text": full_text.strip(),
            "total_pages": total_pages,
            "total_chars": total_chars,
            "avg_chars_per_page": round(avg_chars_per_page, 1),
            "quality_score": quality_score,
            "content_types": {
                "has_thai": has_thai,
                "has_prices": has_prices,
                "has_tables": has_tables,
            },
            "pages": extracted_pages,
        }

    except Exception as e:
        logger.error(f"PDF extraction failed: {e}", exc_info=True)
        return {"success": False, "error": str(e), "text": ""}


def extract_tables_from_pdf(pdf_path: str) -> dict:
    """
    Extract tables from a PDF using PyMuPDF's table detection.
    Useful for itinerary schedules and pricing tables.
    """
    try:
        import fitz
    except ImportError:
        return {"success": False, "error": "PyMuPDF not installed", "tables": []}

    try:
        doc = fitz.open(pdf_path)
        all_tables = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            tables = page.find_tables()

            for table_idx, table in enumerate(tables):
                table_data = table.extract()
                if table_data and len(table_data) > 1:
                    all_tables.append(
                        {
                            "page": page_num + 1,
                            "table_index": table_idx,
                            "rows": len(table_data),
                            "cols": len(table_data[0]) if table_data else 0,
                            "data": table_data,
                        }
                    )

        doc.close()
        return {"success": True, "table_count": len(all_tables), "tables": all_tables}

    except Exception as e:
        return {"success": False, "error": str(e), "tables": []}


# ---------------------------------------------------------------------------
# Text Cleaning
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Clean and normalise extracted text, preserving important data."""
    if not text:
        return ""

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.replace("\ufeff", "").replace("\x00", "")

    # Thai text spacing helpers
    text = re.sub(r"([\u0E00-\u0E7F])(\d)", r"\1 \2", text)
    text = re.sub(r"(\d)([\u0E00-\u0E7F])", r"\1 \2", text)

    # Fix broken thousands separators
    text = re.sub(r"(\d)\s*,\s*(\d{3})", r"\1,\2", text)

    return text.strip()


def _detect_language(text: str) -> str:
    """Detect if text is primarily Thai or English."""
    thai_chars = len(re.findall(r"[\u0E00-\u0E7F]", text))
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    if thai_chars > latin_chars:
        return "Thai"
    return "English"


# ---------------------------------------------------------------------------
# Structured Itinerary Extraction (LLM-based)
# ---------------------------------------------------------------------------

def analyze_itinerary(text: str, language: str = "auto") -> dict:
    """
    Analyse an itinerary document and extract structured data.

    Ported from prototype's aiService.ts / analyzeItinerary().

    Returns a dict matching ITINERARY_SCHEMA.
    """
    if language == "auto":
        language = _detect_language(text)

    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    system_prompt = (
        "You are a travel itinerary analyzer. Extract information from the "
        "provided itinerary and return it as a JSON object with this exact structure:\n"
        "{\n"
        '  "tourName": "string - name of the tour",\n'
        '  "duration": "string - e.g. \'8 Days / 7 Nights\'",\n'
        '  "destinations": ["array of destination cities/countries"],\n'
        '  "pricing": [{"period": "string", "price": number, "currency": "string"}],\n'
        '  "flights": [{"flightNumber": "string", "origin": "string", '
        '"destination": "string", "departureTime": "string", '
        '"arrivalTime": "string", "flightTime": "string"}],\n'
        '  "inclusions": ["array of included items"],\n'
        '  "exclusions": ["array of excluded items"],\n'
        '  "dailyBreakdown": [{"day": number, "title": "string", '
        '"activities": "string", "meals": ["array"], "locations": ["array"]}]\n'
        "}\n"
        f"Respond ONLY with valid JSON. The response should be in {language}."
    )

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL_ANALYSIS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this itinerary:\n\n{text[:8000]}"},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        logger.info(
            f"Itinerary analyzed: {result.get('tourName', 'Unknown')} "
            f"({result.get('duration', 'N/A')})"
        )
        return {"status": "success", "data": result, "language": language}

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM JSON: {e}")
        return {"status": "error", "error": f"Invalid JSON from AI: {e}", "data": None}
    except Exception as e:
        logger.error(f"Itinerary analysis failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e), "data": None}


# ---------------------------------------------------------------------------
# Multi-Itinerary Comparison
# ---------------------------------------------------------------------------

def compare_itineraries(
    itineraries: List[dict],
    language: str = "English",
) -> dict:
    """
    Compare multiple analysed itineraries side by side.

    Each item in `itineraries` should have:
    - name: str
    - analysis: dict (output from analyze_itinerary)
    - text: str (original text, optional)

    Ported from prototype's aiService.ts / getComparison().
    """
    if len(itineraries) < 2:
        return {"status": "error", "error": "Need at least 2 itineraries to compare"}

    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    competitor_details = "\n\n---\n\n".join(
        f"### {it['name']}\n"
        f"ANALYSIS:\n{json.dumps(it.get('analysis', {}), indent=2, ensure_ascii=False)}"
        for it in itineraries
    )

    names_header = " | ".join(it["name"] for it in itineraries)

    system_prompt = (
        "You are a senior travel industry analyst with expertise in competitive analysis.\n\n"
        "Your analysis should be:\n"
        "- Data-driven and specific (use numbers, percentages, days)\n"
        "- Comparative (highlight relative strengths/weaknesses)\n"
        "- Actionable (what can be improved based on comparison)\n"
        "- Market-aware (reference industry standards when available)\n\n"
        f"Respond in {language} using professional markdown format."
    )

    user_prompt = (
        f"Perform a comprehensive comparison of these travel products:\n\n"
        f"{competitor_details}\n\n"
        f"Create a detailed analysis with:\n\n"
        f"## 1. Product Comparison Matrix\n"
        f"| Aspect | {names_header} |\n"
        f"Include: Duration, Price/day, Destinations count, Included meals, "
        f"Activities, Flight quality, Accommodation level\n\n"
        f"## 2. Value Analysis\n"
        f"Compare price-to-value ratio for each product\n\n"
        f"## 3. Strengths & Weaknesses\n"
        f"For each product, list top 3 strengths and areas for improvement\n\n"
        f"## 4. Target Customer Profile\n"
        f"Who is the ideal customer for each product?\n\n"
        f"## 5. Competitive Insights\n"
        f"- Which product offers best value?\n"
        f"- Which has unique differentiators?\n"
        f"- Market positioning recommendations\n\n"
        f"### Conclusion\n"
        f"Summarize key findings and strategic recommendations."
    )

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL_ANALYSIS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )

        comparison_text = response.choices[0].message.content
        logger.info(
            f"Comparison generated for {len(itineraries)} itineraries "
            f"({len(comparison_text)} chars)"
        )
        return {"status": "success", "comparison": comparison_text}

    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Strategic Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(
    itineraries: List[dict],
    language: str = "English",
) -> dict:
    """
    Generate strategic recommendations based on analysed itineraries.

    Ported from prototype's aiService.ts / getRecommendations().
    """
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    analysis_summary = "\n\n".join(
        f"### {it['name']}\n{json.dumps(it.get('analysis', {}), indent=2, ensure_ascii=False)}"
        for it in itineraries
    )

    system_prompt = (
        "You are a strategic travel consultant with deep industry expertise. "
        "Provide comprehensive, actionable insights and recommendations "
        "based on itinerary analysis.\n\n"
        "When analyzing:\n"
        "1. Consider market positioning and competitive differentiation\n"
        "2. Identify pricing strategies and value propositions\n"
        "3. Analyze destination choices and route optimization\n"
        "4. Evaluate service inclusions vs. market standards\n"
        "5. Suggest specific improvements with business impact\n\n"
        f"Respond in {language} using markdown format with clear sections."
    )

    user_prompt = (
        f"Provide strategic deep-dive recommendations for these travel products:\n\n"
        f"## Current Analysis\n{analysis_summary}\n\n"
        f"Please analyze:\n"
        f"1. **Product Positioning** - How does each product fit in the market?\n"
        f"2. **Pricing Analysis** - Is pricing competitive? Value for money?\n"
        f"3. **Unique Selling Points** - What makes each product stand out?\n"
        f"4. **Areas for Improvement** - Specific, actionable recommendations\n"
        f"5. **Market Opportunities** - Untapped potential or gaps\n"
        f"6. **Competitive Threats** - What competitors are doing better?"
    )

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL_ANALYSIS,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )

        recs_text = response.choices[0].message.content
        logger.info(f"Recommendations generated ({len(recs_text)} chars)")
        return {"status": "success", "recommendations": recs_text}

    except Exception as e:
        logger.error(f"Recommendations failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Market Intelligence Pipeline
# ---------------------------------------------------------------------------

def run_market_intelligence(
    documents: List[dict],
    include_web_research: bool = True,
    fast_mode: bool = True,
    generate_report: bool = True,
) -> dict:
    """
    Run the full market intelligence pipeline.

    Ported from prototype backend's /agents/market-intelligence endpoint.

    Pipeline:
    1. EXTRACT  - Parse and clean document text
    2. ANALYSE  - Identify dominant destinations, themes, patterns
    3. WEB SEARCH - Find competitor products (if EXA_API_KEY configured)
    4. AGGREGATE  - Combine into knowledge structure
    5. REPORT     - Generate comprehensive report

    Args:
        documents: [{"name": "...", "text": "..."}, ...]
        include_web_research: Whether to search web for competitors
        fast_mode: Limit documents analysed for speed
        generate_report: Whether to generate final report

    Returns:
        Complete market intelligence analysis.
    """
    import time

    start_time = time.time()
    client = OpenAI(api_key=Config.OPENAI_API_KEY)

    pipeline_steps = {
        "extract": {"status": "pending"},
        "analyze_themes": {"status": "pending"},
        "web_research": {"status": "pending"},
        "aggregate": {"status": "pending"},
        "report": {"status": "pending"},
    }

    logger.info(
        f"Market Intelligence Pipeline started: {len(documents)} documents"
    )

    # ── Step 1: Extract & validate ──
    valid_documents = []
    total_chars = 0

    for doc in documents:
        text = doc.get("text", "")
        name = doc.get("name", "Unknown")
        if text and len(text.strip()) > 50:
            cleaned = _clean_text(text)
            valid_documents.append({"name": name, "text": cleaned, "char_count": len(cleaned)})
            total_chars += len(cleaned)

    pipeline_steps["extract"] = {
        "status": "completed",
        "details": {
            "input_documents": len(documents),
            "valid_documents": len(valid_documents),
            "total_characters": total_chars,
        },
    }

    if not valid_documents:
        return {
            "success": False,
            "error": "No valid documents to analyse",
            "pipeline_steps": pipeline_steps,
            "elapsed_seconds": time.time() - start_time,
        }

    # ── Step 2: Analyse themes & patterns ──
    dominant_themes = {
        "destinations": Counter(),
        "themes": Counter(),
        "duration_patterns": Counter(),
        "price_ranges": Counter(),
        "activities": Counter(),
    }

    all_extracted_data = []
    max_docs = 10 if fast_mode else 50
    docs_to_analyse = valid_documents[:max_docs]

    for doc in docs_to_analyse:
        text_limit = 2000 if fast_mode else 4000
        extraction_prompt = (
            f"Analyze this travel itinerary and extract JSON:\n"
            f"Document: {doc['name']}\n"
            f"Content: {doc['text'][:text_limit]}\n\n"
            f'Return JSON: {{"destinations": ["cities"], '
            f'"themes": ["beach/adventure/cultural/luxury/budget/family/honeymoon"], '
            f'"duration": "X days Y nights", '
            f'"price_range": "price or null", '
            f'"activities": ["key activities"], '
            f'"target_audience": "who"}}'
        )

        try:
            response = client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )

            extracted = json.loads(response.choices[0].message.content)
            extracted["document_name"] = doc["name"]
            all_extracted_data.append(extracted)

            for dest in extracted.get("destinations", []):
                dominant_themes["destinations"][dest.strip()] += 1
            for theme in extracted.get("themes", []):
                dominant_themes["themes"][theme.strip().lower()] += 1
            if extracted.get("duration"):
                dominant_themes["duration_patterns"][extracted["duration"]] += 1
            for activity in extracted.get("activities", []):
                dominant_themes["activities"][activity.strip()] += 1

        except Exception as e:
            logger.warning(f"Failed to analyse {doc['name']}: {e}")

    top_destinations = dominant_themes["destinations"].most_common(5)
    top_themes = dominant_themes["themes"].most_common(5)
    top_activities = dominant_themes["activities"].most_common(10)

    main_destination = top_destinations[0][0] if top_destinations else "Unknown"
    main_theme = top_themes[0][0] if top_themes else "general"

    pipeline_steps["analyze_themes"] = {
        "status": "completed",
        "details": {
            "documents_analyzed": len(all_extracted_data),
            "main_destination": main_destination,
            "main_theme": main_theme,
            "top_destinations": dict(top_destinations),
            "top_themes": dict(top_themes),
        },
    }

    # ── Step 3: Web research (optional) ──
    web_research_results = {
        "queries_executed": [],
        "packages_found": [],
        "prices_found": [],
    }

    exa_api_key = Config.EXA_API_KEY
    if include_web_research and exa_api_key:
        web_research_results = _run_web_research(
            main_destination, main_theme, top_destinations, exa_api_key
        )

    pipeline_steps["web_research"] = {
        "status": "completed" if web_research_results["packages_found"] else "skipped",
        "details": {
            "queries_executed": len(web_research_results["queries_executed"]),
            "packages_found": len(web_research_results["packages_found"]),
            "prices_found": len(web_research_results["prices_found"]),
        },
    }

    # ── Step 4: Aggregate knowledge ──
    knowledge_graph = _aggregate_knowledge(
        valid_documents,
        all_extracted_data,
        main_destination,
        top_themes,
        top_activities,
        web_research_results,
    )

    pipeline_steps["aggregate"] = {
        "status": "completed",
        "details": {
            "entities_created": len(knowledge_graph["entities"]),
            "relationships_created": len(knowledge_graph["relationships"]),
        },
    }

    # ── Step 5: Generate report ──
    final_report = ""
    if generate_report:
        final_report = _generate_market_report(
            client,
            valid_documents,
            main_destination,
            main_theme,
            top_destinations,
            top_themes,
            top_activities,
            web_research_results,
        )

    pipeline_steps["report"] = {
        "status": "completed" if final_report else "skipped",
        "details": {"report_length": len(final_report)},
    }

    elapsed = time.time() - start_time
    logger.info(f"Market Intelligence Pipeline completed in {elapsed:.1f}s")

    return {
        "success": True,
        "pipeline_steps": pipeline_steps,
        "dominant_themes": {
            "main_destination": main_destination,
            "main_theme": main_theme,
            "top_destinations": dict(top_destinations),
            "top_themes": dict(top_themes),
            "top_activities": dict(top_activities[:10]),
            "extracted_data": all_extracted_data,
        },
        "web_research": web_research_results,
        "knowledge_graph": knowledge_graph,
        "final_report": final_report,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Web Research (EXA API integration)
# ---------------------------------------------------------------------------

def _run_web_research(
    main_destination: str,
    main_theme: str,
    top_destinations: list,
    exa_api_key: str,
) -> dict:
    """Execute web research using EXA API for competitor intelligence."""
    results = {
        "queries_executed": [],
        "packages_found": [],
        "prices_found": [],
    }

    try:
        from exa_py import Exa

        exa = Exa(exa_api_key)

        search_queries = [
            f"{main_destination} {main_theme} tour package 2026",
            f"{main_destination} travel itinerary price comparison",
        ]
        if len(top_destinations) > 1:
            second_dest = top_destinations[1][0]
            search_queries.append(f"{main_destination} {second_dest} multi-city tour")

        for query in search_queries[:3]:
            try:
                search_result = exa.search_and_contents(
                    query, num_results=3, use_autoprompt=True
                )
                results["queries_executed"].append(query)

                for item in search_result.results:
                    package_info = {
                        "title": getattr(item, "title", ""),
                        "url": getattr(item, "url", ""),
                        "snippet": (getattr(item, "text", "") or "")[:500],
                        "source_query": query,
                    }

                    text = getattr(item, "text", "") or ""
                    for pattern in [
                        r"(\d{1,3}(?:,\d{3})*)\s*(?:บาท|THB)",
                        r"\$\s*(\d{1,3}(?:,\d{3})*)",
                        r"(\d{1,3}(?:,\d{3})*)\s*USD",
                    ]:
                        match = re.search(pattern, text, re.IGNORECASE)
                        if match:
                            package_info["price_found"] = match.group(0)
                            results["prices_found"].append(
                                {"price": match.group(0), "source": package_info["url"]}
                            )
                            break

                    results["packages_found"].append(package_info)

            except Exception as e:
                logger.warning(f"EXA search failed for '{query}': {e}")

    except ImportError:
        logger.info("exa-py not installed; skipping web research")
    except Exception as e:
        logger.warning(f"Web research failed: {e}")

    return results


# ---------------------------------------------------------------------------
# Knowledge Aggregation
# ---------------------------------------------------------------------------

def _aggregate_knowledge(
    valid_documents: list,
    extracted_data: list,
    main_destination: str,
    top_themes: list,
    top_activities: list,
    web_research: dict,
) -> dict:
    """Aggregate extracted data into a knowledge graph structure."""
    entities = []
    relationships = []

    # Destination entity
    entities.append(
        {
            "type": "destination",
            "name": main_destination,
            "properties": {
                "total_products": len(valid_documents),
                "themes": [t[0] for t in top_themes[:5]],
                "activities": [a[0] for a in top_activities[:10]],
                "web_packages_found": len(web_research.get("packages_found", [])),
            },
        }
    )

    # Product entities from documents
    for data in extracted_data:
        entities.append(
            {
                "type": "product",
                "name": data.get("document_name", "Unknown"),
                "properties": {
                    "destinations": data.get("destinations", []),
                    "themes": data.get("themes", []),
                    "duration": data.get("duration"),
                    "target_audience": data.get("target_audience"),
                },
            }
        )

        for dest in data.get("destinations", []):
            relationships.append(
                {
                    "from": data.get("document_name"),
                    "to": dest,
                    "type": "visits",
                }
            )

    # Competitor entities from web research
    for pkg in web_research.get("packages_found", [])[:5]:
        entities.append(
            {
                "type": "competitor_product",
                "name": pkg.get("title", "Unknown"),
                "properties": {
                    "url": pkg.get("url"),
                    "price": pkg.get("price_found"),
                    "snippet": pkg.get("snippet", "")[:200],
                },
            }
        )

    return {"entities": entities, "relationships": relationships}


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def _generate_market_report(
    client: OpenAI,
    valid_documents: list,
    main_destination: str,
    main_theme: str,
    top_destinations: list,
    top_themes: list,
    top_activities: list,
    web_research: dict,
) -> str:
    """Generate a comprehensive market intelligence report."""
    report_context = (
        f"## Market Intelligence Analysis Summary\n\n"
        f"### Documents Analyzed\n"
        f"- Total documents: {len(valid_documents)}\n"
        f"- Main destination: {main_destination}\n"
        f"- Main theme: {main_theme}\n\n"
        f"### Destination Distribution\n"
        f"{json.dumps(dict(top_destinations), indent=2)}\n\n"
        f"### Theme Distribution\n"
        f"{json.dumps(dict(top_themes), indent=2)}\n\n"
        f"### Popular Activities\n"
        f"{json.dumps(dict(top_activities[:10]), indent=2)}\n\n"
        f"### Web Research Findings\n"
        f"- Competitor packages found: {len(web_research.get('packages_found', []))}\n"
        f"- Price points discovered: {len(web_research.get('prices_found', []))}\n\n"
        f"### Sample Competitor Products:\n"
        f"{json.dumps(web_research.get('packages_found', [])[:5], indent=2, default=str)}\n\n"
        f"### Price Data Found:\n"
        f"{json.dumps(web_research.get('prices_found', [])[:10], indent=2, default=str)}"
    )

    report_prompt = (
        f"Based on this market intelligence data, generate a comprehensive "
        f"strategic report for a travel business.\n\n"
        f"{report_context}\n\n"
        f"Generate a professional market intelligence report with these sections:\n\n"
        f"1. **Executive Summary** - Key findings in 3-4 bullet points\n"
        f"2. **Market Overview** - Analysis of the {main_destination} {main_theme} market\n"
        f"3. **Product Portfolio Analysis** - Insights from the analyzed documents\n"
        f"4. **Competitive Landscape** - What competitors are offering\n"
        f"5. **Pricing Intelligence** - Price trends and positioning opportunities\n"
        f"6. **Strategic Recommendations** - 3-5 actionable recommendations\n"
        f"7. **Opportunities & Threats** - SWOT-style analysis\n\n"
        f"Make it actionable and data-driven. Use specific numbers."
    )

    try:
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL_ANALYSIS,
            messages=[{"role": "user", "content": report_prompt}],
            temperature=0.7,
            max_tokens=2500,
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Full Analysis Pipeline (convenience wrapper)
# ---------------------------------------------------------------------------

def analyze_itinerary_file(file_path: str, language: str = "auto") -> dict:
    """
    End-to-end analysis of an itinerary file.

    Accepts PDF, DOCX, or text files.
    Returns structured itinerary data + metadata.
    """
    ext = os.path.splitext(file_path)[1].lower()

    # Extract text
    if ext == ".pdf":
        extraction = extract_text_from_pdf(file_path)
        if not extraction["success"]:
            return {"status": "error", "error": extraction.get("error", "PDF extraction failed")}
        raw_text = extraction["text"]
        metadata = {
            "total_pages": extraction["total_pages"],
            "quality_score": extraction["quality_score"],
            "content_types": extraction["content_types"],
        }
    elif ext == ".docx":
        from services.document_parser import _parse_docx

        result = _parse_docx(file_path)
        raw_text = result.get("raw_text", "")
        metadata = {"file_type": "docx"}
    elif ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
        metadata = {"file_type": "text"}
    else:
        return {"status": "error", "error": f"Unsupported file type: {ext}"}

    if not raw_text or len(raw_text.strip()) < 50:
        return {"status": "error", "error": "Insufficient text extracted from file"}

    # Analyse
    analysis_result = analyze_itinerary(raw_text, language)

    if analysis_result["status"] != "success":
        return analysis_result

    return {
        "status": "success",
        "file_path": file_path,
        "raw_text_length": len(raw_text),
        "language": analysis_result["language"],
        "data": analysis_result["data"],
        "metadata": metadata,
    }
