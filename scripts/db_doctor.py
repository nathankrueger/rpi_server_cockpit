#!/usr/bin/env python3
"""
Database maintenance tool for the timeseries database.

Safe to run while the dashboard server is live (SQLite WAL mode handles
cross-process concurrency).
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

DB_PATH = 'timeseries.db'


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def action_list():
    """List all distinct sensor IDs in the database with summary info."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT timeseries_id,
               COUNT(*) as count,
               MIN(timestamp) as oldest,
               MAX(timestamp) as newest
        FROM timeseries_data
        GROUP BY timeseries_id
        ORDER BY timeseries_id
    ''')

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No sensor data in database.")
        return

    # Calculate column widths
    id_width = max(len(r['timeseries_id']) for r in rows)
    id_width = max(id_width, len("SENSOR ID"))

    print(f"{'SENSOR ID':<{id_width}}  {'POINTS':>8}  {'OLDEST':>19}  {'NEWEST':>19}")
    print(f"{'-' * id_width}  {'-' * 8}  {'-' * 19}  {'-' * 19}")

    for row in rows:
        oldest = datetime.fromtimestamp(row['oldest']).strftime('%Y-%m-%d %H:%M:%S')
        newest = datetime.fromtimestamp(row['newest']).strftime('%Y-%m-%d %H:%M:%S')
        print(f"{row['timeseries_id']:<{id_width}}  {row['count']:>8}  {oldest}  {newest}")

    print(f"\n{len(rows)} sensor(s) found.")


def action_clear(sensor_names):
    """Delete all data and metadata for the given sensors."""
    conn = get_connection()
    cursor = conn.cursor()

    # Gather row counts for confirmation
    counts = {}
    for name in sensor_names:
        cursor.execute(
            'SELECT COUNT(*) as cnt FROM timeseries_data WHERE timeseries_id = ?',
            (name,)
        )
        counts[name] = cursor.fetchone()['cnt']

    # Show summary and confirm
    print("Sensors to clear:")
    for name in sensor_names:
        print(f"  {name}: {counts[name]} data points")
    print()

    answer = input("Proceed with deletion? [y/N] ").strip().lower()
    if answer != 'y':
        print("Aborted.")
        conn.close()
        return

    # Delete data and metadata
    total_deleted = 0
    for name in sensor_names:
        cursor.execute(
            'DELETE FROM timeseries_data WHERE timeseries_id = ?', (name,)
        )
        deleted = cursor.rowcount
        total_deleted += deleted

        cursor.execute(
            'DELETE FROM external_timeseries WHERE id = ?', (name,)
        )
        meta_deleted = cursor.rowcount

        meta_msg = " (metadata removed)" if meta_deleted else ""
        print(f"  {name}: {deleted} data points deleted{meta_msg}")

    conn.commit()
    conn.close()

    print(f"\nTotal: {total_deleted} data points deleted.")

    # Vacuum to reclaim space
    size_before = os.path.getsize(DB_PATH)
    try:
        conn = get_connection()
        conn.execute('VACUUM')
        conn.close()
        size_after = os.path.getsize(DB_PATH)
        saved = size_before - size_after
        if saved > 0:
            print(f"VACUUM reclaimed {saved / 1024:.1f} KB "
                  f"({size_before / 1024:.0f} KB -> {size_after / 1024:.0f} KB)")
        else:
            print("VACUUM complete (no space to reclaim).")
    except sqlite3.OperationalError:
        print("VACUUM skipped (database busy). Space will be reclaimed later by auto_vacuum.")


ACTIONS = {
    'clear': action_clear,
}


def main():
    parser = argparse.ArgumentParser(
        description='Timeseries database maintenance tool.'
    )
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List all sensors in the database'
    )
    parser.add_argument(
        '-s', '--sensor_name',
        nargs='+',
        metavar='ID',
        help='Sensor ID(s) to operate on (e.g. garage_temp patio_humidity)'
    )
    parser.add_argument(
        '-a', '--action',
        choices=ACTIONS.keys(),
        help='Action to perform'
    )

    args = parser.parse_args()

    # Validate arg combinations
    if not args.list and not args.action:
        parser.error('one of -l/--list or -a/--action is required')
    if args.action and not args.sensor_name:
        parser.error('-s/--sensor_name is required when using -a/--action')

    if not os.path.exists(DB_PATH):
        print(f"Error: database not found at {DB_PATH}", file=sys.stderr)
        print("Run this script from the project root directory.", file=sys.stderr)
        sys.exit(1)

    if args.list:
        action_list()
        return

    ACTIONS[args.action](args.sensor_name)


if __name__ == '__main__':
    main()
