"""
Itinerary Analysis Tools.

Provides standalone tool functions for the Data Analysis Agent and
Market Analysis Agent to work with travel itineraries.

Tools:
- analyze_itinerary_tool       - Parse an itinerary file and extract structured data
- compare_itineraries_tool     - Compare 2+ analysed itineraries
- market_intelligence_tool     - Run full market intelligence pipeline
- extract_pdf_text_tool        - Extract raw text from PDF files
- generate_recommendations_tool - Generate strategic recommendations

These are designed to be used directly or wrapped as CrewAI BaseTool
subclasses when the agent framework is wired up.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, List

from config import Config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: Analyze Itinerary
# ---------------------------------------------------------------------------

def analyze_itinerary_tool(
    file_path: str,
    language: str = "auto",
    save_output: bool = True,
) -> dict:
    """
    Parse an itinerary file (PDF, DOCX, TXT) and extract structured data.

    Extracts: tour name, duration, destinations, pricing, flights,
    inclusions/exclusions, and day-by-day breakdown.

    Args:
        file_path: Path to the itinerary document
        language: 'auto', 'English', or 'Thai'
        save_output: Whether to save the result to data/

    Returns:
        {
            "status": "success" | "error",
            "data": { structured itinerary data },
            "language": "English" | "Thai",
            "file_path": str,
            ...
        }
    """
    from services.itinerary_analyzer import analyze_itinerary_file

    result = analyze_itinerary_file(file_path, language)

    if save_output and result.get("status") == "success":
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        basename = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(Config.DATA_DIR, f"itinerary_{basename}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "analyzed_at": datetime.now().isoformat(),
                    "source_file": file_path,
                    **result,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        result["output_path"] = output_path
        logger.info(f"Itinerary analysis saved to {output_path}")

    return result


# ---------------------------------------------------------------------------
# Tool: Compare Itineraries
# ---------------------------------------------------------------------------

def compare_itineraries_tool(
    itinerary_files: Optional[List[str]] = None,
    itinerary_data: Optional[List[dict]] = None,
    language: str = "English",
    save_output: bool = True,
) -> dict:
    """
    Compare multiple itineraries side by side.

    Provide either file paths (will be analysed first) or
    pre-analysed itinerary data dicts.

    Args:
        itinerary_files: List of file paths to itinerary documents
        itinerary_data: List of dicts with 'name' and 'analysis' keys
        language: Output language
        save_output: Whether to save comparison to data/

    Returns:
        {
            "status": "success" | "error",
            "comparison": str (markdown report),
            ...
        }
    """
    from services.itinerary_analyzer import (
        analyze_itinerary_file,
        compare_itineraries,
    )

    # Build itinerary list
    itineraries = []

    if itinerary_data:
        itineraries.extend(itinerary_data)

    if itinerary_files:
        for fpath in itinerary_files:
            result = analyze_itinerary_file(fpath, language)
            if result.get("status") == "success":
                name = os.path.splitext(os.path.basename(fpath))[0]
                itineraries.append({
                    "name": name,
                    "analysis": result["data"],
                    "text": "",
                })
            else:
                logger.warning(f"Skipping {fpath}: {result.get('error')}")

    if len(itineraries) < 2:
        return {
            "status": "error",
            "error": f"Need at least 2 itineraries to compare (got {len(itineraries)})",
        }

    comparison_result = compare_itineraries(itineraries, language)

    if save_output and comparison_result.get("status") == "success":
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        output_path = os.path.join(Config.DATA_DIR, "itinerary_comparison.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "compared_at": datetime.now().isoformat(),
                    "itineraries": [it["name"] for it in itineraries],
                    "comparison": comparison_result["comparison"],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        comparison_result["output_path"] = output_path

    return comparison_result


# ---------------------------------------------------------------------------
# Tool: Market Intelligence
# ---------------------------------------------------------------------------

def market_intelligence_tool(
    document_paths: Optional[List[str]] = None,
    document_texts: Optional[List[dict]] = None,
    include_web_research: bool = True,
    fast_mode: bool = True,
    save_output: bool = True,
) -> dict:
    """
    Run the full market intelligence pipeline on itinerary documents.

    Pipeline: Extract -> Analyse Themes -> Web Research -> Aggregate -> Report

    Args:
        document_paths: List of file paths to parse
        document_texts: List of dicts with 'name' and 'text' keys
        include_web_research: Whether to search web for competitors
        fast_mode: Limit documents for speed
        save_output: Whether to save result to data/

    Returns:
        Full market intelligence report with themes, web research,
        knowledge graph, and strategic report.
    """
    from services.itinerary_analyzer import (
        extract_text_from_pdf,
        run_market_intelligence,
    )

    documents = []

    # Collect documents from texts
    if document_texts:
        documents.extend(document_texts)

    # Parse file paths
    if document_paths:
        for fpath in document_paths:
            ext = os.path.splitext(fpath)[1].lower()
            if ext == ".pdf":
                extraction = extract_text_from_pdf(fpath)
                if extraction["success"]:
                    documents.append({
                        "name": os.path.basename(fpath),
                        "text": extraction["text"],
                    })
            elif ext in (".txt", ".md"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        documents.append({
                            "name": os.path.basename(fpath),
                            "text": f.read(),
                        })
                except Exception as e:
                    logger.warning(f"Failed to read {fpath}: {e}")

    if not documents:
        return {"status": "error", "error": "No documents provided"}

    result = run_market_intelligence(
        documents=documents,
        include_web_research=include_web_research,
        fast_mode=fast_mode,
        generate_report=True,
    )

    if save_output and result.get("success"):
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        output_path = os.path.join(Config.DATA_DIR, "market_intelligence.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {"generated_at": datetime.now().isoformat(), **result},
                f,
                ensure_ascii=False,
                indent=2,
            )
        result["output_path"] = output_path

    return result


# ---------------------------------------------------------------------------
# Tool: Extract PDF Text
# ---------------------------------------------------------------------------

def extract_pdf_text_tool(file_path: str) -> dict:
    """
    Extract raw text from a PDF file using PyMuPDF.

    Also detects content types (Thai, prices, tables) and
    provides a quality score.

    Args:
        file_path: Path to the PDF file

    Returns:
        {
            "success": True/False,
            "text": str,
            "total_pages": int,
            "quality_score": "high" | "medium" | "low",
            "content_types": { "has_thai": bool, ... },
        }
    """
    from services.itinerary_analyzer import extract_text_from_pdf

    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    return extract_text_from_pdf(file_path)


# ---------------------------------------------------------------------------
# Tool: Generate Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations_tool(
    itinerary_data: List[dict],
    language: str = "English",
    save_output: bool = True,
) -> dict:
    """
    Generate strategic recommendations based on analysed itineraries.

    Args:
        itinerary_data: List of dicts with 'name' and 'analysis' keys
        language: Output language
        save_output: Whether to save to data/

    Returns:
        {
            "status": "success" | "error",
            "recommendations": str (markdown report),
        }
    """
    from services.itinerary_analyzer import generate_recommendations

    result = generate_recommendations(itinerary_data, language)

    if save_output and result.get("status") == "success":
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        output_path = os.path.join(Config.DATA_DIR, "itinerary_recommendations.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "recommendations": result["recommendations"],
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        result["output_path"] = output_path

    return result


# ---------------------------------------------------------------------------
# Tool: Batch Analyze Directory
# ---------------------------------------------------------------------------

def batch_analyze_directory_tool(
    directory_path: str,
    language: str = "auto",
    run_comparison: bool = True,
    run_market_intel: bool = True,
) -> dict:
    """
    Analyse all itinerary files in a directory.

    Scans for PDF and text files, analyses each one, then
    optionally runs comparison and market intelligence.

    Args:
        directory_path: Path to folder containing itinerary files
        language: 'auto', 'English', or 'Thai'
        run_comparison: Whether to compare all found itineraries
        run_market_intel: Whether to run market intelligence pipeline

    Returns:
        {
            "files_found": int,
            "files_analyzed": int,
            "individual_analyses": [...],
            "comparison": str or None,
            "market_intelligence": dict or None,
        }
    """
    supported_extensions = {".pdf", ".txt", ".md", ".docx"}
    files = []

    for fname in os.listdir(directory_path):
        ext = os.path.splitext(fname)[1].lower()
        if ext in supported_extensions:
            files.append(os.path.join(directory_path, fname))

    if not files:
        return {"status": "error", "error": f"No supported files found in {directory_path}"}

    # Analyse each file
    analyses = []
    for fpath in files:
        result = analyze_itinerary_tool(fpath, language, save_output=True)
        if result.get("status") == "success":
            analyses.append({
                "file": fpath,
                "name": os.path.splitext(os.path.basename(fpath))[0],
                "analysis": result["data"],
            })

    output = {
        "status": "success",
        "files_found": len(files),
        "files_analyzed": len(analyses),
        "individual_analyses": analyses,
        "comparison": None,
        "market_intelligence": None,
    }

    # Comparison
    if run_comparison and len(analyses) >= 2:
        comp = compare_itineraries_tool(
            itinerary_data=analyses, language=language
        )
        output["comparison"] = comp.get("comparison")

    # Market intelligence
    if run_market_intel and analyses:
        from services.itinerary_analyzer import extract_text_from_pdf

        docs = []
        for fpath in files:
            ext = os.path.splitext(fpath)[1].lower()
            if ext == ".pdf":
                extraction = extract_text_from_pdf(fpath)
                if extraction["success"]:
                    docs.append({"name": os.path.basename(fpath), "text": extraction["text"]})
            elif ext in (".txt", ".md"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        docs.append({"name": os.path.basename(fpath), "text": f.read()})
                except Exception:
                    pass

        if docs:
            mi = market_intelligence_tool(document_texts=docs)
            output["market_intelligence"] = mi

    return output
