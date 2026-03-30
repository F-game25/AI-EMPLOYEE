"""Financial DeepSearch Bot — Dexter AI-style open-source financial intelligence.

Performs deep financial research by combining multiple free/open-source data
sources with AI synthesis:

  - Yahoo Finance via yfinance (open-source Python library, no key needed)
  - SEC EDGAR public API (free US government filings API, no key needed)
  - DuckDuckGo instant answers (no API key needed)
  - Alpha Vantage (optional, requires ALPHA_VANTAGE_KEY env var)

Commands (via chatlog / WhatsApp / Dashboard):
  deepsearch company <ticker>          — comprehensive company deep-dive
  deepsearch market <sector>           — sector-level market analysis
  deepsearch news <ticker>             — latest financial news synthesis
  deepsearch compare <t1> vs <t2>      — side-by-side company comparison
  deepsearch macro <topic>             — macroeconomic deep research
  deepsearch sec <ticker>              — SEC filing insights
  deepsearch earnings <ticker>         — earnings history & quality analysis
  deepsearch status                    — show recent searches

Configuration (~/.ai-employee/config/financial-deepsearch.env):
    FINANCIAL_DEEPSEARCH_POLL_INTERVAL — poll interval in seconds (default: 5)
    FINANCIAL_DEEPSEARCH_TIMEOUT       — HTTP timeout in seconds (default: 15)
    ALPHA_VANTAGE_KEY                  — Alpha Vantage API key (optional)

State files:
  ~/.ai-employee/state/financial-deepsearch.state.json
  ~/.ai-employee/state/financial-deepsearch-results.jsonl
"""
import json
import logging
import os
import sys
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "financial-deepsearch.state.json"
RESULTS_FILE = AI_HOME / "state" / "financial-deepsearch-results.jsonl"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("FINANCIAL_DEEPSEARCH_POLL_INTERVAL", "5"))
HTTP_TIMEOUT = int(os.environ.get("FINANCIAL_DEEPSEARCH_TIMEOUT", "15"))
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("financial-deepsearch")

# ── AI router ─────────────────────────────────────────────────────────────────

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

# ── yfinance (optional, install with: pip install yfinance) ───────────────────

try:
    import yfinance as yf  # type: ignore
    _YFINANCE_AVAILABLE = True
except ImportError:
    _YFINANCE_AVAILABLE = False

# ── Helpers ───────────────────────────────────────────────────────────────────


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    try:
        lines = [line for line in CHATLOG.read_text().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]
    except Exception:
        return []


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def append_result(result: dict) -> None:
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "a") as f:
        f.write(json.dumps(result) + "\n")


def ai_query(prompt: str, system_prompt: str = "") -> str:
    if not _AI_AVAILABLE:
        return "AI router not available."
    try:
        result = _query_ai_for_agent("financial-deepsearch", prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        return f"AI query failed: {exc}"


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_FINANCIAL_ANALYST = (
    "You are Dexter, an elite financial deep-search analyst combining the expertise of "
    "a sell-side equity analyst, CFA charterholder, and data scientist. "
    "You synthesize data from SEC filings, earnings reports, market data, and financial news "
    "into actionable investment-grade intelligence. Be precise, cite specific numbers, "
    "identify key risks and opportunities, and deliver clear institutional-quality insights. "
    "Always note data freshness limitations and recommend further diligence where appropriate."
)

# ── Data Fetchers ─────────────────────────────────────────────────────────────


def _http_get(url: str, headers: dict | None = None) -> dict | None:
    """Safe HTTP GET returning parsed JSON or None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers=headers or {"User-Agent": "AI-Employee/1.0 financial-deepsearch-bot"},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.debug("HTTP GET failed %s: %s", url, exc)
        return None


def fetch_yfinance_data(ticker: str) -> dict:
    """Fetch comprehensive stock data from Yahoo Finance via yfinance (open-source)."""
    if not _YFINANCE_AVAILABLE:
        return {"error": "yfinance not installed — run: pip install yfinance", "ticker": ticker}
    try:
        t = yf.Ticker(ticker)
        info: dict[str, Any] = t.info or {}
        hist = t.history(period="1y")

        price_summary: dict[str, Any] = {}
        if not hist.empty:
            price_summary = {
                "current": round(float(hist["Close"].iloc[-1]), 2),
                "52w_high": round(float(hist["Close"].max()), 2),
                "52w_low": round(float(hist["Close"].min()), 2),
                "avg_volume": int(hist["Volume"].mean()),
                "ytd_change_pct": round(
                    (
                        (hist["Close"].iloc[-1] - hist["Close"].iloc[0])
                        / hist["Close"].iloc[0]
                    )
                    * 100,
                    2,
                ),
            }

        fields = [
            "longName", "sector", "industry", "country", "marketCap",
            "trailingPE", "forwardPE", "priceToBook", "debtToEquity",
            "returnOnEquity", "returnOnAssets", "grossMargins", "operatingMargins",
            "profitMargins", "revenueGrowth", "earningsGrowth",
            "totalRevenue", "ebitda", "freeCashflow", "totalCash", "totalDebt",
            "dividendYield", "beta", "sharesOutstanding", "floatShares",
            "shortPercentOfFloat", "recommendationKey", "targetMeanPrice",
            "numberOfAnalystOpinions", "longBusinessSummary",
        ]
        summary = {k: info.get(k) for k in fields if info.get(k) is not None}

        return {
            "ticker": ticker.upper(),
            "price": price_summary,
            "fundamentals": summary,
            "source": "Yahoo Finance (yfinance)",
        }
    except Exception as exc:
        return {"error": f"yfinance fetch failed: {exc}", "ticker": ticker}


def fetch_sec_filings(ticker: str) -> dict:
    """Fetch recent SEC filings from EDGAR public API (free, no key needed)."""
    # Resolve CIK from the EDGAR company tickers file
    cik_data = _http_get("https://www.sec.gov/files/company_tickers.json")
    cik: str | None = None
    company_name: str | None = None
    if cik_data:
        for entry in cik_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry.get("cik_str", "")).zfill(10)
                company_name = entry.get("title")
                break

    if not cik:
        return {"error": f"Ticker '{ticker}' not found in SEC EDGAR", "ticker": ticker}

    # Fetch recent filing history
    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    subs = _http_get(submissions_url)
    if not subs:
        return {"error": "SEC EDGAR submissions API unavailable", "ticker": ticker, "cik": cik}

    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])

    key_filings = []
    for i, form in enumerate(forms[:50]):
        if form in ("10-K", "10-Q", "8-K"):
            key_filings.append({
                "form": form,
                "date": dates[i] if i < len(dates) else "",
                "accession": accessions[i] if i < len(accessions) else "",
            })
        if len(key_filings) >= 10:
            break

    return {
        "ticker": ticker.upper(),
        "company": company_name,
        "cik": cik,
        "recent_filings": key_filings,
        "source": "SEC EDGAR",
    }


def fetch_duckduckgo_news(query: str) -> list[dict]:
    """Fetch financial context via DuckDuckGo instant answers (no API key needed)."""
    try:
        url = (
            "https://api.duckduckgo.com/?q="
            + urllib.parse.quote(f"{query} financial analysis")
            + "&format=json&no_redirect=1&no_html=1"
        )
        data = _http_get(url, headers={"User-Agent": "Mozilla/5.0 AI-Employee/1.0"})
        if not data:
            return []
        results = []
        for topic in data.get("RelatedTopics", [])[:8]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:120],
                    "url": topic.get("FirstURL", ""),
                })
        return results
    except Exception:
        return []


def fetch_alpha_vantage(ticker: str, function: str = "OVERVIEW") -> dict:
    """Fetch fundamental data from Alpha Vantage (free tier, requires ALPHA_VANTAGE_KEY)."""
    if not ALPHA_VANTAGE_KEY:
        return {"available": False}
    url = (
        f"https://www.alphavantage.co/query?function={function}"
        f"&symbol={urllib.parse.quote(ticker)}&apikey={ALPHA_VANTAGE_KEY}"
    )
    data = _http_get(url)
    if not data:
        return {"error": "Alpha Vantage API unavailable"}
    if "Information" in data:
        return {"error": data["Information"]}
    return data


# ── Command Handlers ──────────────────────────────────────────────────────────


def cmd_company(ticker: str) -> str:
    """Comprehensive company deep-dive analysis."""
    ticker = ticker.upper().strip()

    yf_data = fetch_yfinance_data(ticker)
    sec_data = fetch_sec_filings(ticker)
    news = fetch_duckduckgo_news(f"{ticker} stock earnings results")

    context_parts = [f"## Company: {ticker}\n"]

    if "error" not in yf_data:
        fund = yf_data.get("fundamentals", {})
        price = yf_data.get("price", {})
        context_parts.append(
            f"### Market Data (Yahoo Finance)\n"
            f"Name: {fund.get('longName', ticker)} | "
            f"Sector: {fund.get('sector', 'N/A')} | Industry: {fund.get('industry', 'N/A')}\n"
            f"Market Cap: ${fund.get('marketCap', 0):,.0f}\n"
            f"Price: ${price.get('current', 'N/A')} | "
            f"52w High: ${price.get('52w_high', 'N/A')} | "
            f"52w Low: ${price.get('52w_low', 'N/A')} | "
            f"YTD: {price.get('ytd_change_pct', 'N/A')}%\n"
            f"P/E Trailing: {fund.get('trailingPE', 'N/A')} | "
            f"P/E Forward: {fund.get('forwardPE', 'N/A')} | "
            f"P/B: {fund.get('priceToBook', 'N/A')}\n"
            f"Revenue: ${fund.get('totalRevenue', 0):,.0f} | "
            f"EBITDA: ${fund.get('ebitda', 0):,.0f}\n"
            f"Gross Margin: {fund.get('grossMargins', 'N/A')} | "
            f"Op Margin: {fund.get('operatingMargins', 'N/A')} | "
            f"Net Margin: {fund.get('profitMargins', 'N/A')}\n"
            f"Revenue Growth: {fund.get('revenueGrowth', 'N/A')} | "
            f"Earnings Growth: {fund.get('earningsGrowth', 'N/A')}\n"
            f"Free Cash Flow: ${fund.get('freeCashflow', 0):,.0f} | "
            f"Cash: ${fund.get('totalCash', 0):,.0f} | "
            f"Debt: ${fund.get('totalDebt', 0):,.0f}\n"
            f"D/E Ratio: {fund.get('debtToEquity', 'N/A')} | "
            f"ROE: {fund.get('returnOnEquity', 'N/A')} | "
            f"ROA: {fund.get('returnOnAssets', 'N/A')}\n"
            f"Beta: {fund.get('beta', 'N/A')} | "
            f"Short Float: {fund.get('shortPercentOfFloat', 'N/A')}\n"
            f"Analyst Rating: {fund.get('recommendationKey', 'N/A')} | "
            f"Target: ${fund.get('targetMeanPrice', 'N/A')} | "
            f"# Analysts: {fund.get('numberOfAnalystOpinions', 'N/A')}\n"
            f"Business: {str(fund.get('longBusinessSummary', ''))[:400]}\n"
        )
    else:
        context_parts.append(f"Market data unavailable: {yf_data.get('error')}\n")

    if "error" not in sec_data and sec_data.get("recent_filings"):
        filings_text = "\n".join(
            f"  - {f['form']} filed {f['date']}"
            for f in sec_data["recent_filings"][:5]
        )
        context_parts.append(f"### SEC Filings\n{filings_text}\n")

    if news:
        news_text = "\n".join(f"  - {n['title']}" for n in news[:5])
        context_parts.append(f"### Recent Context\n{news_text}\n")

    context = "\n".join(context_parts)

    prompt = (
        f"{context}\n\n"
        f"Perform a comprehensive deep-search financial analysis of {ticker}:\n\n"
        f"## 1. Executive Summary\n"
        f"Bull case, bear case, and base case — 3 bullet points each.\n\n"
        f"## 2. Financial Health Score (1-10)\n"
        f"Rate: Profitability | Growth | Balance Sheet | Cash Flow | Valuation\n"
        f"Overall score and reasoning.\n\n"
        f"## 3. Valuation Analysis\n"
        f"Current vs fair value, key multiples vs peers, DCF sanity check.\n\n"
        f"## 4. Competitive Moat\n"
        f"What protects this business? Rate moat: Wide / Narrow / None\n\n"
        f"## 5. Key Risks (Top 5)\n"
        f"Ranked by severity with likelihood estimate.\n\n"
        f"## 6. Catalysts (Next 12 Months)\n"
        f"What could move the stock significantly up or down?\n\n"
        f"## 7. Investment Verdict\n"
        f"Strong Buy / Buy / Hold / Sell / Strong Sell with price target range.\n\n"
        f"## 8. Key Metrics to Monitor\n"
        f"3-5 data points that will validate or invalidate the thesis."
    )

    result = ai_query(prompt, SYSTEM_FINANCIAL_ANALYST)
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "company",
        "ticker": ticker,
        "result": result,
        "ts": now_iso(),
    })
    return f"🔬 *Financial DeepSearch: {ticker}*\n\n{result}"


def cmd_market(sector: str) -> str:
    """Market sector deep analysis."""
    news = fetch_duckduckgo_news(f"{sector} sector stocks market")
    news_context = (
        "Recent context:\n" + "\n".join(f"- {n['title']}" for n in news[:5])
        if news else ""
    )

    result = ai_query(
        f"Perform a deep-search analysis of the {sector} sector.\n"
        f"{news_context}\n\n"
        f"## 1. Sector Overview\n"
        f"Current state, key tailwinds, key headwinds.\n\n"
        f"## 2. Top 5 Companies to Watch\n"
        f"Name, ticker, why they stand out, key metric.\n\n"
        f"## 3. Sector Valuation\n"
        f"Cheap, fair, or expensive vs historical averages?\n\n"
        f"## 4. Macro Influences\n"
        f"Interest rates, inflation, regulation, geopolitics impact.\n\n"
        f"## 5. Investment Themes (6-12 months)\n"
        f"3 specific alpha-generating themes in this sector.\n\n"
        f"## 6. Key Risks\n"
        f"Sector-specific risks to monitor.\n\n"
        f"## 7. ETF Exposure Options\n"
        f"Top 3 ETFs for this sector with tickers.",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "market",
        "sector": sector,
        "result": result,
        "ts": now_iso(),
    })
    return f"📊 *Sector DeepSearch: {sector}*\n\n{result}"


def cmd_news(ticker: str) -> str:
    """Latest financial news synthesis for a ticker."""
    ticker = ticker.upper().strip()
    yf_data = fetch_yfinance_data(ticker)
    news = fetch_duckduckgo_news(f"{ticker} stock earnings financial news")

    fund = yf_data.get("fundamentals", {}) if "error" not in yf_data else {}
    price = yf_data.get("price", {}) if "error" not in yf_data else {}
    company_name = fund.get("longName", ticker)

    price_context = (
        f"Price: ${price.get('current', 'N/A')} | "
        f"52w range: ${price.get('52w_low', 'N/A')}–${price.get('52w_high', 'N/A')} | "
        f"YTD: {price.get('ytd_change_pct', 'N/A')}%"
        if price else "Price data unavailable"
    )
    news_text = "\n".join(f"- {n['title']}" for n in news) if news else "No recent context found."

    result = ai_query(
        f"Company: {company_name} ({ticker})\n"
        f"{price_context}\n\n"
        f"Recent context:\n{news_text}\n\n"
        f"## News Impact Assessment\n"
        f"For each major story: what happened, why it matters, likely price impact.\n\n"
        f"## Sentiment Score\n"
        f"Overall news sentiment: Bullish / Neutral / Bearish (rate 1-10).\n\n"
        f"## What to Watch Next\n"
        f"Upcoming catalysts, earnings dates, events to monitor.\n\n"
        f"## Trading Implications\n"
        f"Short-term (1-4 weeks) positioning based on the news flow.",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "news",
        "ticker": ticker,
        "result": result,
        "ts": now_iso(),
    })
    return f"📰 *News DeepSearch: {ticker}*\n\n{result}"


def cmd_compare(ticker1: str, ticker2: str) -> str:
    """Side-by-side company comparison."""
    ticker1, ticker2 = ticker1.upper().strip(), ticker2.upper().strip()

    d1 = fetch_yfinance_data(ticker1)
    d2 = fetch_yfinance_data(ticker2)

    def _summary(data: dict, t: str) -> str:
        if "error" in data:
            return f"{t}: data unavailable ({data['error']})"
        f = data.get("fundamentals", {})
        p = data.get("price", {})
        return (
            f"{t} ({f.get('longName', t)}):\n"
            f"  Sector: {f.get('sector', 'N/A')} | Industry: {f.get('industry', 'N/A')}\n"
            f"  Market Cap: ${f.get('marketCap', 0):,.0f}\n"
            f"  Price: ${p.get('current', 'N/A')} | YTD: {p.get('ytd_change_pct', 'N/A')}%\n"
            f"  P/E: {f.get('trailingPE', 'N/A')} | Fwd P/E: {f.get('forwardPE', 'N/A')}\n"
            f"  Revenue Growth: {f.get('revenueGrowth', 'N/A')} | "
            f"Earnings Growth: {f.get('earningsGrowth', 'N/A')}\n"
            f"  Gross Margin: {f.get('grossMargins', 'N/A')} | "
            f"Op Margin: {f.get('operatingMargins', 'N/A')}\n"
            f"  FCF: ${f.get('freeCashflow', 0):,.0f} | D/E: {f.get('debtToEquity', 'N/A')}\n"
            f"  ROE: {f.get('returnOnEquity', 'N/A')} | Beta: {f.get('beta', 'N/A')}\n"
            f"  Analyst: {f.get('recommendationKey', 'N/A')} | "
            f"Target: ${f.get('targetMeanPrice', 'N/A')}"
        )

    context = f"{_summary(d1, ticker1)}\n\n{_summary(d2, ticker2)}"

    result = ai_query(
        f"Compare {ticker1} vs {ticker2}:\n\n{context}\n\n"
        f"## Side-by-Side Scorecard\n"
        f"| Metric | {ticker1} | {ticker2} | Winner |\n"
        f"|--------|--------|--------|--------|\n"
        f"Fill in rows: Valuation | Growth | Profitability | Balance Sheet | Momentum\n\n"
        f"## Competitive Positioning\n"
        f"Same market or different? Direct rivals or complements?\n\n"
        f"## Risk/Reward Comparison\n"
        f"Which offers better risk-adjusted returns? Specific reasoning with numbers.\n\n"
        f"## Verdict\n"
        f"If you can only own one for the next 12 months, which one and why?",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "compare",
        "tickers": [ticker1, ticker2],
        "result": result,
        "ts": now_iso(),
    })
    return f"⚖️ *Comparison DeepSearch: {ticker1} vs {ticker2}*\n\n{result}"


def cmd_macro(topic: str) -> str:
    """Macroeconomic deep research."""
    news = fetch_duckduckgo_news(f"{topic} macroeconomic economy market impact")
    news_context = (
        "Recent context:\n" + "\n".join(f"- {n['title']}" for n in news[:5])
        if news else ""
    )

    result = ai_query(
        f"Macroeconomic deep-search analysis: {topic}\n"
        f"{news_context}\n\n"
        f"## Macro Overview\n"
        f"Current state and historical context.\n\n"
        f"## Key Indicators to Monitor\n"
        f"Most important data points with current vs historical norms.\n\n"
        f"## Market Implications\n"
        f"How this macro factor affects: Equities | Bonds | Commodities | FX | Crypto\n\n"
        f"## Sector Impact Matrix\n"
        f"Which sectors benefit vs suffer most? Why?\n\n"
        f"## Central Bank Implications\n"
        f"How this influences monetary policy outlook.\n\n"
        f"## 6-12 Month Outlook\n"
        f"Bull/base/bear case scenarios with probability estimates.\n\n"
        f"## Actionable Ideas\n"
        f"3 specific trade ideas or positioning changes based on this analysis.",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "macro",
        "topic": topic,
        "result": result,
        "ts": now_iso(),
    })
    return f"🌍 *Macro DeepSearch: {topic}*\n\n{result}"


def cmd_sec(ticker: str) -> str:
    """SEC filing deep analysis."""
    ticker = ticker.upper().strip()
    sec_data = fetch_sec_filings(ticker)
    yf_data = fetch_yfinance_data(ticker)

    if "error" in sec_data:
        sec_context = f"SEC data unavailable: {sec_data['error']}"
    else:
        filings_text = "\n".join(
            f"  - {f['form']} filed {f['date']} (accession: {f['accession']})"
            for f in sec_data.get("recent_filings", [])
        )
        sec_context = (
            f"Company: {sec_data.get('company', ticker)} ({ticker}) | "
            f"CIK: {sec_data.get('cik', 'N/A')}\n\n"
            f"Recent SEC Filings:\n{filings_text or 'No filings found'}"
        )

    fund = yf_data.get("fundamentals", {}) if "error" not in yf_data else {}
    financials_context = ""
    if fund:
        financials_context = (
            f"\n\nLatest Financials:\n"
            f"Revenue: ${fund.get('totalRevenue', 0):,.0f} | "
            f"EBITDA: ${fund.get('ebitda', 0):,.0f}\n"
            f"Gross Margin: {fund.get('grossMargins', 'N/A')} | "
            f"Net Margin: {fund.get('profitMargins', 'N/A')}\n"
            f"Cash: ${fund.get('totalCash', 0):,.0f} | "
            f"Total Debt: ${fund.get('totalDebt', 0):,.0f}"
        )

    result = ai_query(
        f"{sec_context}{financials_context}\n\n"
        f"Analyze the SEC filing profile for {ticker}:\n\n"
        f"## Filing Pattern Analysis\n"
        f"What do timing and types of filings suggest about this company?\n\n"
        f"## What to Scrutinize in the 10-K\n"
        f"Top 5 items to examine in the annual report for this company/sector.\n\n"
        f"## Quarterly Metrics to Track (10-Q)\n"
        f"Key metrics to compare quarter-over-quarter.\n\n"
        f"## Accounting Red Flags\n"
        f"Common disclosure risks for this sector to watch for.\n\n"
        f"## Management Commentary Signals\n"
        f"Key phrases or disclosures that signal quality or deterioration.\n\n"
        f"## EDGAR Research Links\n"
        f"How to access and read these filings on SEC.gov.",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "sec",
        "ticker": ticker,
        "result": result,
        "ts": now_iso(),
    })
    return f"📋 *SEC DeepSearch: {ticker}*\n\n{result}"


def cmd_earnings(ticker: str) -> str:
    """Earnings history and quality analysis."""
    ticker = ticker.upper().strip()
    yf_data = fetch_yfinance_data(ticker)

    fund = yf_data.get("fundamentals", {}) if "error" not in yf_data else {}
    price = yf_data.get("price", {}) if "error" not in yf_data else {}

    if fund:
        context = (
            f"Ticker: {ticker} | {fund.get('longName', ticker)}\n"
            f"Price: ${price.get('current', 'N/A')} | YTD: {price.get('ytd_change_pct', 'N/A')}%\n"
            f"Trailing P/E: {fund.get('trailingPE', 'N/A')} | "
            f"Forward P/E: {fund.get('forwardPE', 'N/A')}\n"
            f"Revenue Growth: {fund.get('revenueGrowth', 'N/A')} | "
            f"Earnings Growth: {fund.get('earningsGrowth', 'N/A')}\n"
            f"Analyst Rating: {fund.get('recommendationKey', 'N/A')} | "
            f"Target: ${fund.get('targetMeanPrice', 'N/A')} | "
            f"Analysts: {fund.get('numberOfAnalystOpinions', 'N/A')}"
        )
    else:
        context = f"Market data unavailable for {ticker}"

    result = ai_query(
        f"{context}\n\n"
        f"Earnings deep-dive for {ticker}:\n\n"
        f"## Earnings Quality Assessment\n"
        f"Is earnings growth sustainable? Organic vs engineered?\n\n"
        f"## Beat/Miss History Analysis\n"
        f"What does typical EPS beat/miss pattern reveal about management guidance?\n\n"
        f"## Revenue vs EPS Growth\n"
        f"Is the company growing revenue or just cutting costs?\n\n"
        f"## Forward Estimates Assessment\n"
        f"Are consensus estimates reasonable? What are key assumptions?\n\n"
        f"## EPS Sensitivity\n"
        f"How does a 10% revenue miss/beat flow through to EPS?\n\n"
        f"## Key Earnings Drivers\n"
        f"Top 3 variables that will determine next quarter beat or miss.\n\n"
        f"## Post-Earnings Positioning\n"
        f"Historical post-earnings move patterns and how to position.",
        SYSTEM_FINANCIAL_ANALYST,
    )
    append_result({
        "id": str(uuid.uuid4())[:8],
        "type": "earnings",
        "ticker": ticker,
        "result": result,
        "ts": now_iso(),
    })
    return f"📈 *Earnings DeepSearch: {ticker}*\n\n{result}"


def cmd_status() -> str:
    """Show recent searches and active data sources."""
    results = []
    if RESULTS_FILE.exists():
        try:
            lines = [line for line in RESULTS_FILE.read_text().splitlines() if line.strip()]
            results = [json.loads(line) for line in lines[-10:]]
        except Exception:
            pass

    if not results:
        return (
            "No searches yet.\n"
            "Try: `deepsearch company AAPL` or `deepsearch market technology`"
        )

    lines = ["🔬 *Financial DeepSearch — Recent Searches:*"]
    for r in reversed(results[-5:]):
        rtype = r.get("type", "?")
        tickers = r.get("tickers")
        subject = (
            " vs ".join(tickers) if tickers
            else r.get("ticker") or r.get("sector") or r.get("topic") or "?"
        )
        lines.append(f"  • {rtype}: {subject} @ {r.get('ts', '?')}")

    sources = ["SEC EDGAR", "DuckDuckGo"]
    if _YFINANCE_AVAILABLE:
        sources.insert(0, "yfinance")
    if ALPHA_VANTAGE_KEY:
        sources.append("Alpha Vantage")
    lines.append(f"\n_Active sources: {', '.join(sources)}_")
    return "\n".join(lines)


# ── Orchestrator queue integration ────────────────────────────────────────────


def check_agent_queue() -> list:
    queue_file = AGENT_TASKS_DIR / "financial-deepsearch.queue.jsonl"
    if not queue_file.exists():
        return []
    lines = queue_file.read_text().splitlines()
    pending = []
    for line in lines:
        if line.strip():
            try:
                pending.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if pending:
        queue_file.write_text("")
    return pending


def process_subtask(subtask: dict) -> None:
    subtask_id = subtask.get("subtask_id", "")
    instructions = subtask.get("instructions", "")
    result = ai_query(instructions, SYSTEM_FINANCIAL_ANALYST)
    write_orchestrator_result(subtask_id, result)
    logger.info("financial-deepsearch: completed subtask '%s'", subtask_id)


# ── Command dispatch ──────────────────────────────────────────────────────────


def handle_command(message: str) -> str | None:
    msg = message.strip()
    msg_lower = msg.lower()

    if not msg_lower.startswith("deepsearch ") and msg_lower != "deepsearch":
        return None

    rest = msg[11:].strip() if msg_lower.startswith("deepsearch ") else ""
    rest_lower = rest.lower()

    if rest_lower.startswith("company "):
        return cmd_company(rest[8:].strip())
    if rest_lower.startswith("market "):
        return cmd_market(rest[7:].strip())
    if rest_lower.startswith("news "):
        return cmd_news(rest[5:].strip())
    if rest_lower.startswith("compare "):
        arg = rest[8:].strip()
        parts = arg.upper().split(" VS ")
        if len(parts) == 2:
            return cmd_compare(parts[0].strip(), parts[1].strip())
        tokens = arg.split()
        if len(tokens) >= 2:
            return cmd_compare(tokens[0], tokens[-1])
        return "Usage: `deepsearch compare AAPL vs MSFT`"
    if rest_lower.startswith("macro "):
        return cmd_macro(rest[6:].strip())
    if rest_lower.startswith("sec "):
        return cmd_sec(rest[4:].strip())
    if rest_lower.startswith("earnings "):
        return cmd_earnings(rest[9:].strip())
    if rest_lower == "status":
        return cmd_status()
    if rest_lower in ("help", ""):
        sources = "SEC EDGAR, DuckDuckGo"
        if _YFINANCE_AVAILABLE:
            sources = "yfinance, " + sources
        if ALPHA_VANTAGE_KEY:
            sources += ", Alpha Vantage"
        return (
            "🔬 *Financial DeepSearch (Dexter AI) Commands:*\n"
            "  `deepsearch company <ticker>` — comprehensive company deep-dive\n"
            "  `deepsearch market <sector>` — sector market analysis\n"
            "  `deepsearch news <ticker>` — latest news synthesis\n"
            "  `deepsearch compare <t1> vs <t2>` — side-by-side comparison\n"
            "  `deepsearch macro <topic>` — macroeconomic analysis\n"
            "  `deepsearch sec <ticker>` — SEC EDGAR filing insights\n"
            "  `deepsearch earnings <ticker>` — earnings deep dive\n"
            "  `deepsearch status` — recent searches & active sources\n\n"
            f"_Sources: {sources}_"
        )

    return "Unknown command. Try `deepsearch help`"


# ── Main loop ─────────────────────────────────────────────────────────────────


def main() -> None:
    sources = ["SEC EDGAR", "DuckDuckGo"]
    if _YFINANCE_AVAILABLE:
        sources.insert(0, "yfinance")
    if ALPHA_VANTAGE_KEY:
        sources.append("Alpha Vantage")

    ai_status = "AI routing active" if _AI_AVAILABLE else "AI router not available"
    print(
        f"[{now_iso()}] financial-deepsearch started; "
        f"poll={POLL_INTERVAL}s; {ai_status}; "
        f"sources: {', '.join(sources)}"
    )

    AGENT_TASKS_DIR.mkdir(parents=True, exist_ok=True)
    last_processed_idx = len(load_chatlog())

    write_state({
        "bot": "financial-deepsearch",
        "ts": now_iso(),
        "status": "starting",
        "sources": sources,
        "ai_available": _AI_AVAILABLE,
    })

    while True:
        for subtask in check_agent_queue():
            process_subtask(subtask)

        chatlog = load_chatlog()
        new_entries = chatlog[last_processed_idx:]
        last_processed_idx = len(chatlog)

        for entry in new_entries:
            if entry.get("type") != "user":
                continue
            message = entry.get("message", "").strip()
            if not message:
                continue
            response = handle_command(message)
            if response:
                append_chatlog({
                    "ts": now_iso(),
                    "type": "bot",
                    "bot": "financial-deepsearch",
                    "message": response,
                })
                logger.info("financial-deepsearch: handled command: %s", message[:60])

        write_state({
            "bot": "financial-deepsearch",
            "ts": now_iso(),
            "status": "running",
            "sources": sources,
            "ai_available": _AI_AVAILABLE,
        })

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
