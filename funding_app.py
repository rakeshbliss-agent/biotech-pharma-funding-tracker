#!/usr/bin/env python3
"""
A minimal web application to serve a biotech/pharma funding tracker.

This script starts a simple HTTP server that reads a JSON file containing
funding rounds (generated from an Excel tracker) and serves an HTML
page showing the funding events in reverse chronological order.  A
"Refresh" link allows users to reload the data, reflecting any updates
made to the JSON file by an external script.

To start the server:

    python3 funding_app.py --host 0.0.0.0 --port 8000

Then visit http://localhost:8000/ in your browser.

Assumes `funding_data.json` is located in the same directory.
"""

import json
import os
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any, Dict, List, Optional


DATA_FILE = os.path.join(os.path.dirname(__file__), 'funding_data.json')


def load_funding_data() -> List[Dict[str, Any]]:
    """Load funding data from the JSON file and sort by date descending."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Convert date strings to datetime objects for sorting; keep None as None
    def parse_date(entry: Dict[str, Any]) -> Optional[datetime]:
        date_str = entry.get('Funding date')
        if date_str:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pass
        return None
    sorted_data = sorted(data, key=lambda x: parse_date(x) or datetime.min, reverse=True)
    return sorted_data


class FundingTrackerHandler(SimpleHTTPRequestHandler):
    """HTTP request handler that serves the funding tracker page."""

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path in ('/', '/index'):
            # Serve the main page with funding table
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            funding_data = load_funding_data()
            self.wfile.write(self.render_html(funding_data).encode('utf-8'))
        elif parsed_path.path == '/refresh':
            # Force reloading the data and redirect back to the index
            # In this simple implementation, reloading just means reading
            # the JSON file again on the next request. Here we return a
            # redirect response back to the main page.
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            # Fallback to default behavior for other paths (e.g., static files)
            super().do_GET()

    def render_html(self, funding_data: List[Dict[str, Any]]) -> str:
        """Generate HTML for the funding table."""
        # Basic inline CSS for readability
        styles = """
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { margin-bottom: 10px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 6px; text-align: left; }
            th { background-color: #f2f2f2; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            .small-col { white-space: nowrap; }
            a.refresh { margin-top: 10px; display: inline-block; }
            .footer { margin-top: 20px; font-size: 0.9em; color: #666; }
        </style>
        """
        # Generate table headers
        headers = [
            'Company', 'Funding date', 'Funding round', 'Funding amount',
            'Investors', 'Description', 'Therapeutic Area', 'Therapeutic Modality',
            'Lead Clinical Stage', 'Small molecule modality?', 'HQ City', 'HQ State/Region'
        ]
        header_html = ''.join(f'<th>{h}</th>' for h in headers)

        # Generate table rows
        rows_html_parts = []
        for entry in funding_data:
            cells = []
            for key in headers:
                value = entry.get(key)
                if value is None:
                    value_str = ''
                else:
                    value_str = str(value)
                cells.append(f'<td>{value_str}</td>')
            row_html = '<tr>' + ''.join(cells) + '</tr>'
            rows_html_parts.append(row_html)
        rows_html = '\n'.join(rows_html_parts)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Biotech/Pharma Funding Tracker</title>
    {styles}
</head>
<body>
    <h1>Biotech/Pharma Funding Tracker</h1>
    <a class="refresh" href="/refresh">Refresh Data</a>
    <table>
        <thead>
            <tr>{header_html}</tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    <div class="footer">
        Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
        Data source: funding_data.json (external updates required for new entries)
    </div>
</body>
</html>
"""
        return html


def run_server(host: str = '0.0.0.0', port: int = 8000):
    """Start the HTTP server."""
    server_address = (host, port)
    httpd = HTTPServer(server_address, FundingTrackerHandler)
    print(f"Serving funding tracker on http://{host}:{port} ...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Run the funding tracker web server.')
    parser.add_argument('--host', default='0.0.0.0', help='Hostname to listen on (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8000, help='Port to listen on (default: 8000)')
    args = parser.parse_args()
    run_server(args.host, args.port)
