from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
import streamlit as st
import yfinance as yf


API_BASE_URL = "http://localhost:8000"


st.set_page_config(page_title="Financial Instrument Analyzer", layout="wide")

st.title("Financial Instrument Analyzer")

with st.sidebar:
    st.header("Data source")
    data_source = st.selectbox("Mode", ["Direct yfinance", "FastAPI backend"])
    api_base_url = st.text_input("FastAPI base URL", value=API_BASE_URL, disabled=data_source == "Direct yfinance")
    news_limit = st.slider("News items", min_value=0, max_value=20, value=5)

symbol = st.text_input("Stock or financial instrument symbol", placeholder="AAPL, MSFT, TSLA, BTC-USD")
submitted = st.button("Fetch data", type="primary")


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def format_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def percentage_change(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or start == 0:
        return None
    return round(((end - start) / start) * 100, 2)


def price_change_for_period(ticker: yf.Ticker, period: str, interval: str) -> float | None:
    history = ticker.history(period=period, interval=interval, auto_adjust=False)
    if history.empty or "Close" not in history:
        return None

    closes = history["Close"].dropna()
    if len(closes) < 2:
        return None

    return percentage_change(float(closes.iloc[0]), float(closes.iloc[-1]))


def format_news_timestamp(timestamp: Any) -> str | None:
    if not isinstance(timestamp, (int, float)):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def extract_news(ticker: yf.Ticker, limit: int) -> list[dict[str, Any]]:
    news_items: list[dict[str, Any]] = []

    for item in (ticker.news or [])[:limit]:
        content = item.get("content", item)
        title = content.get("title") or item.get("title")
        if not title:
            continue

        click_through_url = content.get("clickThroughUrl") or {}
        canonical_url = content.get("canonicalUrl") or {}
        provider = content.get("provider") or {}

        news_items.append(
            {
                "title": title,
                "publisher": provider.get("displayName") or item.get("publisher"),
                "link": click_through_url.get("url") or canonical_url.get("url") or item.get("link"),
                "published_at": format_news_timestamp(
                    content.get("pubDate")
                    if isinstance(content.get("pubDate"), (int, float))
                    else item.get("providerPublishTime")
                ),
                "summary": content.get("summary"),
            }
        )

    return news_items


def fetch_from_yfinance(symbol: str, limit: int) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    ticker = yf.Ticker(normalized_symbol)
    info = ticker.get_info()

    current_price = None
    for key in ("regularMarketPrice", "currentPrice", "previousClose"):
        value = info.get(key)
        if isinstance(value, (int, float)) and value > 0:
            current_price = float(value)
            break

    if current_price is None:
        history = ticker.history(period="1d", interval="1m", auto_adjust=False)
        closes = history["Close"].dropna() if not history.empty and "Close" in history else []
        if len(closes) > 0:
            current_price = float(closes.iloc[-1])

    if current_price is None:
        raise ValueError(f"No market data found for {normalized_symbol}.")

    return {
        "symbol": normalized_symbol,
        "short_name": info.get("shortName") or info.get("longName"),
        "currency": info.get("currency"),
        "current_price": round(current_price, 4),
        "changes": {
            "one_hour": price_change_for_period(ticker, "1d", "1m"),
            "one_week": price_change_for_period(ticker, "5d", "30m"),
            "one_month": price_change_for_period(ticker, "1mo", "1d"),
            "one_year": price_change_for_period(ticker, "1y", "1d"),
        },
        "news": extract_news(ticker, limit),
        "fetched_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def fetch_from_backend(symbol: str, limit: int, base_url: str) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}/quote/{symbol}",
        params={"news_limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


if submitted:
    normalized_symbol = symbol.strip()

    if not normalized_symbol:
        st.warning("Enter a symbol to continue.")
        st.stop()

    with st.spinner(f"Fetching market data for {normalized_symbol.upper()}..."):
        try:
            if data_source == "Direct yfinance":
                data = fetch_from_yfinance(normalized_symbol, news_limit)
            else:
                data = fetch_from_backend(normalized_symbol, news_limit, api_base_url)
        except requests.exceptions.HTTPError as exc:
            detail = exc.response.json().get("detail", exc.response.text)
            st.error(f"Backend error: {detail}")
            st.stop()
        except requests.exceptions.RequestException as exc:
            st.error(f"Could not reach the FastAPI backend: {exc}")
            st.stop()
        except Exception as exc:
            st.error(f"Could not fetch market data: {exc}")
            st.stop()

    heading = data.get("short_name") or data["symbol"]
    currency = data.get("currency") or ""
    st.subheader(f"{heading} ({data['symbol']})")

    price_label = f"{data['current_price']:,.4f} {currency}".strip()
    st.metric("Current price", price_label)

    changes = data.get("changes", {})
    cols = st.columns(4)
    cols[0].metric("1 hour", format_percent(changes.get("one_hour")))
    cols[1].metric("1 week", format_percent(changes.get("one_week")))
    cols[2].metric("1 month", format_percent(changes.get("one_month")))
    cols[3].metric("1 year", format_percent(changes.get("one_year")))

    st.caption(f"Fetched at {format_datetime(data.get('fetched_at'))}")

    st.divider()
    st.subheader("Latest news")

    news_items = data.get("news", [])
    if not news_items:
        st.info("No recent yfinance news was returned for this symbol.")
    else:
        for item in news_items:
            title = item.get("title", "Untitled")
            link = item.get("link")
            publisher = item.get("publisher") or "Unknown publisher"
            published_at = format_datetime(item.get("published_at"))

            if link:
                st.markdown(f"### [{title}]({link})")
            else:
                st.markdown(f"### {title}")

            meta = " | ".join(part for part in (publisher, published_at) if part)
            if meta:
                st.caption(meta)

            if item.get("summary"):
                st.write(item["summary"])
else:
    st.info("Enter a symbol and fetch the latest market snapshot.")
