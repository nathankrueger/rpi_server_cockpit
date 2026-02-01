"""External API routes (stocks, weather)."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from utils import lttb_downsample

external_bp = Blueprint('external', __name__)


@external_bp.route('/api/stocks/daily-change', methods=['POST'])
def get_stock_daily_change():
    """Get cumulative percentage return for stock symbols from period start.

    This shows how each stock has performed relative to the start of the period,
    making it easy to compare stocks with different share prices.

    Request body:
        symbols: list of stock symbols
        days: number of days of data to fetch (0 = all available, default 30)
        max_points: maximum data points per symbol (uses LTTB downsampling, default 10000)
    """
    try:
        data = request.get_json()
        symbols = data.get('symbols', [])
        requested_days = data.get('days', 30)
        max_points = data.get('max_points', 10000)

        if not symbols:
            return jsonify({'success': False, 'error': 'No symbols provided'}), 400

        stock_data = {}

        for symbol in symbols:
            try:
                # Use Yahoo Finance API to get stock data
                # Choose interval based on date range for best resolution
                end_date = datetime.now()

                if requested_days == 0:
                    # All time - use weekly interval
                    start_date = end_date - timedelta(days=365 * 50)
                    interval = '1wk'
                elif requested_days <= 7:
                    # 1 week or less - use 5 minute intervals for high resolution
                    start_date = end_date - timedelta(days=requested_days + 1)
                    interval = '5m'
                elif requested_days <= 60:
                    # Up to 2 months - use hourly intervals
                    start_date = end_date - timedelta(days=requested_days + 1)
                    interval = '1h'
                elif requested_days <= 365 * 2:
                    # Up to 2 years - use daily intervals
                    start_date = end_date - timedelta(days=requested_days + 30)
                    interval = '1d'
                else:
                    # More than 2 years - use weekly intervals
                    start_date = end_date - timedelta(days=requested_days + 30)
                    interval = '1wk'

                period1 = int(start_date.timestamp())
                period2 = int(end_date.timestamp())

                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={period1}&period2={period2}&interval={interval}"

                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=15) as response:
                    result = json.loads(response.read().decode())

                if 'chart' in result and 'result' in result['chart'] and result['chart']['result']:
                    chart_data = result['chart']['result'][0]
                    timestamps = chart_data.get('timestamp', [])
                    quotes = chart_data['indicators']['quote'][0]
                    close_prices = quotes.get('close', [])

                    if not timestamps or not close_prices:
                        stock_data[symbol] = {
                            'dates': [],
                            'cumulative_return': [],
                            'error': 'No data available'
                        }
                        continue

                    # Filter to requested time range first
                    if requested_days > 0:
                        cutoff_time = end_date.timestamp() - (requested_days * 24 * 60 * 60)
                        filtered_data = [
                            (t, p) for t, p in zip(timestamps, close_prices)
                            if t >= cutoff_time and p is not None
                        ]
                    else:
                        filtered_data = [
                            (t, p) for t, p in zip(timestamps, close_prices)
                            if p is not None
                        ]

                    if not filtered_data:
                        stock_data[symbol] = {
                            'dates': [],
                            'cumulative_return': [],
                            'error': 'No data in range'
                        }
                        continue

                    # Calculate cumulative % return from period start
                    # All values are relative to the first price in the period
                    base_price = filtered_data[0][1]
                    raw_data = []  # List of (index, timestamp, cumulative_return)

                    for idx, (t, price) in enumerate(filtered_data):
                        cumulative_return = ((price - base_price) / base_price) * 100
                        raw_data.append((idx, t, round(cumulative_return, 4)))

                    # Apply LTTB downsampling if needed
                    # Use index as X for LTTB to preserve visual shape without time gaps
                    if len(raw_data) > max_points:
                        lttb_input = [(idx, val) for idx, t, val in raw_data]
                        downsampled_indices = set()
                        downsampled = lttb_downsample(lttb_input, max_points)
                        downsampled_indices = {int(idx) for idx, _ in downsampled}
                        raw_data = [item for item in raw_data if item[0] in downsampled_indices]

                    # Format dates for labels - compact format for axis ticks
                    if interval in ['5m', '15m', '30m', '1h']:
                        date_format = '%m/%d'  # Just month/day for intraday
                    elif interval == '1d':
                        date_format = '%b %d'  # "Jan 15" for daily
                    else:
                        date_format = '%b %y'  # "Jan 25" for weekly/longer

                    # Create sequential indices and formatted date labels
                    indices = list(range(len(raw_data)))
                    date_labels = [datetime.fromtimestamp(t).strftime(date_format) for _, t, _ in raw_data]
                    cumulative_returns = [val for _, _, val in raw_data]

                    stock_data[symbol] = {
                        'indices': indices,
                        'date_labels': date_labels,
                        'cumulative_return': cumulative_returns,
                        'interval': interval,
                        'raw_points': len(timestamps),
                        'displayed_points': len(raw_data),
                        'base_price': round(base_price, 2)
                    }
                else:
                    stock_data[symbol] = {
                        'dates': [],
                        'cumulative_return': [],
                        'error': 'No data available'
                    }

            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
                stock_data[symbol] = {
                    'dates': [],
                    'cumulative_return': [],
                    'error': str(e)
                }

        return jsonify({'success': True, 'data': stock_data})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@external_bp.route('/api/weather', methods=['POST'])
def get_weather():
    """Get weather data for a given location using wttr.in service."""
    try:
        data = request.get_json()
        location = data.get('location', '')

        if not location:
            return jsonify({'success': False, 'error': 'No location provided'}), 400

        # Use wttr.in API (free, no API key required)
        # Format: wttr.in/Location?format=j1 for JSON
        encoded_location = urllib.parse.quote(location)
        url = f"https://wttr.in/{encoded_location}?format=j1"

        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            weather_data = json.loads(response.read().decode())

        # Extract current weather
        current = weather_data['current_condition'][0]
        temp_f = current['temp_F']
        condition = current['weatherDesc'][0]['value']

        # Get location name from nearest area
        location_name = weather_data['nearest_area'][0]['areaName'][0]['value']
        region = weather_data['nearest_area'][0].get('region', [{}])[0].get('value', '')
        country = weather_data['nearest_area'][0].get('country', [{}])[0].get('value', '')

        full_location = f"{location_name}"
        if region:
            full_location += f", {region}"
        if country and country != "United States of America":
            full_location += f", {country}"

        return jsonify({
            'success': True,
            'temperature': float(temp_f),
            'condition': condition,
            'location': full_location
        })

    except Exception as e:
        print(f"Error fetching weather: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
