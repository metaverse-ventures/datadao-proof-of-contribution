# proof_of_quality.py
import pandas as pd
import os
import logging
from typing import Dict, Any

points = {
    "REDDIT":50,
    "STEAM":50,
    "UBER":50,
    "LINKEDIN":50,
    "TWITCH":50,
    "AMAZON_PRIME":50,
    "NETFLIX":50,
    "ZOMATO":50,
    "SPOTIFY":50,
    "TWITTER":50,
}

def calculate_max_points(points_dict):
    return sum(points_dict.values())

# Scoring thresholds
def get_watch_history_score(count, task_type):
    max_point = points[task_type]
    if count >= 10:
        return max_point
    elif 4 <= count <= 9:
        return max_point * 0.5
    elif 1 <= count <= 3:
        return max_point * 0.1
    else:
        return 0

def calculate_watch_score(watch_data, task_type):
    df = pd.DataFrame(watch_data)
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%y')

    start_date = df['Date'].min()
    end_date = df['Date'].max()

    intervals = pd.date_range(start=start_date, end=end_date, freq='15D')
    interval_counts = []
    for i in range(len(intervals) - 1):
        interval_start = intervals[i]
        interval_end = intervals[i + 1]
        count = df[(df['Date'] >= interval_start) & (df['Date'] < interval_end)].shape[0]
        interval_counts.append(count)

    interval_scores = [get_watch_history_score(count, task_type) for count in interval_counts]

    overall_score = sum(interval_scores) / len(interval_scores) if interval_scores else 0

    return overall_score, interval_scores

def get_order_history_score(orderCount, task_type):
    max_point = points[task_type]

    if orderCount >= 10:
        return max_point
    elif 5 <= orderCount <= 9:
        return max_point * 0.5
    elif 1 <= orderCount <= 4:
        return max_point * 0.1
    else:
        return 0

def get_coins_pairs_score(unique_counts, task_type):
    max_point = points[task_type]
    total_count = unique_counts

    if total_count >= 10:
        return max_point
    elif 4 <= total_count <= 9:
        return max_point * 0.5
    elif 1 <= total_count <= 3:
        return max_point * 0.1
    else:
        return 0

def calculate_browser_history_score(csv_path):
    df = pd.read_csv(csv_path)
    df['DateTime'] = pd.to_datetime(df['DateTime'])

    unique_rows = df.drop_duplicates(subset=['DateTime', 'NavigatedToUrl', 'PageTitle'])
    unique_count = len(unique_rows)
    base_score = 50

    if unique_count > 10000:
        uniqueness_score = base_score
    elif unique_count > 5000:
        uniqueness_score = 0.7 * base_score
    elif unique_count > 2000:
        uniqueness_score = 0.5 * base_score
    elif unique_count > 10:
        uniqueness_score = 0.05 * base_score
    else:
        uniqueness_score = 0

    max_date_diff = (df['DateTime'].max() - df['DateTime'].min()).days

    if max_date_diff > 180:
        date_range_score = 50
    elif 120 <= max_date_diff <= 180:
        date_range_score = 0.5 * 50
    else:
        date_range_score = 0

    total_score = int(uniqueness_score + date_range_score) / 2

    logging.info(f"Browser History Score: {total_score}")
    return total_score

def calculate_quality_score(input_data, config, unique_entry_details):
    """Calculate quality score based on contribution data and input files."""
    final_scores = {}
    total_secured_score = 0
    total_max_score = 0

    # Convert unique_entry_details into a dictionary for quick lookup
    logging.info(f"unique_entry_details is {unique_entry_details}")
    unique_entries_dict = {
    entry["type"]: {
        "unique_entry_count": entry["unique_entry_count"], 
        "type_unique_score": entry["type_unique_score"]
    }
        for entry in unique_entry_details
    }
    # Loop through each contribution in the input data
    for contribution in input_data['contribution']:
        task_type = contribution['type']
        securedSharedData = contribution['securedSharedData']
        type_unique_count = unique_entries_dict.get(task_type)["unique_entry_count"] # Get unique entries if available
        type_uniqueness_score = unique_entries_dict.get(task_type)["type_unique_score"] 

        # if task_type == 'NETFLIX_HISTORY':
        #    # score, _ = calculate_watch_score(securedSharedData['csv'], task_type)
        #     score = get_watch_history_score(type_unique_count, task_type)
        # elif task_type == 'COINMARKETCAP_USER_WATCHLIST':
        #     score = get_coins_pairs_score(type_unique_count, task_type)  # Use unique_entries instead of coins_count
        if task_type in ['UBER', 'AMAZON_PRIME', 'ZOMATO', 'SPOTIFY', 'NETFLIX']:
            score = get_order_history_score(type_unique_count, task_type)  # Use unique_entries instead of order_count
        elif task_type in ['REDDIT', 'STEAM', 'TWITCH',' TWITTER', 'LINKEDIN']:
            score = points[task_type] * type_uniqueness_score
        else:
            score = 0  # Default score for unknown types

        final_scores[task_type] = score
        total_secured_score += score

    # Check for CSV files starting with 'BrowserHistory' in the input directory
    csv_file = [f for f in os.listdir(config['input_dir']) if f.startswith("BrowserHistory") and f.endswith(".csv")]
    browser_history_score = 0
    if csv_file:
        csv_path = os.path.join(config['input_dir'], csv_file[0])
        browser_history_score = calculate_browser_history_score(csv_path)
        total_secured_score += browser_history_score
        total_max_score += 50

    total_max_score += calculate_max_points(points)

    # Normalize the total score
    normalized_total_score = total_secured_score / total_max_score if total_max_score > 0 else 0

    # Log the results
    logging.info(f"Total Secured Score: {total_secured_score}")
    logging.info(f"Total Max Score: {total_max_score}")
    logging.info(f"Normalized Total Score: {normalized_total_score}")

    return normalized_total_score
